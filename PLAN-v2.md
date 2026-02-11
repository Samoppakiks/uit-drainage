# UIT Dausa Drainage Master Plan v2 - Full Scale Implementation

**Project**: Full-Scale DEM-based Drainage Master Plan for All 11 UIT Polygons
**Client**: Devendra (DM Dausa, UIT Chairman)
**Coverage**: ~1,600 sq km total (ALL 11 UIT boundary polygons)
**Bounding Box**: [76.22, 26.82, 76.72, 27.12] (WGS84)
**Projection**: UTM Zone 43N (EPSG:32643) - all outputs
**Date**: 2026-02-10

---

## 1. Executive Summary

Scale the drainage mapping system from the single-polygon prototype to ALL 11 UIT polygons, implementing updated client specifications:

1. **Stream Order Filter**: Show only Order 3+ streams (filter out Orders 1-2)
2. **UTM Projection**: All outputs in EPSG:32643 (UTM Zone 43N)
3. **Full Coverage**: Process entire 1,600 sq km area (all 11 polygons)
4. **Line Smoothing**: Remove jagged staircase artifacts from stream vectors
5. **Complete Outputs**: KML + HTML + GeoJSON in UTM projection

---

## 2. Prototype Assessment

### What's Already Built (Single Polygon Test)
- ✅ GEE data acquisition (DEM, water bodies, SAR flood, HydroSHEDS)
- ✅ Local hydrological processing with pysheds
- ✅ Stream network extraction (Order 1-4, 568 segments)
- ✅ Water body detection (9 bodies, JRC + Sentinel-2)
- ✅ Flood risk mapping (TWI + SAR + depressions)
- ✅ Watershed delineation (720 basins)
- ✅ Streamlit dashboard with 8 toggleable layers
- ✅ KML and HTML exports

### Current Limitations vs New Requirements
1. **Coverage**: Only polygon 2 (~10 sq km) → Need all 11 polygons (~1600 sq km)
2. **Stream Filter**: Shows Order 1-4 → Need Order 3+ only
3. **Projection**: WGS84 (EPSG:4326) → Need UTM 43N (EPSG:32643)
4. **Line Quality**: Jagged 30m pixels → Need smoothed vectors
5. **Scale**: Prototype thresholds → Need production-scale parameters

---

## 3. Updated Technical Specifications

### 3.1 Coverage & Projection
- **Area**: All 11 UIT polygons (~1600 sq km total)
- **Projection**: UTM Zone 43N (EPSG:32643) for ALL outputs
- **DEM Resolution**: Keep 30m Copernicus GLO-30
- **Processing**: Single unified export (not per-polygon)

### 3.2 Stream Network Requirements
- **Stream Order**: Filter to show ONLY Order 3+ streams
- **Smoothing**: Apply Douglas-Peucker or spline smoothing to remove jagged artifacts
- **Validation**: Cross-check against HydroSHEDS reference network

### 3.3 Output Format Requirements
- **Primary Projection**: UTM 43N (EPSG:32643)
- **Export Formats**: 
  - GeoJSON layers (UTM coordinates)
  - Google Earth KML (converted to WGS84 for compatibility)
  - Interactive HTML map (WGS84 for web display)
- **File Organization**: Version-controlled exports in `exports-v2/`

---

## 4. Scaled Implementation Plan

### Phase 1: GEE Data Acquisition (Updated for Full Scale)

**Update Required Scripts:**
- `gee_dem_export_v2.py`: Export DEM for full 1600 sq km area
- `gee_water_bodies_v2.py`: Process all 11 polygons for water detection
- `gee_flood_sar_v2.py`: SAR analysis for full region
- `gee_hydrosheds_v2.py`: Reference network for full area

**Key Changes:**
- Increase export area from 10 sq km to 1600 sq km
- Use tiled export strategy (16-64 tiles depending on memory)
- Export directly to UTM 43N projection
- Adjust processing parameters for larger scale

### Phase 2: Hydrological Processing (Scaled)

**Update Required Scripts:**
- `hydro_process_v2.py`: Process full-scale DEM with appropriate thresholds
- `flood_risk_v2.py`: Scale flood risk analysis to 1600 sq km

**Key Changes:**
- **Flow Accumulation Threshold**: Increase from 500-1000 cells to 2000-5000 cells (larger area needs higher threshold)
- **Stream Order Filter**: Extract only Order 3+ streams, discard 1-2
- **Smoothing**: Add line smoothing using `simplify()` or spline interpolation
- **Memory Management**: Process in chunks if needed for large rasters

### Phase 3: Layer Preparation (Updated)

**Update Required Scripts:**
- `prepare_layers_v2.py`: Handle UTM projection and smoothing

**Key Changes:**
- **Primary Output**: UTM 43N coordinates in GeoJSON
- **Stream Smoothing**: Douglas-Peucker algorithm with 10-20m tolerance
- **Projection Workflow**: 
  - Process in UTM 43N (native)
  - Export GeoJSON in UTM 43N
  - Convert copy to WGS84 for KML/HTML only

