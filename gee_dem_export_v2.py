#!/usr/bin/env python3
"""
GEE DEM Export v2: Full-scale UIT Dausa drainage area
Export Copernicus GLO-30 DEM for all 11 UIT polygons in UTM Zone 43N
Area: ~1600 sq km, Bounding Box: [76.22, 26.82, 76.72, 27.12]
"""

import ee
import geojson
import os

# Initialize Earth Engine
try:
    ee.Initialize(project='gmail-claude-483711')
    print("✓ Earth Engine initialized")
except Exception as e:
    print(f"✗ Earth Engine initialization failed: {e}")
    print("Run: earthengine authenticate")
    exit(1)

# Load UIT boundary polygons
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOUNDARY_FILE = os.path.join(BASE_DIR, 'boundaries.geojson')

print(f"Loading boundaries from: {BOUNDARY_FILE}")
with open(BOUNDARY_FILE) as f:
    boundary_data = geojson.load(f)

# Create bounding box for entire region (covers all 11 UIT polygons)
bbox = ee.Geometry.Rectangle([76.22, 26.82, 76.72, 27.12])
print(f"Processing bounding box: [76.22, 26.82, 76.72, 27.12]")

# Buffer bbox by 500m for watershed context
bbox_buffered = bbox.buffer(500)

# Load Copernicus GLO-30 DEM
dem_collection = ee.ImageCollection('COPERNICUS/DEM/GLO30')
dem = dem_collection.mosaic().select('DEM')

print("✓ Loaded Copernicus GLO-30 DEM")

# Clip to buffered region
dem_clipped = dem.clip(bbox_buffered)

# Reproject to UTM Zone 43N (EPSG:32643) - required for client
dem_utm = dem_clipped.reproject(
    crs='EPSG:32643',
    scale=30
)

print("✓ Reprojected to UTM Zone 43N (EPSG:32643)")

# Calculate approximate output size
region_info = bbox.getInfo()
coords = region_info['coordinates'][0]
width_deg = abs(coords[2][0] - coords[0][0])  # ~0.5 degrees
height_deg = abs(coords[2][1] - coords[0][1])  # ~0.3 degrees

# At 30m resolution in UTM:
width_pixels = int(width_deg * 111000 / 30)  # ~1850 pixels
height_pixels = int(height_deg * 111000 / 30)  # ~1100 pixels
total_pixels = width_pixels * height_pixels

print(f"Expected output size: {width_pixels} x {height_pixels} pixels ({total_pixels/1e6:.1f}M pixels)")
print(f"Estimated file size: ~{total_pixels * 4 / 1e6:.1f} MB")

# Export to Google Drive
export_task = ee.batch.Export.image.toDrive(
    image=dem_utm,
    description='uit_dausa_dem_full_utm43n_v2',
    folder='UIT_Dausa_Drainage_v2',
    fileNamePrefix='dem_full_utm43n',
    scale=30,
    region=bbox_buffered,
    maxPixels=int(1e9),
    crs='EPSG:32643',
    fileFormat='GeoTIFF'
)

export_task.start()

print("\n" + "="*60)
print("DEM EXPORT STARTED (v2 - Full Scale)")
print("="*60)
print(f"Task ID: {export_task.id}")
print(f"Description: uit_dausa_dem_full_utm43n_v2")
print(f"Projection: UTM Zone 43N (EPSG:32643)")
print(f"Resolution: 30m")
print(f"Coverage: ~1600 sq km (all 11 UIT polygons)")
print(f"Expected size: ~{total_pixels * 4 / 1e6:.1f} MB")
print("")
print("Monitor progress at: https://code.earthengine.google.com/tasks")
print("Download from Google Drive when complete.")
print("")
print("Next steps:")
print("1. Wait for export to complete (30-60 minutes)")
print("2. Download from Google Drive to data-v2/dem_full_utm43n.tif")
print("3. Run hydro_process_v2.py for full-scale hydrological analysis")

# Also print export region for reference
print(f"\nExport region (WGS84): {bbox.getInfo()}")
print(f"Buffered region for watershed context: {bbox_buffered.getInfo()}")