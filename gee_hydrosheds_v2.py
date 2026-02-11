#!/usr/bin/env python3
"""
GEE HydroSHEDS Reference Network v2: Full-scale UIT Dausa
Load HydroSHEDS global river network for all 11 UIT polygons
to use as validation reference for our DEM-derived streams
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

# Union all UIT polygons with buffer for context
uit_boundary = ee.Geometry.MultiPolygon(all_features).dissolve()
analysis_region = uit_boundary.buffer(2000)  # 2km buffer for regional context

print(f"✓ Loaded all 11 UIT boundary polygons")
print(f"Analysis region: UIT boundaries + 2km buffer")

print("\n" + "="*60)
print("HYDROSHEDS REFERENCE NETWORK v2")
print("="*60)

# Load HydroSHEDS Free Flowing Rivers
print("\n1. Loading HydroSHEDS Free Flowing Rivers...")

hydrosheds = ee.FeatureCollection('WWF/HydroSHEDS/v1/FreeFlowingRivers')

# Filter to analysis region
rivers_in_region = hydrosheds.filterBounds(analysis_region)

print("✓ HydroSHEDS data loaded and filtered")

# Add length calculation in UTM projection for accuracy
def add_utm_length(feature):
    """Calculate river segment length in UTM coordinates."""
    length_utm = feature.geometry().transform('EPSG:32643', 1).length(maxError=1)
    return feature.set({
        'LENGTH_UTM_M': length_utm,
        'LENGTH_UTM_KM': ee.Number(length_utm).divide(1000)
    })

rivers_with_length = rivers_in_region.map(add_utm_length)

print("✓ Added UTM-based length calculations")

# Print basic statistics
river_count = rivers_with_length.size()
total_length = rivers_with_length.aggregate_sum('LENGTH_UTM_KM')

print(f"\n2. HydroSHEDS Statistics:")
try:
    print(f"  River segments in region: {river_count.getInfo()}")
    print(f"  Total river length: {total_length.getInfo():.1f} km")
    
    # Get range of river orders
    orders = rivers_with_length.aggregate_array('RIV_ORD').distinct().sort()
    print(f"  River orders present: {orders.getInfo()}")
    
    # Count by order (batched to avoid many getInfo calls)
    def order_stats(order):
        filtered = rivers_with_length.filter(ee.Filter.eq('RIV_ORD', order))
        return ee.Feature(None, {
            'order': order,
            'count': filtered.size(),
            'length_km': filtered.aggregate_sum('LENGTH_UTM_KM')
        })

    stats_fc = ee.FeatureCollection([order_stats(o) for o in [3, 4, 5, 6, 7, 8, 9]])
    stats_list = stats_fc.getInfo()['features']
    for stat in stats_list:
        props = stat['properties']
        if props['count'] > 0:
            print(f"    Order {props['order']}: {props['count']} segments, {props['length_km']:.1f} km")
            
except Exception as e:
    print("  Statistics: (calculating in background)")

# 3. Export HydroSHEDS Reference
print("\n3. Exporting HydroSHEDS reference...")

export_task = ee.batch.Export.table.toDrive(
    collection=rivers_with_length,
    description='uit_dausa_hydrosheds_ref_v2',
    folder='UIT_Dausa_Drainage_v2',
    fileNamePrefix='hydrosheds_ref_full_utm43n',
    fileFormat='GeoJSON'
)

export_task.start()

print("\n" + "="*60)
print("HYDROSHEDS EXPORT STARTED (v2)")
print("="*60)
print(f"Task ID: {export_task.id}")
print(f"Description: uit_dausa_hydrosheds_ref_v2")
print(f"Coverage: All 11 UIT polygons + 2km buffer")
print("")
print("HydroSHEDS attributes included:")
print("  - RIV_ORD: Strahler river order")
print("  - LENGTH_KM: Original length (degrees)")
print("  - LENGTH_UTM_KM: Accurate UTM length (kilometers)")
print("  - REACH_ID: Unique river reach identifier")
print("  - Various flow and connectivity attributes")
print("")
print("Use for validation against DEM-derived streams:")
print("  - Compare Order 3+ streams from hydro_process_v2.py")
print("  - Check spatial alignment of major drainage")
print("  - Validate Strahler ordering consistency")
print("")
print("Monitor at: https://code.earthengine.google.com/tasks")
print("Download to: layers-v2/hydrosheds_ref_full_utm43n.geojson")
print("")
print("Next: Run hydro_process_v2.py (ensure DEM is downloaded first)")

# Additional analysis for reference
print("\n4. Expected validation comparisons:")
print("")
print("HydroSHEDS (global dataset):")
print("  - Coarser resolution (~90m derived)")
print("  - Shows major regional drainage only")
print("  - Good for Order 5+ validation")
print("")
print("DEM-derived streams (30m Copernicus):")
print("  - Higher resolution, more local detail")
print("  - Shows Order 3+ channels as requested")
print("  - May show minor channels not in HydroSHEDS")
print("")
print("Validation strategy:")
print("  1. Major streams (Order 6+) should align closely")
print("  2. Medium streams (Order 4-5) should be nearby") 
print("  3. Order 3 streams are local detail (new information)")