#!/usr/bin/env python3
"""
Flood Risk Analysis v2: Full-scale UIT Dausa
Combine TWI, depressions, and SAR flood history to create
composite flood risk map for all 11 UIT polygons
"""

import os
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.features import shapes
from shapely.geometry import shape, Polygon

print("\n" + "="*70)
print("FLOOD RISK ANALYSIS v2 (Full Scale)")
print("="*70)

# Setup directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data-v2')
LAYERS_DIR = os.path.join(BASE_DIR, 'layers-v2')

# Required input files
TWI_FILE = os.path.join(DATA_DIR, 'twi_utm43n.tif')
DEM_FILE = os.path.join(DATA_DIR, 'dem_filled_utm43n.tif')

# Check required inputs
required_files = [TWI_FILE, DEM_FILE]
missing_files = [f for f in required_files if not os.path.exists(f)]

if missing_files:
    print("✗ Missing required files:")
    for f in missing_files:
        print(f"  {f}")
    print("Run hydro_process_v2.py first to generate TWI and filled DEM")
    exit(1)

print("✓ All required files found")

# 1. LOAD TWI AND DEM
print("\n1. Loading TWI and DEM data...")

with rasterio.open(TWI_FILE) as twi_src:
    twi = twi_src.read(1)
    twi_transform = twi_src.transform
    twi_crs = twi_src.crs
    twi_bounds = twi_src.bounds

with rasterio.open(DEM_FILE) as dem_src:
    dem = dem_src.read(1)
    dem_transform = dem_src.transform

print(f"✓ TWI loaded: {twi.shape} pixels")
print(f"  TWI range: {np.nanmin(twi):.1f} to {np.nanmax(twi):.1f}")

print(f"✓ DEM loaded: {dem.shape} pixels")
print(f"  Elevation range: {np.nanmin(dem):.1f} to {np.nanmax(dem):.1f} m")

# 2. CALCULATE SLOPE
print("\n2. Calculating slope...")

# Calculate slope using numpy gradients
dy, dx = np.gradient(dem, 30, 30)  # 30m pixel size
slope = np.arctan(np.sqrt(dx**2 + dy**2))
slope_degrees = np.rad2deg(slope)

print(f"✓ Slope calculated")
print(f"  Slope range: {np.nanmin(slope_degrees):.1f}° to {np.nanmax(slope_degrees):.1f}°")

# 3. IDENTIFY DEPRESSIONS AND LOW-LYING AREAS
print("\n3. Identifying depressions and low-lying areas...")

# Low-lying areas (bottom 10% of elevation)
elevation_threshold = np.nanpercentile(dem[~np.isnan(dem)], 10)
low_areas = dem <= elevation_threshold

# Very flat areas (slope < 1 degree)
flat_areas = slope_degrees < 1.0

# Potential ponding zones (combination of low elevation and flat slope)
ponding_zones = low_areas & flat_areas

print(f"✓ Topographic analysis complete")
print(f"  Low elevation threshold: {elevation_threshold:.1f} m")
print(f"  Low-lying area: {np.sum(low_areas) * 0.0009:.1f} km²")
print(f"  Flat areas (<1°): {np.sum(flat_areas) * 0.0009:.1f} km²")
print(f"  Ponding zones: {np.sum(ponding_zones) * 0.0009:.1f} km²")

# 4. TWI-BASED WETNESS CLASSIFICATION
print("\n4. TWI-based wetness classification...")

# Remove infinite and NaN values from TWI
twi_clean = twi.copy()
twi_clean[~np.isfinite(twi_clean)] = np.nan

# Define TWI thresholds based on distribution
valid_twi = twi_clean[~np.isnan(twi_clean)]
twi_low = np.percentile(valid_twi, 75)    # Top 25% = wet areas
twi_high = np.percentile(valid_twi, 90)   # Top 10% = very wet areas

print(f"TWI thresholds: Low={twi_low:.1f}, High={twi_high:.1f}")

# Create TWI risk zones
twi_risk = np.zeros_like(twi_clean, dtype=np.int8)
twi_risk[twi_clean >= twi_low] = 1   # Medium risk
twi_risk[twi_clean >= twi_high] = 2  # High risk

