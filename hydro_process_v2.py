#!/usr/bin/env python3
"""
Hydrological Processing v2: Full-scale UIT Dausa Drainage Analysis
Uses WhiteboxTools for proper depression breaching and flow routing.
Process 1600 sq km DEM with updated client requirements:
1. Stream order minimum 3 (filter out order 1-2)
2. UTM Zone 43N projection (EPSG:32643)
3. Line smoothing to remove DEM artifacts
4. Full coverage of all 11 UIT polygons
"""

import os
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.transform import rowcol
from shapely.geometry import Point, Polygon, LineString, shape
from rasterio.features import shapes as rio_shapes
from scipy import ndimage
import whitebox

print("\n" + "="*70)
print("HYDROLOGICAL PROCESSING v2 (Full Scale — WhiteboxTools)")
print("="*70)
print("Coverage: All 11 UIT polygons (~1600 sq km)")
print("Requirements: Stream Order 3+, UTM 43N, Line Smoothing")
print("="*70)

# Setup directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data-v2')
LAYERS_DIR = os.path.join(BASE_DIR, 'layers-v2')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LAYERS_DIR, exist_ok=True)

# Input DEM file (should be downloaded from GEE export)
DEM_FILE = os.path.join(DATA_DIR, 'dem_full_utm43n.tif')

if not os.path.exists(DEM_FILE):
    print(f"ERROR: DEM file not found: {DEM_FILE}")
    print("Run gee_dem_export_v2.py first and download the exported DEM")
    exit(1)

print(f"DEM file found: {DEM_FILE}")

# Load UIT boundaries for context
BOUNDARY_FILE = os.path.join(BASE_DIR, 'boundaries.geojson')
boundaries = gpd.read_file(BOUNDARY_FILE)
if boundaries.crs != 'EPSG:32643':
    boundaries = boundaries.to_crs('EPSG:32643')
    print(f"Boundaries reprojected to UTM 43N")
print(f"Loaded {len(boundaries)} UIT boundary polygons")

# ====================================================================
# 1. PREPROCESS DEM: Fix nodata tag
# ====================================================================
print("\n1. Preprocessing DEM (fix nodata)...")

DEM_FIXED = os.path.join(DATA_DIR, 'dem_full_utm43n_fixed.tif')
with rasterio.open(DEM_FILE) as src:
    profile = src.profile.copy()
    data = src.read(1)
    dem_crs = src.crs
    dem_transform = src.transform
    dem_bounds = src.bounds

NODATA_VAL = -9999.0
nan_count = np.isnan(data).sum()
data[np.isnan(data)] = NODATA_VAL
profile.update(nodata=NODATA_VAL)
with rasterio.open(DEM_FIXED, 'w', **profile) as dst:
    dst.write(data, 1)

valid_data = data[data != NODATA_VAL]
print(f"  DEM shape: {data.shape} ({data.shape[0]*30/1000:.0f} km x {data.shape[1]*30/1000:.0f} km)")
print(f"  Elevation range: {valid_data.min():.1f} to {valid_data.max():.1f} m")
print(f"  NoData cells: {nan_count} ({nan_count/data.size*100:.1f}%)")
print(f"  Resolution: {dem_transform[0]:.1f}m x {-dem_transform[4]:.1f}m")
print(f"  CRS: {dem_crs}")

# ====================================================================
# 2. BREACH DEPRESSIONS (WhiteboxTools priority-flood)
# ====================================================================
print("\n2. Breaching depressions (WhiteboxTools)...")

wbt = whitebox.WhiteboxTools()
wbt.set_verbose_mode(False)

DEM_BREACHED = os.path.join(DATA_DIR, 'dem_breached.tif')
wbt.breach_depressions(DEM_FIXED, DEM_BREACHED)
print("  Depression breaching complete")

# ====================================================================
# 3. D8 FLOW DIRECTION
# ====================================================================
print("\n3. Computing D8 flow direction...")

FDIR_FILE = os.path.join(DATA_DIR, 'flow_dir_wbt.tif')
wbt.d8_pointer(DEM_BREACHED, FDIR_FILE)
print("  D8 flow direction computed")

# ====================================================================
# 4. D8 FLOW ACCUMULATION
# ====================================================================
print("\n4. Computing D8 flow accumulation...")

