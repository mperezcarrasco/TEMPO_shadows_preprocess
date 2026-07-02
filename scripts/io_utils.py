"""I/O helpers for the day-by-day TEMPO shadow-detection pipeline.

- File pairing (L1B → L2 CLDO4 via timestamp/scan/granule)
- L1B and L2 array loading (with explicit fill handling)
- Orientation transforms matching the visualization convention
- GeoTIFF (RGB) and shapefile (cloud / PCSF / ACSF) writers
"""
from __future__ import annotations

import glob
import os
import re
from typing import Optional, Tuple

import warnings

import fiona
import geopandas as gpd
import h5py
import netCDF4 as nc
import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.transform import from_bounds
from shapely.geometry import mapping, shape


TIMESTAMP_RE = re.compile(r"(\d{8}T\d{6}Z)_S(\d{3})G(\d{2})")


def extract_timestamp_scan(filename: str):
    """Return (timestamp, scan, granule) parsed from a TEMPO filename."""
    m = TIMESTAMP_RE.search(filename)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None, None, None


def find_matching_l2_file(
    l1_file: str, l2_dir: str, version: str,
) -> Optional[str]:
    """Locate the CLDO4 L2 file matching this L1B granule, or None."""
    ts, scan, granule = extract_timestamp_scan(l1_file)
    if ts is None:
        return None
    exact = os.path.join(
        l2_dir,
        f"TEMPO_CLDO4_L2_{version}_{ts}_S{scan}G{granule.split('-')[0]}.nc",
    )
    if os.path.exists(exact):
        return exact
    pattern = os.path.join(
        l2_dir, f"TEMPO_CLDO4_L2_{version}_{ts}_S{scan}G*.nc"
    )
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def _h5_read_float(dset) -> np.ndarray:
    """Read an HDF5 dataset, cast to float64, and convert ``_FillValue`` to NaN."""
    arr = np.asarray(dset[:])
    if not np.issubdtype(arr.dtype, np.floating):
        arr = arr.astype(np.float64)
    if "_FillValue" in dset.attrs:
        fv = dset.attrs["_FillValue"]
        if hasattr(fv, "__len__") and len(fv) == 1:
            fv = fv[0]
        arr = np.where(arr == fv, np.nan, arr)
    return arr


def load_l1b(l1_file: str, band: str) -> dict:
    """Load RGB, L1B cloud_top_height, and the four angles from the L1B band group.

    Uses ``h5py`` directly. TEMPO L1B files are HDF5 but do not always satisfy
    the strict NetCDF-4 subset that ``netCDF4.Dataset`` requires — on some
    archives ``nc.Dataset`` raises ``[Errno -101] NetCDF: HDF error`` while the
    very same file opens fine with ``h5py``. The reference snippet supplied
    with the data also uses ``h5py``, so this loader matches that contract.

    Raises
    ------
    ValueError
        If any of the four angles is entirely fill-valued (the algorithm cannot
        proceed without geometry).
    """
    with h5py.File(l1_file, "r") as f:
        g = f[band]
        sza = _h5_read_float(g["solar_zenith_angle"])
        saa = _h5_read_float(g["solar_azimuth_angle"])
        vza = _h5_read_float(g["viewing_zenith_angle"])
        vaa = _h5_read_float(g["viewing_azimuth_angle"])
        cth = _h5_read_float(g["cloud_top_height"])
        cmg = f["cloud_mask_group"]
        red   = _h5_read_float(cmg["red"])
        green = _h5_read_float(cmg["green"])
        blue  = _h5_read_float(cmg["blue"])

    for name, arr in [("sza", sza), ("saa", saa), ("vza", vza), ("vaa", vaa)]:
        if int(np.isfinite(arr).sum()) == 0:
            raise ValueError(
                f"L1B angle '{name}' is entirely fill-valued in {l1_file}"
            )
    return {
        "red": red, "green": green, "blue": blue,
        "cth": cth, "sza": sza, "saa": saa, "vza": vza, "vaa": vaa,
    }


def _h5_read_with_fill(dset, fill_replacement: float) -> np.ndarray:
    """Read an HDF5 dataset, cast to float64, replace ``_FillValue`` with the given value."""
    arr = np.asarray(dset[:])
    if not np.issubdtype(arr.dtype, np.floating):
        arr = arr.astype(np.float64)
    if "_FillValue" in dset.attrs:
        fv = dset.attrs["_FillValue"]
        if hasattr(fv, "__len__") and len(fv) == 1:
            fv = fv[0]
        arr = np.where(arr == fv, fill_replacement, arr)
    return arr