### Phase 4: Dashboard & Exports (Enhanced)

**Update Required Scripts:**
- `app_drainage_v2.py`: Updated dashboard with all 11 polygons

**Key Changes:**
- **Full Coverage**: Show all 11 UIT polygons, not just polygon 2
- **Stream Filter**: Only display Order 3+ streams by default
- **Polygon Selection**: Dropdown to zoom to individual polygons
- **Performance**: Optimize layer loading for 1600 sq km dataset

---

## 5. Technical Implementation Details

### 5.1 GEE Export Strategy (Scaled)

```python
# For full 1600 sq km area:
# Bounding box: [76.22, 26.82, 76.72, 27.12]
# At 30m resolution: ~1667 x 1000 pixels = ~1.67 million pixels
# Expected export size: ~50-100 MB (vs 9 MB for prototype)

# Use tiled export if needed:
export_region = ee.Geometry.Rectangle([76.22, 26.82, 76.72, 27.12])
task = ee.batch.Export.image.toDrive({
  'image': dem.reproject('EPSG:32643', None, 30),  # UTM 43N
  'description': 'uit_dausa_dem_full_utm43n',
  'scale': 30,
  'region': export_region,
  'maxPixels': 1e9,  # Increase limit for large area
  'crs': 'EPSG:32643',
  'fileFormat': 'GeoTIFF'
})
```

### 5.2 Stream Order Filtering

```python
# In hydro_process_v2.py:
# After computing Strahler stream order, filter to Order 3+

stream_order = pysheds.grid.streamorder(...)
streams_filtered = np.where(stream_order >= 3, stream_order, 0)

# When vectorizing:
streams_gdf = streams_gdf[streams_gdf['stream_order'] >= 3]
print(f"Streams after Order 3+ filter: {len(streams_gdf)} segments")
```

### 5.3 Line Smoothing Implementation

```python
# In prepare_layers_v2.py:
import geopandas as gpd
from shapely.geometry import LineString

def smooth_linestrings(gdf, tolerance=15.0):
    """Smooth jagged linestrings using Douglas-Peucker simplification."""
    gdf_smoothed = gdf.copy()
    gdf_smoothed['geometry'] = gdf_smoothed['geometry'].simplify(tolerance, preserve_topology=True)
    return gdf_smoothed

# Apply to streams:
streams_gdf = smooth_linestrings(streams_gdf, tolerance=15.0)  # 15m tolerance for 30m DEM
```

### 5.4 UTM Projection Workflow

```python
# Primary processing in UTM 43N:
utm_crs = 'EPSG:32643'

# Load and reproject data:
gdf = gpd.read_file('input.geojson')
gdf_utm = gdf.to_crs(utm_crs)

# Process in UTM (accurate distance/area calculations)
# ...

# Export primary outputs in UTM:
gdf_utm.to_file('exports-v2/streams_utm43n.geojson', driver='GeoJSON')

# For web display, convert to WGS84:
gdf_wgs84 = gdf_utm.to_crs('EPSG:4326')
gdf_wgs84.to_file('exports-v2/streams_wgs84.geojson', driver='GeoJSON')
```

### 5.5 Scaled Processing Parameters

| Parameter | Prototype (10 sq km) | Full Scale (1600 sq km) | Reasoning |
|-----------|---------------------|------------------------|-----------|
| Flow Accumulation Threshold | 500 cells | 5000 cells | Larger area → higher threshold to avoid too many small streams |
| Stream Order Filter | 1-4 | 3+ only | Client requirement: remove minor channels |
| Smoothing Tolerance | None | 15m | Remove 30m DEM artifacts |
| Watershed Pour Points | Auto | Major stream intersections | Focus on significant drainage basins |
| Export Tiles | 1 | 4-16 | Large area may exceed GEE memory limits |

---

## 6. File Structure (Updated)