ACC_FILE = os.path.join(DATA_DIR, 'flow_acc_wbt.tif')
wbt.d8_flow_accumulation(DEM_BREACHED, ACC_FILE, out_type='cells')

with rasterio.open(ACC_FILE) as src:
    acc_data = src.read(1)
max_acc = np.nanmax(acc_data)
print(f"  Max accumulation: {max_acc:.0f} cells")
print(f"  Max catchment: {max_acc * dem_transform[0]**2 / 1e6:.1f} km2")
print(f"  Cells > 1000: {(acc_data > 1000).sum()}")
print(f"  Cells > 10000: {(acc_data > 10000).sum()}")

# ====================================================================
# 5. STREAM EXTRACTION + STRAHLER ORDER
# ====================================================================
print("\n5. Extracting stream network + Strahler ordering...")

STREAM_THRESHOLD = 500  # cells (~0.45 km2 catchment at 30m)
STREAMS_RASTER = os.path.join(DATA_DIR, 'streams_wbt.tif')
STRAHLER_RASTER = os.path.join(DATA_DIR, 'strahler_wbt.tif')
STREAMS_VECTOR = os.path.join(DATA_DIR, 'streams_wbt.shp')

# Extract streams
wbt.extract_streams(ACC_FILE, STREAMS_RASTER, threshold=STREAM_THRESHOLD)

# Compute Strahler stream order
wbt.strahler_stream_order(FDIR_FILE, STREAMS_RASTER, STRAHLER_RASTER)

# Vectorize streams (WhiteboxTools traces flow paths properly)
wbt.raster_streams_to_vector(STREAMS_RASTER, FDIR_FILE, STREAMS_VECTOR)

# Load vectorized streams
streams_gdf = gpd.read_file(STREAMS_VECTOR)
streams_gdf = streams_gdf.set_crs(dem_crs, allow_override=True)

print(f"  Total stream segments: {len(streams_gdf)}")
print(f"  Total stream length: {streams_gdf.geometry.length.sum()/1000:.1f} km")

# Join Strahler order: sample the raster at each stream's midpoint
with rasterio.open(STRAHLER_RASTER) as src:
    strahler_data = src.read(1)
    strahler_transform = src.transform