def load_l2(l2_file: str) -> dict:
    """Load lat/lon, ECF, cloud and surface pressure, terrain height from CLDO4 L2.

    Uses ``h5py`` directly. On shared/NFS storage, ``netCDF4.Dataset`` sometimes
    raises ``[Errno -101] NetCDF: HDF error`` (HDF5 file-locking / version
    issues) while ``h5py`` opens the same file fine.
    """
    with h5py.File(l2_file, "r") as f:
        lat = _h5_read_with_fill(f["geolocation/latitude"],         np.nan)
        lon = _h5_read_with_fill(f["geolocation/longitude"],        np.nan)
        cloud_fraction   = _h5_read_with_fill(f["product/cloud_fraction"],   -999.0)
        cloud_pressure   = _h5_read_with_fill(f["product/cloud_pressure"],   np.nan)
        terrain_height   = _h5_read_with_fill(f["support_data/terrain_height"],     0.0)
        surface_pressure = _h5_read_with_fill(f["support_data/surface_pressure"], np.nan)
    return {
        "lat": lat, "lon": lon,
        "cloud_fraction":   cloud_fraction,
        "cloud_pressure":   cloud_pressure,
        "terrain_height":   terrain_height,
        "surface_pressure": surface_pressure,
    }


def orient_2d(arr: np.ndarray) -> np.ndarray:
    """transpose+flip for GIS alignment (matches test/netcdf_to_raster_with_L2.py)."""
    return np.flip(np.transpose(arr, (1, 0)), axis=0)


def write_rgb_geotiff(
    out_path: str,
    red: np.ndarray, green: np.ndarray, blue: np.ndarray,
    lat: np.ndarray, lon: np.ndarray,
    apply_gamma: bool, gamma: float,
) -> Tuple[object, Tuple[int, int]]:
    """Write a 3-band RGB GeoTIFF at EPSG:4326 with a bounding-box affine transform.

    Returns the affine ``transform`` and ``(height, width)`` so callers can
    align downstream shapefiles to the same georeferencing.
    """
    # Clip to [0, 1] and replace NaN with 0 BEFORE gamma — NaN**0.4 would warn.
    def _clean(ch):
        ch = np.nan_to_num(ch, nan=0.0, posinf=1.0, neginf=0.0)
        return np.clip(ch, 0.0, 1.0)

    red, green, blue = _clean(red), _clean(green), _clean(blue)
    if apply_gamma:
        red   = red   ** gamma
        green = green ** gamma
        blue  = blue  ** gamma

    red_o   = orient_2d(red)
    green_o = orient_2d(green)
    blue_o  = orient_2d(blue)
    lon_o   = orient_2d(lon)
    lat_o   = orient_2d(lat)

    west  = float(np.nanmin(lon_o)); east  = float(np.nanmax(lon_o))
    south = float(np.nanmin(lat_o)); north = float(np.nanmax(lat_o))
    if not all(np.isfinite([west, east, south, north])):
        raise ValueError(
            f"Non-finite lat/lon bounding box for {out_path}; cannot georeference."
        )

    height, width = red_o.shape
    transform = from_bounds(west, south, east, north, width, height)

    red_8   = (np.nan_to_num(red_o,   nan=0.0) * 255).astype(np.uint8)
    green_8 = (np.nan_to_num(green_o, nan=0.0) * 255).astype(np.uint8)
    blue_8  = (np.nan_to_num(blue_o,  nan=0.0) * 255).astype(np.uint8)

    with rasterio.open(
        out_path, "w",
        driver="GTiff", height=height, width=width, count=3,
        dtype=np.uint8, crs="EPSG:4326", transform=transform,
        compress="lzw",
    ) as dst:
        dst.write(red_8,   1)
        dst.write(green_8, 2)
        dst.write(blue_8,  3)
        dst.set_band_description(1, "Red")
        dst.set_band_description(2, "Green")
        dst.set_band_description(3, "Blue")

    return transform, (height, width)


_SHP_SCHEMA = {
    "geometry": "Polygon",
    "properties": {
        "type":      "str:32",
        "name":      "str:64",
        "value":     "int",
        "source":    "str:128",
        "area_deg2": "float",
    },
}


def write_mask_shapefile(
    out_path: str, mask_oriented: np.ndarray, transform,
    mask_type: str, mask_name: str, source_file: str,
) -> Optional[str]:
    """Polygonize an oriented boolean mask and write as a shapefile (EPSG:4326).

    Uses ``fiona`` directly (not ``GeoDataFrame.to_file``) to avoid the NumPy
    2.0 + GeoPandas issue where ``iterfeatures()`` calls
    ``np.array(geometry, copy=False)`` which is no longer allowed.

    Returns the output path, or None if the mask has no True pixels.
    """
    mask_int = mask_oriented.astype(np.int32)
    results = list(shapes(mask_int, mask=(mask_int == 1), transform=transform))
    if not results:
        return None

    # Suppress the geographic-CRS area warning — degree² is a relative-size
    # proxy, not a real area; users who need true area should reproject in GIS.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with fiona.open(
            out_path, "w",
            driver="ESRI Shapefile",
            schema=_SHP_SCHEMA,
            crs="EPSG:4326",
        ) as dst:
            for geom, value in results:
                shp = shape(geom)
                dst.write({
                    "geometry":   mapping(shp),
                    "properties": {
                        "type":      mask_type,
                        "name":      mask_name,
                        "value":     int(value),
                        "source":    source_file,
                        "area_deg2": float(shp.area),
                    },
                })
    return out_path