```
projects/uit-drainage/
  PLAN.md                    # Original prototype plan
  PLAN-v2.md                 # This updated full-scale plan
  
  # Original prototype scripts (keep for reference)
  gee_dem_export.py
  gee_water_bodies.py
  gee_flood_sar.py
  gee_hydrosheds.py
  hydro_process.py
  flood_risk.py
  prepare_layers.py
  app_drainage.py
  
  # Updated full-scale scripts
  gee_dem_export_v2.py       # Full 1600 sq km DEM export (UTM 43N)
  gee_water_bodies_v2.py     # All 11 polygons water analysis
  gee_flood_sar_v2.py        # Full-scale SAR flood mapping
  gee_hydrosheds_v2.py       # Reference network for full area
  hydro_process_v2.py        # Scaled hydro processing + Order 3+ filter
  flood_risk_v2.py           # Scaled flood risk analysis
  prepare_layers_v2.py       # UTM projection + line smoothing
  app_drainage_v2.py         # Updated dashboard for all 11 polygons
  
  data-v2/
    dem_full_utm43n.tif      # Full-scale DEM (UTM projection)
    dem_filled_utm43n.tif    # Depression-filled DEM
    flow_dir_utm43n.tif      # Flow direction raster
    flow_acc_utm43n.tif      # Flow accumulation raster
    streams_order3plus.tif   # Filtered stream network (Order 3+)
    # ... other raster outputs
  
  layers-v2/
    streams_utm43n.geojson   # Order 3+ streams (UTM 43N coordinates)
    streams_wgs84.geojson    # Same streams (WGS84 for web)
    water_bodies_utm43n.geojson
    flood_risk_utm43n.geojson
    watersheds_utm43n.geojson
    # ... other vector layers (primary UTM, secondary WGS84)
  
  exports-v2/
    drainage_map_full.html   # Interactive HTML (all 11 polygons)
    drainage_layers_utm43n.kml  # KML for Google Earth
    drainage_summary_full.csv    # Per-polygon statistics
    
  exports/                   # Keep prototype outputs for reference
    drainage_map.html        # Original single-polygon prototype
    drainage_layers.kml
    drainage_summary.csv
```

---

## 7. Implementation Steps

### Step 1: Update GEE Scripts for Full Scale
1. **Run `gee_dem_export_v2.py`**
   - Export full 1600 sq km DEM in UTM 43N
   - Handle large export (may take 30-60 minutes)
   
2. **Run `gee_water_bodies_v2.py`**
   - Process all 11 polygons for water detection
   - Merge results into single dataset
   
3. **Run `gee_flood_sar_v2.py`** & **`gee_hydrosheds_v2.py`**
   - Scale SAR analysis and reference network to full area

### Step 2: Scale Local Processing
1. **Run `hydro_process_v2.py`**
   - Process full-scale DEM with updated thresholds
   - Filter streams to Order 3+ only
   - Apply line smoothing
   
2. **Run `flood_risk_v2.py`**
   - Scale flood risk analysis to 1600 sq km

### Step 3: Prepare Final Layers
1. **Run `prepare_layers_v2.py`**
   - Generate UTM 43N primary outputs
   - Create WGS84 versions for web display
   - Apply final smoothing and simplification

### Step 4: Build Updated Dashboard
1. **Run `app_drainage_v2.py`**
   - Test dashboard with all 11 polygons
   - Verify performance with large dataset
   - Generate final exports

### Step 5: Quality Control
1. **Validate Stream Network**
   - Compare Order 3+ streams against HydroSHEDS
   - Visual inspection on satellite imagery
   
2. **Test Exports**
   - Open KML in Google Earth
   - Verify UTM coordinates are correct
   - Check HTML map performance

---

## 8. Expected Outputs (Full Scale)

### 8.1 Stream Network
- **Filtered Network**: Only Order 3+ streams (~58 segments vs 568 total)
- **Smoothed Lines**: 15m tolerance removes 30m DEM artifacts
- **UTM Coordinates**: Accurate distance/area measurements

### 8.2 Coverage Statistics
- **Total Area**: ~1600 sq km (vs 10 sq km prototype)
- **Stream Length**: Order 3+ only, estimated 200-400 km total
- **Water Bodies**: Estimated 50-100 bodies across all polygons
- **Flood Risk Zones**: High-resolution mapping for entire region

### 8.3 Export Files
- **KML Size**: ~10-20 MB (vs 2.6 MB prototype)
- **HTML Size**: ~20-40 MB (vs 5.3 MB prototype)
- **Processing Time**: 2-4 hours total (vs 30 minutes prototype)

---

## 9. Success Criteria (Updated)

1. ✅ **Complete Coverage**: All 11 UIT polygons processed
2. ✅ **Stream Order Filter**: Only Order 3+ streams visible
3. ✅ **UTM Projection**: All primary outputs in EPSG:32643
4. ✅ **Line Smoothing**: No jagged 30m artifacts visible
5. ✅ **Performance**: Dashboard loads in < 15 seconds
6. ✅ **Export Quality**: KML opens correctly in Google Earth
7. ✅ **Data Accuracy**: Major streams match known drainage patterns

---

## 10. Risk Assessment (Scaled)

### R1: GEE Memory Limits (HIGH)
**Risk**: 1600 sq km export may exceed free tier limits
**Mitigation**: Use tiled export strategy, increase maxPixels limit

### R2: Processing Time (MEDIUM)
**Risk**: Full-scale processing takes 4+ hours
**Mitigation**: Optimize algorithms, process overnight if needed

### R3: File Sizes (MEDIUM)  
**Risk**: Large outputs may be difficult to share/view
**Mitigation**: Provide simplified versions for quick viewing

### R4: Order 3+ Filter Too Restrictive (LOW)
**Risk**: Filtering to Order 3+ removes important drainage channels
**Mitigation**: Client requested this filter; can adjust if needed

---

This plan scales the proven prototype approach to meet the updated client specifications for the full 1600 sq km drainage master plan.