print(f"✓ TWI risk zones created:")
print(f"  Low risk: {np.sum(twi_risk == 0) * 0.0009:.1f} km²")
print(f"  Medium risk: {np.sum(twi_risk == 1) * 0.0009:.1f} km²")
print(f"  High risk: {np.sum(twi_risk == 2) * 0.0009:.1f} km²")

# 5. LOAD SAR FLOOD DATA (if available)
print("\n5. Loading SAR flood data...")

sar_flood_file = os.path.join(LAYERS_DIR, 'sar_flood_full_utm43n.geojson')
sar_risk_raster = np.zeros_like(twi, dtype=np.float32)

if os.path.exists(sar_flood_file):
    try:
        sar_floods = gpd.read_file(sar_flood_file)
        
        if not sar_floods.empty:
            print(f"✓ SAR flood data loaded: {len(sar_floods)} flood areas")
            
            # Rasterize SAR flood areas
            from rasterio.features import rasterize
            
            flood_shapes = [(geom, 1.0) for geom in sar_floods.geometry]
            sar_risk_raster = rasterize(
                flood_shapes,
                out_shape=twi.shape,
                transform=twi_transform,
                fill=0.0,
                dtype=np.float32
            )
            
            print(f"  SAR flood area: {np.sum(sar_risk_raster > 0) * 0.0009:.1f} km²")
        else:
            print("⚠ SAR flood data is empty")
    
    except Exception as e:
        print(f"⚠ Could not load SAR data: {e}")
        
else:
    print("⚠ SAR flood data not found (optional)")

# 6. COMPOSITE FLOOD RISK CALCULATION
print("\n6. Creating composite flood risk map...")

# Normalize all risk factors to 0-1 scale
def normalize_raster(raster):
    """Normalize raster to 0-1 scale."""
    valid_data = raster[~np.isnan(raster) & np.isfinite(raster)]
    if len(valid_data) == 0:
        return np.zeros_like(raster)
    
    min_val, max_val = np.min(valid_data), np.max(valid_data)
    if max_val == min_val:
        return np.zeros_like(raster)
    
    normalized = (raster - min_val) / (max_val - min_val)
    normalized = np.clip(normalized, 0, 1)
    return normalized

# Normalize individual risk factors
twi_norm = normalize_raster(twi_clean)
ponding_norm = ponding_zones.astype(np.float32)
sar_norm = normalize_raster(sar_risk_raster)

# Weighted composite risk
# Weights: TWI (40%), Ponding zones (30%), SAR history (30%)
weights = [0.4, 0.3, 0.3]

composite_risk = (
    weights[0] * twi_norm +
    weights[1] * ponding_norm +
    weights[2] * sar_norm
)

# Set invalid areas to NaN
composite_risk[np.isnan(twi)] = np.nan

print(f"✓ Composite risk calculated with weights: TWI({weights[0]:.0%}), Ponding({weights[1]:.0%}), SAR({weights[2]:.0%})")

# 7. CLASSIFY COMPOSITE RISK
print("\n7. Classifying flood risk levels...")

# Define risk level thresholds
valid_risk = composite_risk[~np.isnan(composite_risk)]
risk_low = np.percentile(valid_risk, 70)    # Bottom 70% = low risk
risk_medium = np.percentile(valid_risk, 85) # 70-85% = medium risk
                                           # Top 15% = high risk

flood_risk_classified = np.zeros_like(composite_risk, dtype=np.int8)
flood_risk_classified[composite_risk >= risk_low] = 1      # Medium risk
flood_risk_classified[composite_risk >= risk_medium] = 2   # High risk

# Set NaN areas to -1
flood_risk_classified[np.isnan(composite_risk)] = -1

print(f"Risk thresholds: Low={risk_low:.2f}, Medium={risk_medium:.2f}")

risk_areas = {
    'low': np.sum(flood_risk_classified == 0) * 0.0009,
    'medium': np.sum(flood_risk_classified == 1) * 0.0009,
    'high': np.sum(flood_risk_classified == 2) * 0.0009
}

print(f"✓ Flood risk areas:")
for level, area in risk_areas.items():
    print(f"  {level.capitalize()}: {area:.1f} km²")

# 8. VECTORIZE RISK ZONES
print("\n8. Vectorizing flood risk zones...")

risk_polygons = []

