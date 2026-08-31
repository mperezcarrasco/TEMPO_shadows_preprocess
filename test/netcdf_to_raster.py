import glob
import h5py
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import shape, mapping
import geopandas as gpd
from rasterio.features import shapes
import os

# Create output directories
os.makedirs('geotiff_output', exist_ok=True)
os.makedirs('shapefile_output', exist_ok=True)

# Process files
files = glob.glob('../data/raw_l1/*.nc')
print(f"Found {len(files)} files to process")

for file in files:
    print(f"\nProcessing: {file}")
    
    # Read the red, green, blue variables and cloud mask
    with h5py.File(file, 'r') as f:
        red = f['cloud_mask_group']['red'][:]
        green = f['cloud_mask_group']['green'][:]
        blue = f['cloud_mask_group']['blue'][:]
        cloud = f['cloud_mask_group']['cloud_mask'][:]
        
        # Read geolocation data from the VIS band group
        # TEMPO stores lat/lon in band_540_740_nm group
        try:
            lon = f['band_540_740_nm']['longitude'][:]
            lat = f['band_540_740_nm']['latitude'][:]
            has_geo = True
        except:
            # Fallback: try UV band or use default extent
            try:
                lon = f['band_290_490_nm']['longitude'][:]
                lat = f['band_290_490_nm']['latitude'][:]
                has_geo = True
            except:
                has_geo = False
                print("  Geolocation data not found, using default TEMPO extent")
    
    print(f"  Cloud mask unique values: {np.unique(cloud)}")
    
    # Clip the RGB values exceeding 1.0
    red = np.where((red > 1.0), 1.0, red)
    green = np.where((green > 1.0), 1.0, green)
    blue = np.where((blue > 1.0), 1.0, blue)
    
    # Apply power of 0.4 to brighten
    red = red**0.4
    green = green**0.4
    blue = blue**0.4
    
    # Transpose and flip for correct orientation
    red = np.flip(np.transpose(red, (1, 0)), axis=0)
    green = np.flip(np.transpose(green, (1, 0)), axis=0)
    blue = np.flip(np.transpose(blue, (1, 0)), axis=0)
    cloud = np.flip(np.transpose(cloud, (1, 0)), axis=0)
    
    # Get dimensions
    height, width = red.shape
    
    # Define geographic extent
    if has_geo:
        # Use actual geolocation data
        lon_transposed = np.flip(np.transpose(lon, (1, 0)), axis=0)
        lat_transposed = np.flip(np.transpose(lat, (1, 0)), axis=0)
        west = float(np.nanmin(lon_transposed))
        east = float(np.nanmax(lon_transposed))
        south = float(np.nanmin(lat_transposed))
        north = float(np.nanmax(lat_transposed))
    else:
        # Default TEMPO coverage
        west, south, east, north = -140.0, 15.0, -60.0, 60.0
    
    # Create affine transform
    transform = from_bounds(west, south, east, north, width, height)
    
    # === Export RGB as GeoTIFF ===
    output_tif = f"geotiff_output/rgb_{os.path.basename(file).replace('.nc', '.tif')}"
    
    # Convert to 8-bit (0-255) for standard image format
    red_8bit = (red * 255).astype(np.uint8)
    green_8bit = (green * 255).astype(np.uint8)
    blue_8bit = (blue * 255).astype(np.uint8)
    
    # Write GeoTIFF with 3 bands (RGB)
    with rasterio.open(
        output_tif,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=3,
        dtype=np.uint8,
        crs='EPSG:4326',  # WGS84
        transform=transform,
        compress='lzw'
    ) as dst:
        dst.write(red_8bit, 1)
        dst.write(green_8bit, 2)
        dst.write(blue_8bit, 3)
        dst.set_band_description(1, 'Red')
        dst.set_band_description(2, 'Green')
        dst.set_band_description(3, 'Blue')
    
    print(f"  Saved GeoTIFF: {output_tif}")
    
    # === Export Cloud Mask as Shapefile ===
    output_shp = f"shapefile_output/cloud_mask_{os.path.basename(file).replace('.nc', '.shp')}"
    
    # Convert cloud mask to integer type
    cloud_int = cloud.astype(np.int32)
    
    # Extract shapes from the cloud mask
    # shapes() returns (geometry, value) pairs
    # Note: cloud_mask values are 0 (no cloud), 1 (cloudy), and potentially 2 (missing)
    # according to your original description, but the user guide only mentions 0 and 1
    results = list(shapes(cloud_int, mask=None, transform=transform))
    
    # Create list of geometries and attributes
    geometries = []
    cloud_types = []
    
    for geom, value in results:
        geometries.append(shape(geom))
        cloud_types.append(int(value))
    
    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame({
        'cloud_type': cloud_types,
        'description': ['Clear' if ct == 0 else 'Cloudy' if ct == 1 else 'Missing' 
                       for ct in cloud_types]
    }, geometry=geometries, crs='EPSG:4326')
    
    # Save as shapefile
    gdf.to_file(output_shp)
    print(f"  Saved Shapefile: {output_shp}")
    print(f"  Total polygons: {len(gdf)}")
    print(f"  Cloud type distribution:\n{gdf['description'].value_counts()}")

print("\n=== Processing Complete ===")
print(f"GeoTIFF files saved in: geotiff_output/")
print(f"Shapefiles saved in: shapefile_output/")