orders = []
for idx, row in streams_gdf.iterrows():
    coords = list(row.geometry.coords)
    mid = coords[len(coords)//2]
    r, c = rowcol(strahler_transform, mid[0], mid[1])
    if 0 <= r < strahler_data.shape[0] and 0 <= c < strahler_data.shape[1]:
        orders.append(int(strahler_data[r, c]))
    else:
        orders.append(0)

streams_gdf['stream_order'] = orders
streams_gdf['length_m'] = streams_gdf.geometry.length
streams_gdf['stream_id'] = range(len(streams_gdf))

# Print order distribution
order_counts = streams_gdf['stream_order'].value_counts().sort_index()
print(f"\n  Stream order distribution:")
for order, count in order_counts.items():
    length_km = streams_gdf[streams_gdf['stream_order'] == order].geometry.length.sum() / 1000
    print(f"    Order {order}: {count} segments, {length_km:.1f} km")

# ====================================================================
# 6. FILTER TO ORDER 3+ (KEY REQUIREMENT)
# ====================================================================
print("\n6. Applying Order 3+ filter...")

streams_filtered = streams_gdf[streams_gdf['stream_order'] >= 3].copy()
print(f"  Before filter: {len(streams_gdf)} segments")
print(f"  After filter (Order 3+): {len(streams_filtered)} segments")
print(f"  Total Order 3+ length: {streams_filtered.geometry.length.sum()/1000:.1f} km")

# ====================================================================
# 7. LINE SMOOTHING (KEY REQUIREMENT)
# ====================================================================
print("\n7. Applying line smoothing...")

SMOOTH_TOLERANCE = 15.0  # meters (half of 30m DEM resolution)
streams_filtered['geometry'] = streams_filtered['geometry'].simplify(
    SMOOTH_TOLERANCE, preserve_topology=True
)
streams_filtered['length_m_smoothed'] = streams_filtered.geometry.length

avg_reduction = 1 - (streams_filtered['length_m_smoothed'].sum() / streams_filtered['length_m'].sum())
print(f"  Smoothing tolerance: {SMOOTH_TOLERANCE}m")
print(f"  Average length reduction: {avg_reduction*100:.1f}%")

# ====================================================================
# 8. SAVE STREAM NETWORK
# ====================================================================
print("\n8. Saving stream network...")

# Save in UTM 43N
streams_utm_path = os.path.join(LAYERS_DIR, 'streams_order3plus_utm43n.geojson')
streams_filtered.to_file(streams_utm_path, driver='GeoJSON')

# Save in WGS84 for web display
streams_wgs84 = streams_filtered.to_crs('EPSG:4326')
streams_wgs84_path = os.path.join(LAYERS_DIR, 'streams_order3plus_wgs84.geojson')
streams_wgs84.to_file(streams_wgs84_path, driver='GeoJSON')

print(f"  UTM: {streams_utm_path}")
print(f"  WGS84: {streams_wgs84_path}")

# ====================================================================
# 9. WATERSHED DELINEATION
# ====================================================================
print("\n9. Watershed delineation...")

# Use WhiteboxTools watershed delineation
# Pour points = endpoints of Order 4+ streams
pour_points = []
high_order_streams = streams_filtered[streams_filtered['stream_order'] >= 4]

for idx, stream in high_order_streams.iterrows():
    coords = list(stream.geometry.coords)
    if coords:
        end_point = Point(coords[-1])
        pour_points.append({
            'geometry': end_point,
            'stream_id': stream['stream_id'],
            'stream_order': stream['stream_order']
        })

if pour_points:
    pour_gdf = gpd.GeoDataFrame(pour_points, crs=dem_crs)
    pour_shp = os.path.join(DATA_DIR, 'pour_points.shp')
    pour_gdf.to_file(pour_shp)

    # Use WhiteboxTools watershed tool
    watershed_raster = os.path.join(DATA_DIR, 'watersheds_wbt.tif')
    try:
        wbt.watershed(FDIR_FILE, pour_shp, watershed_raster)

        # Vectorize watersheds
        with rasterio.open(watershed_raster) as src:
            ws_data = src.read(1)
            ws_transform = src.transform

        watersheds_list = []
        for geom, value in rio_shapes(ws_data, mask=(ws_data > 0), transform=ws_transform):
            poly = shape(geom)
            if poly.is_valid and poly.area > 100000:  # > 0.1 km2
                watersheds_list.append({
                    'geometry': poly,
                    'watershed_id': int(value),
                    'area_m2': poly.area,
                    'area_km2': poly.area / 1e6
                })

        if watersheds_list:
            watersheds_gdf = gpd.GeoDataFrame(watersheds_list, crs=dem_crs)

            # Save watersheds
            ws_utm_path = os.path.join(LAYERS_DIR, 'watersheds_utm43n.geojson')
            watersheds_gdf.to_file(ws_utm_path, driver='GeoJSON')

            ws_wgs84 = watersheds_gdf.to_crs('EPSG:4326')
            ws_wgs84_path = os.path.join(LAYERS_DIR, 'watersheds_wgs84.geojson')
            ws_wgs84.to_file(ws_wgs84_path, driver='GeoJSON')

            print(f"  {len(watersheds_gdf)} watersheds delineated")
            print(f"  Total watershed area: {watersheds_gdf['area_km2'].sum():.1f} km2")
        else:
            print("  No valid watersheds found")
    except Exception as e:
        print(f"  Watershed delineation failed: {e}")
        print("  Falling back to simple catchment polygons...")

        # Fallback: use rasterio shapes on flow accumulation to get catchment areas
        watersheds_list = []
        for idx, pp in pour_gdf.iterrows():
            x, y = pp.geometry.x, pp.geometry.y
            r, c = rowcol(dem_transform, x, y)
            if 0 <= r < acc_data.shape[0] and 0 <= c < acc_data.shape[1]:
                # Use accumulation-based catchment approximation
                threshold = acc_data[r, c] * 0.5
                catch_mask = (acc_data >= threshold).astype(np.uint8)
                labeled, n = ndimage.label(catch_mask)
                label_at_point = labeled[r, c]
                if label_at_point > 0:
                    single_mask = (labeled == label_at_point).astype(np.uint8)
                    for geom, val in rio_shapes(single_mask, mask=single_mask.astype(bool), transform=dem_transform):
                        poly = shape(geom)
                        if poly.is_valid and poly.area > 100000:
                            watersheds_list.append({
                                'geometry': poly,
                                'watershed_id': idx,
                                'area_m2': poly.area,
                                'area_km2': poly.area / 1e6
                            })

        if watersheds_list:
            watersheds_gdf = gpd.GeoDataFrame(watersheds_list, crs=dem_crs)
            ws_utm_path = os.path.join(LAYERS_DIR, 'watersheds_utm43n.geojson')
            watersheds_gdf.to_file(ws_utm_path, driver='GeoJSON')
            ws_wgs84 = watersheds_gdf.to_crs('EPSG:4326')
            ws_wgs84_path = os.path.join(LAYERS_DIR, 'watersheds_wgs84.geojson')
            ws_wgs84.to_file(ws_wgs84_path, driver='GeoJSON')
            print(f"  {len(watersheds_gdf)} fallback watersheds created")
else:
    print("  No high-order pour points found for watershed delineation")

# ====================================================================
# 10. TOPOGRAPHIC WETNESS INDEX
# ====================================================================
print("\n10. Computing Topographic Wetness Index...")

# Compute slope from breached DEM
with rasterio.open(DEM_BREACHED) as src:
    dem_arr = src.read(1).astype(np.float64)
dem_arr[dem_arr == NODATA_VAL] = np.nan

dy, dx = np.gradient(dem_arr, abs(dem_transform[4]), dem_transform[0])
slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
print(f"  Slope range: {np.nanmin(slope):.2f} to {np.nanmax(slope):.2f} degrees")

# TWI = ln(a / tan(slope))
slope_rad = np.deg2rad(slope)
slope_tan = np.tan(slope_rad)
slope_tan[slope_tan < 0.001] = 0.001

# Use WhiteboxTools accumulation (already in cells, convert to area)
cell_area = dem_transform[0] * abs(dem_transform[4])  # m2
sca = acc_data * cell_area / dem_transform[0]  # specific catchment area (m)

twi = np.log(sca / slope_tan)
twi[np.isnan(dem_arr)] = np.nan

# Save TWI
twi_path = os.path.join(DATA_DIR, 'twi_utm43n.tif')
with rasterio.open(DEM_FIXED) as src:
    twi_profile = src.profile.copy()
twi_profile.update(dtype='float64', nodata=np.nan)
with rasterio.open(twi_path, 'w', **twi_profile) as dst:
    dst.write(twi, 1)

print(f"  TWI range: {np.nanmin(twi):.1f} to {np.nanmax(twi):.1f}")
print(f"  TWI saved: {twi_path}")

# Also save slope for flood risk analysis
slope_path = os.path.join(DATA_DIR, 'slope_utm43n.tif')
with rasterio.open(slope_path, 'w', **twi_profile) as dst:
    dst.write(slope, 1)
print(f"  Slope saved: {slope_path}")

# ====================================================================
# 11. SUMMARY
# ====================================================================
print("\n" + "="*70)
print("PROCESSING COMPLETE - SUMMARY")
print("="*70)

print(f"DEM: {data.shape[0]} x {data.shape[1]} pixels ({data.shape[0]*30/1000:.0f} x {data.shape[1]*30/1000:.0f} km)")
print(f"Max flow accumulation: {max_acc:.0f} cells ({max_acc * cell_area / 1e6:.1f} km2)")
print(f"Total streams: {len(streams_gdf)} segments, {streams_gdf.geometry.length.sum()/1000:.1f} km")
print(f"Order 3+ streams: {len(streams_filtered)} segments, {streams_filtered.geometry.length.sum()/1000:.1f} km")

if 'watersheds_gdf' in locals():
    print(f"Watersheds: {len(watersheds_gdf)} basins, {watersheds_gdf['area_km2'].sum():.1f} km2")

print(f"Projection: UTM Zone 43N (EPSG:32643)")
print(f"Line smoothing: {SMOOTH_TOLERANCE}m tolerance")

print("\nOutput files:")
print(f"  {streams_utm_path}")
print(f"  {streams_wgs84_path}")
if 'ws_utm_path' in locals():
    print(f"  {ws_utm_path}")
    print(f"  {ws_wgs84_path}")
print(f"  {twi_path}")
print(f"  {slope_path}")

print("\nNext steps:")
print("1. Run flood_risk_v2.py for flood risk analysis")
print("2. Run prepare_layers_v2.py to finalize all layers")
print("3. Run app_drainage_v2.py to test updated dashboard")