for risk_level in [2, 1]:  # High, Medium only (skip low to avoid massive polygon count)
    mask = (flood_risk_classified == risk_level)
    
    if np.sum(mask) > 0:
        # Convert raster to polygons
        polygon_shapes = shapes(mask.astype(np.uint8), mask=mask, transform=twi_transform)
        
        for geom, value in polygon_shapes:
            if value == 1:  # Only include risk areas
                polygon = shape(geom)
                
                # Filter out very small polygons (< 0.1 hectare)
                if polygon.area > 1000:  # 1000 m² = 0.1 hectare
                    
                    risk_label = {2: 'high', 1: 'medium', 0: 'low'}[risk_level]
                    
                    risk_polygons.append({
                        'geometry': polygon,
                        'risk_level': risk_level,
                        'risk_label': risk_label,
                        'area_m2': polygon.area,
                        'area_hectares': polygon.area / 10000,
                        'twi_contribution': weights[0],
                        'ponding_contribution': weights[1],
                        'sar_contribution': weights[2]
                    })

if risk_polygons:
    flood_risk_gdf = gpd.GeoDataFrame(risk_polygons, crs=twi_crs)
    
    print(f"✓ {len(flood_risk_gdf)} flood risk polygons created")
    
    # Summary by risk level
    summary = flood_risk_gdf.groupby('risk_label').agg({
        'area_hectares': ['count', 'sum']
    }).round(1)
    print("Risk level summary:")
    print(summary)
    
    # 9. SAVE FLOOD RISK LAYERS
    print("\n9. Saving flood risk layers...")
    
    # Save in UTM 43N
    flood_risk_utm_path = os.path.join(LAYERS_DIR, 'flood_risk_utm43n.geojson')
    flood_risk_gdf.to_file(flood_risk_utm_path, driver='GeoJSON')
    
    # Save in WGS84 for web display
    flood_risk_wgs84 = flood_risk_gdf.to_crs('EPSG:4326')
    flood_risk_wgs84_path = os.path.join(LAYERS_DIR, 'flood_risk_wgs84.geojson')
    flood_risk_wgs84.to_file(flood_risk_wgs84_path, driver='GeoJSON')
    
    print(f"✓ UTM flood risk saved: {flood_risk_utm_path}")
    print(f"✓ WGS84 flood risk saved: {flood_risk_wgs84_path}")
    
else:
    print("⚠ No significant flood risk areas found")

# 10. SAVE RASTER OUTPUTS
print("\n10. Saving raster outputs...")

# Save composite risk raster
composite_risk_path = os.path.join(DATA_DIR, 'composite_flood_risk_utm43n.tif')

with rasterio.open(
    composite_risk_path, 'w',
    driver='GTiff',
    height=composite_risk.shape[0],
    width=composite_risk.shape[1],
    count=1,
    dtype=composite_risk.dtype,
    crs=twi_crs,
    transform=twi_transform,
    compress='lzw'
) as dst:
    dst.write(composite_risk, 1)

print(f"✓ Composite risk raster saved: {composite_risk_path}")

# 11. SUMMARY
print("\n" + "="*70)
print("FLOOD RISK ANALYSIS COMPLETE")
print("="*70)

print(f"✓ Coverage: ~{twi.shape[0] * twi.shape[1] * 0.0009:.1f} km²")
print(f"✓ Risk factors: TWI + Topographic depressions + SAR flood history")
print(f"✓ Weighting: TWI({weights[0]:.0%}), Ponding({weights[1]:.0%}), SAR({weights[2]:.0%})")

if 'flood_risk_gdf' in locals():
    total_risk_area = flood_risk_gdf['area_hectares'].sum()
    high_risk_area = flood_risk_gdf[flood_risk_gdf['risk_label'] == 'high']['area_hectares'].sum()
    print(f"✓ Total flood-prone area: {total_risk_area:.1f} hectares")
    print(f"✓ High-risk area: {high_risk_area:.1f} hectares ({high_risk_area/total_risk_area*100:.1f}%)")

print("\nOutput files:")
if 'flood_risk_utm_path' in locals():
    print(f"  {flood_risk_utm_path}")
    print(f"  {flood_risk_wgs84_path}")
print(f"  {composite_risk_path}")

print("\nNext: Run prepare_layers_v2.py to finalize all outputs")