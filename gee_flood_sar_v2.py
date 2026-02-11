#!/usr/bin/env python3
"""
GEE SAR Flood Detection v2: Full-scale UIT Dausa (All 11 Polygons)
Compare dry season vs monsoon Sentinel-1 SAR backscatter
to identify flood-prone areas across entire 1600 sq km region
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
    exit(1)

# Load all 11 UIT boundary polygons
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOUNDARY_FILE = os.path.join(BASE_DIR, 'boundaries.geojson')

with open(BOUNDARY_FILE) as f:
    boundary_data = geojson.load(f)

# Create combined geometry for all 11 UIT polygons
all_features = []
for feature in boundary_data['features']:
    coords = feature['geometry']['coordinates']
    if feature['geometry']['type'] == 'MultiPolygon':
        for poly in coords:
            all_features.append(ee.Geometry.Polygon(poly))
    else:
        all_features.append(ee.Geometry.Polygon(coords))

# Union all UIT polygons with buffer for edge effects
uit_boundary = ee.Geometry.MultiPolygon(all_features).dissolve()
analysis_region = uit_boundary.buffer(500)

print(f"✓ Loaded all 11 UIT boundary polygons")

print("\n" + "="*60)
print("SAR FLOOD ANALYSIS v2 (Full Scale)")
print("="*60)

# Sentinel-1 SAR preprocessing function
def preprocess_s1(image):
    """Preprocess Sentinel-1 image."""
    # Convert to dB and mask edges
    db = ee.Image(10).multiply(image.select('VH').log10()).rename('VH_dB')
    mask = image.select('VH').gt(0.001)  # Remove very low values
    return db.updateMask(mask)

# 1. Dry Season Composite (January-March 2025)
print("\n1. Processing dry season SAR (Jan-Mar 2025)...")

dry_season = ee.ImageCollection('COPERNICUS/S1_GRD') \
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH')) \
    .filter(ee.Filter.eq('instrumentMode', 'IW')) \
    .filterDate('2025-01-01', '2025-03-31') \
    .filterBounds(analysis_region) \
    .map(preprocess_s1)

dry_composite = dry_season.median().clip(analysis_region)
dry_count = dry_season.size()

print(f"  ✓ Dry season: {dry_count.getInfo()} images")

# 2. Monsoon Season Composite (July-September)
# Try 2025 first, fall back to 2024 if no data available yet
print("\n2. Processing monsoon season SAR...")

monsoon_season_2025 = ee.ImageCollection('COPERNICUS/S1_GRD') \
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH')) \
    .filter(ee.Filter.eq('instrumentMode', 'IW')) \
    .filterDate('2025-07-01', '2025-09-30') \
    .filterBounds(analysis_region)

monsoon_count_2025 = monsoon_season_2025.size().getInfo()

if monsoon_count_2025 > 0:
    monsoon_year = 2025
    monsoon_season = monsoon_season_2025.map(preprocess_s1)
    print(f"  ✓ Using 2025 monsoon: {monsoon_count_2025} images")
else:
    monsoon_year = 2024
    print("  ! No 2025 monsoon data yet, falling back to 2024...")
    monsoon_season = ee.ImageCollection('COPERNICUS/S1_GRD') \
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH')) \
        .filter(ee.Filter.eq('instrumentMode', 'IW')) \
        .filterDate('2024-07-01', '2024-09-30') \
        .filterBounds(analysis_region) \
        .map(preprocess_s1)
    print(f"  ✓ Using 2024 monsoon: {monsoon_season.size().getInfo()} images")

monsoon_composite = monsoon_season.median().clip(analysis_region)
monsoon_count = monsoon_season.size()

# 3. Calculate Backscatter Difference
print("\n3. Calculating flood extent...")

# Flood detection: areas where backscatter drops >3dB during monsoon
backscatter_diff = dry_composite.subtract(monsoon_composite)
flood_mask = backscatter_diff.gt(3.0)  # 3dB drop indicates flooding

# Additional filters:
# - Remove very steep slopes (>10°) where flooding is unlikely
# - Remove areas with very high dry-season backscatter (buildings)
slope = ee.Terrain.slope(ee.ImageCollection('COPERNICUS/DEM/GLO30').mosaic().select('DEM'))
steep_areas = slope.gt(10)
high_backscatter = dry_composite.gt(-5)  # Buildings typically > -5 dB

# Refined flood mask
flood_refined = flood_mask.And(steep_areas.Not()).And(high_backscatter.Not())

print("✓ Flood extent calculated with terrain filters")

# 4. Vectorize Flood Areas
print("\n4. Vectorizing flood-prone areas...")

# Group connected flood pixels and vectorize
flood_vectors = flood_refined.selfMask().reduceToVectors(
    geometry=analysis_region,
    scale=20,  # 20m for balance between detail and processing time
    maxPixels=1e8,
    geometryType='polygon'
)

# Add attributes to flood polygons
def add_flood_attributes(feature):
    """Add area and flood intensity attributes."""
    
    # Calculate area in UTM for accuracy
    area_utm = feature.geometry().transform('EPSG:32643', 1).area(maxError=1)
    
    # Sample backscatter difference at centroid
    centroid = feature.geometry().centroid(maxError=100)
    diff_sample = backscatter_diff.sample(centroid, 20).first()
    flood_intensity = diff_sample.get('VH_dB')
    
    return feature.set({
        'area_sqm': area_utm,
        'area_hectares': ee.Number(area_utm).divide(10000),
        'flood_intensity_db': flood_intensity,
        'flood_category': ee.Algorithms.If(
            ee.Number(flood_intensity).gt(6), 'high',
            ee.Algorithms.If(
                ee.Number(flood_intensity).gt(4), 'moderate',
                'low'
            )
        ),
        'detection_year': monsoon_year,
        'data_source': 'Sentinel-1_VH'
    })

flood_classified = flood_vectors.map(add_flood_attributes)

# Filter out very small flood areas (< 1000 m²)
flood_filtered = flood_classified.filter(ee.Filter.gte('area_sqm', 1000))

print("✓ Flood areas classified and filtered")

# 5. Export Results
print("\n5. Exporting flood analysis...")

# Export flood polygons
flood_export = ee.batch.Export.table.toDrive(
    collection=flood_filtered,
    description='uit_dausa_sar_flood_v2',
    folder='UIT_Dausa_Drainage_v2',
    fileNamePrefix='sar_flood_full_utm43n',
    fileFormat='GeoJSON'
)

flood_export.start()

# Also export backscatter difference raster for analysis
diff_export = ee.batch.Export.image.toDrive(
    image=backscatter_diff.select('VH_dB'),
    description='uit_dausa_backscatter_diff_v2',
    folder='UIT_Dausa_Drainage_v2',
    fileNamePrefix='backscatter_difference',
    scale=20,
    region=analysis_region,
    maxPixels=int(1e9),
    crs='EPSG:32643',
    fileFormat='GeoTIFF'
)

diff_export.start()

# Print summary
print("\n" + "="*60)
print("SAR FLOOD ANALYSIS EXPORT STARTED (v2)")
print("="*60)
print(f"Flood polygons task ID: {flood_export.id}")
print(f"Backscatter raster task ID: {diff_export.id}")
print("")
print("Analysis parameters:")
print(f"  Dry season: Jan-Mar 2025 ({dry_count.getInfo()} images)")
print(f"  Monsoon season: Jul-Sep {monsoon_year} ({monsoon_count.getInfo()} images)")
print("  Flood threshold: >3dB backscatter decrease")
print("  Minimum area: 1000 m² (0.1 hectare)")
print("  Excluded: steep slopes (>10°) and buildings")
print("")
print("Monitor at: https://code.earthengine.google.com/tasks")
print("Download to: layers-v2/sar_flood_full_utm43n.geojson")

# Get approximate statistics
try:
    flood_count = flood_filtered.size()
    total_area = flood_filtered.aggregate_sum('area_hectares')
    print(f"\nFlood-prone areas detected: {flood_count.getInfo()}")
    print(f"Total flood-prone area: {total_area.getInfo():.1f} hectares")
except Exception as e:
    print("\nFlood statistics: (calculating in background)")

print("\nNext: Run gee_hydrosheds_v2.py for reference network")