import glob
import h5py
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import shape, mapping
import geopandas as gpd
from rasterio.features import shapes
import os
import re

# Create output directories
os.makedirs('geotiff_output', exist_ok=True)
os.makedirs('shapefile_output', exist_ok=True)

def extract_timestamp_scan(filename):
    """Extract timestamp and scan/granule info from filename"""
    # Pattern: TEMPO_{PRODUCT}_L{LEVEL}_V04_{TIMESTAMP}_S{SCAN}G{GRANULE}
    match = re.search(r'(\d{8}T\d{6}Z)_S(\d{3})G(\d{2})', filename)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, None, None

def find_matching_l2_file(l1_file, l2_dir='L2', version="V03"):
    """Find corresponding L2 cloud file for an L1 file"""
    timestamp, scan, granule = extract_timestamp_scan(l1_file)
    if not timestamp:
        return None
    
    # L2 cloud files have format: TEMPO_CLDO4_L2_V04_{TIMESTAMP}_S{SCAN}G{GRANULE}.nc
    # Note: L2 files might not have the -034 suffix that L1 has
    pattern = f"TEMPO_CLDO4_L2_{version}_{timestamp}_S{scan}G{granule.split('-')[0]}.nc"
    l2_path = os.path.join(l2_dir, pattern)
    
    if os.path.exists(l2_path):
        return l2_path
    
    # Try with wildcard if exact match not found
    search_pattern = os.path.join(l2_dir, f"TEMPO_CLDO4_L2_{version}_{timestamp}_S{scan}G*.nc")
    matches = glob.glob(search_pattern)
    return matches[0] if matches else None

input_dir = "/Volumes/EXTERNO-MP/TEMPO_l1"
l2_dir = "../data/raw_l2_v3"
version = "V03"

# Process L1 files
l1_files = glob.glob('/Volumes/EXTERNO-MP/TEMPO_l1/TEMPO_RAD_*.nc')
print(f"Found {len(l1_files)} L1 files to process")

for l1_file in l1_files:
    print(f"\nProcessing L1: {l1_file}")
    
    # Find matching L2 file
    l2_file = find_matching_l2_file(l1_file, l2_dir, version=version)
    if not l2_file:
        print(f"  WARNING: No matching L2 file found, skipping...")
        continue
    
    print(f"  Matched L2: {l2_file}")
    
    # Read RGB data from L1
    with h5py.File(l1_file, 'r') as f:
        red = f['cloud_mask_group']['red'][:]
        green = f['cloud_mask_group']['green'][:]
        blue = f['cloud_mask_group']['blue'][:]
    
    # Read cloud data and geolocation from L2
    with h5py.File(l2_file, 'r') as f:
        # Cloud fraction (0-1 scale, where higher values = more cloudy)
        cloud_fraction = f['product']['cloud_fraction'][:]
                
        # Geolocation from L2
        lat = f['geolocation']['latitude'][:]
        lon = f['geolocation']['longitude'][:]
        
        # Quality flags
        quality_flag = f['support_data']['ground_pixel_quality_flag'][:]
    
    print(f"  Cloud fraction range: {np.nanmin(cloud_fraction):.3f} to {np.nanmax(cloud_fraction):.3f}")
    
    # Clip RGB values exceeding 1.0
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
    cloud_fraction = np.flip(np.transpose(cloud_fraction, (1, 0)), axis=0)
    
    # Get dimensions
    height, width = red.shape
    
    # Define geographic extent from L2 geolocation
    lon_transposed = np.flip(np.transpose(lon, (1, 0)), axis=0)
    lat_transposed = np.flip(np.transpose(lat, (1, 0)), axis=0)
    west = float(np.nanmin(lon_transposed))
    east = float(np.nanmax(lon_transposed))
    south = float(np.nanmin(lat_transposed))
    north = float(np.nanmax(lat_transposed))
    
    # Create affine transform
    transform = from_bounds(west, south, east, north, width, height)
    
    # === Export RGB as GeoTIFF ===
    output_tif = f"geotiff_output/rgb_{os.path.basename(l1_file).replace('.nc', '.tif')}"
    
    # Convert to 8-bit (0-255)
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
        crs='EPSG:4326',
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
    
    # === Export L2 Cloud Mask as Shapefile ===
    output_shp = f"shapefile_output/cloud_l2_{os.path.basename(l2_file).replace('.nc', '.shp')}"
    
    # Create binary cloud mask from cloud fraction
    # You can adjust the threshold (e.g., 0.3 means 30% cloud coverage)
    cloud_threshold = 0.3
    cloud_binary = np.where(cloud_fraction >= cloud_threshold, 1, 0).astype(np.int32)
    
    # Handle NaN/invalid values
    cloud_binary = np.where(np.isnan(cloud_fraction), 2, cloud_binary)
    
    # Extract shapes from the cloud mask
    results = list(shapes(cloud_binary, mask=None, transform=transform))
    
    # Create lists of geometries and attributes
    geometries = []
    cloud_types = []
    cloud_fractions = []
    
    for geom, value in results:
        geometries.append(shape(geom))
        cloud_types.append(int(value))
    
    # Create description labels
    descriptions = []
    for ct in cloud_types:
        if ct == 0:
            descriptions.append('Clear')
        elif ct == 1:
            descriptions.append('Cloudy')
        else:
            descriptions.append('Invalid/Missing')
    
    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame({
        'cloud_type': cloud_types,
        'description': descriptions
    }, geometry=geometries, crs='EPSG:4326')
    
    # Save as shapefile
    gdf.to_file(output_shp)
    print(f"  Saved Shapefile: {output_shp}")
    print(f"  Total polygons: {len(gdf)}")
    print(f"  Cloud type distribution:\n{gdf['description'].value_counts()}")
    print(f"  Cloud threshold used: {cloud_threshold} ({cloud_threshold*100}%)")

print("\n=== Processing Complete ===")
print(f"GeoTIFF files saved in: geotiff_output/")
print(f"Shapefiles saved in: shapefile_output/")