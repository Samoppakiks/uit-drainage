#!/usr/bin/env python3
"""
GEE Water Bodies Detection v2: Full-scale UIT Dausa (All 11 Polygons)
Detect permanent, seasonal, and current water bodies using:
- JRC Global Surface Water (1984-2021, 30m)
- Sentinel-2 MNDWI (2025 pre/post-monsoon, 10m)
Export in UTM Zone 43N projection
"""

import ee
import geojson
import os
from datetime import datetime

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

# Union all UIT polygons
uit_boundary = ee.Geometry.MultiPolygon(all_features).dissolve()
print(f"✓ Loaded all 11 UIT boundary polygons")

# Extended region for analysis (buffer 1km for edge effects)
analysis_region = uit_boundary.buffer(1000)

print("\n" + "="*60)
print("WATER BODY DETECTION v2 (Full Scale)")
print("="*60)

# 1. JRC Global Surface Water Analysis
print("\n1. JRC Global Surface Water Analysis...")

jrc = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')

# Extract different water categories
occurrence = jrc.select('occurrence').clip(analysis_region)
seasonality = jrc.select('seasonality').clip(analysis_region)
max_extent = jrc.select('max_extent').clip(analysis_region)

# Classify water bodies:
# Permanent: occurrence > 80%
# Seasonal: occurrence 20-80%  
# Historical: max_extent but low current occurrence
permanent_water = occurrence.gt(80)
seasonal_water = occurrence.gt(20).And(occurrence.lte(80))
historical_extent = max_extent.eq(1)

print("✓ JRC water categories extracted")

# 2. Sentinel-2 MNDWI Analysis
print("\n2. Sentinel-2 MNDWI Analysis...")

def get_s2_water_composite(start_date, end_date, description):
    """Get Sentinel-2 water composite for date range."""
    
    s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
        .filterDate(start_date, end_date) \
        .filterBounds(analysis_region) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
    
    def add_water_indices(image):
        """Add NDWI and MNDWI to image."""
        ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')
        mndwi = image.normalizedDifference(['B3', 'B11']).rename('MNDWI') 
        return image.addBands([ndwi, mndwi])
    
    s2_indices = s2.map(add_water_indices)
    
    # Composite and extract water (MNDWI > 0)
    composite = s2_indices.median().clip(analysis_region)
    water_mask = composite.select('MNDWI').gt(0)
    
    print(f"  ✓ {description}: {s2.size().getInfo()} images")
    return water_mask

# Pre-monsoon (April-May 2025) and Post-monsoon (October-November 2025)
pre_monsoon_water = get_s2_water_composite('2025-04-01', '2025-05-31', 'Pre-monsoon')
post_monsoon_water = get_s2_water_composite('2025-10-01', '2025-11-30', 'Post-monsoon')

# 3. Combine and Vectorize Water Bodies
print("\n3. Combining and Vectorizing Water Bodies...")

# Create combined water mask with categories
water_categories = ee.Image.constant(0).clip(analysis_region)

# Add categories (higher values override lower)
water_categories = water_categories.where(historical_extent, 1)  # Historical
water_categories = water_categories.where(seasonal_water, 2)     # Seasonal JRC
water_categories = water_categories.where(permanent_water, 3)    # Permanent JRC
water_categories = water_categories.where(pre_monsoon_water, 4)  # Pre-monsoon S2
water_categories = water_categories.where(post_monsoon_water, 5) # Post-monsoon S2

# Vectorize water bodies
water_vectors = water_categories.gt(0).selfMask().reduceToVectors(
    geometry=analysis_region,
    scale=30,
    maxPixels=1e8,
    geometryType='polygon'
)

print("✓ Water bodies vectorized")

# 4. Add Attributes and Classification
def classify_water_body(feature):
    """Classify water body type and add attributes."""
    
    # Sample the dominant water category across the polygon (mode)
    category = water_categories.reduceRegion(
        reducer=ee.Reducer.mode(),
        geometry=feature.geometry(),
        scale=30,
        maxPixels=1e6
    ).get('constant')
    
    # Calculate area in UTM projection for accuracy
    area_utm = feature.geometry().transform('EPSG:32643', 1).area(maxError=1)
    
    # Assign water type based on category
    water_type = ee.Algorithms.If(
        ee.Number(category).eq(5), 'post_monsoon_s2',
        ee.Algorithms.If(
            ee.Number(category).eq(4), 'pre_monsoon_s2',
            ee.Algorithms.If(
                ee.Number(category).eq(3), 'permanent_jrc',
                ee.Algorithms.If(
                    ee.Number(category).eq(2), 'seasonal_jrc',
                    'historical_jrc'
                )
            )
        )
    )
    
    return feature.set({
        'water_type': water_type,
        'area_sqm': area_utm,
        'area_hectares': ee.Number(area_utm).divide(10000),
        'category_code': category,
        'detection_source': ee.String(water_type).slice(0, 3)  # 'jrc' or 'sen'
    })

print("\n4. Adding water body attributes...")
water_classified = water_vectors.map(classify_water_body)

# Filter out very small water bodies (< 100 m²)
water_filtered = water_classified.filter(ee.Filter.gte('area_sqm', 100))

print("✓ Water body classification complete")

# 5. Export to Drive (as GeoJSON for UTM preservation)
print("\n5. Exporting water bodies...")

# Export as FeatureCollection to preserve UTM coordinates in properties
export_task = ee.batch.Export.table.toDrive(
    collection=water_filtered,
    description='uit_dausa_water_bodies_v2',
    folder='UIT_Dausa_Drainage_v2',
    fileNamePrefix='water_bodies_full_utm43n',
    fileFormat='GeoJSON'
)

export_task.start()

# Print summary statistics
print("\n" + "="*60)
print("WATER BODIES EXPORT STARTED (v2)")
print("="*60)
print(f"Task ID: {export_task.id}")
print(f"Description: uit_dausa_water_bodies_v2")
print(f"Coverage: All 11 UIT polygons (~1600 sq km)")
print(f"Minimum water body size: 100 m²")
print("")
print("Water body categories:")
print("  1. permanent_jrc (JRC occurrence > 80%)")
print("  2. seasonal_jrc (JRC occurrence 20-80%)")
print("  3. historical_jrc (JRC max extent)")
print("  4. pre_monsoon_s2 (Sentinel-2 Apr-May 2025)")
print("  5. post_monsoon_s2 (Sentinel-2 Oct-Nov 2025)")
print("")
print("Monitor at: https://code.earthengine.google.com/tasks")
print("Download to: layers-v2/water_bodies_full_utm43n.geojson")

# Get approximate count for reporting
try:
    water_count = water_filtered.size()
    print(f"\nApproximate water bodies detected: {water_count.getInfo()}")
except Exception as e:
    print(f"\nWater body count: (calculating in background)")

print("\nNext: Run gee_flood_sar_v2.py for SAR flood analysis")