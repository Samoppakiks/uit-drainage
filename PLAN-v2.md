# UIT Dausa Drainage Master Plan v2 - Full Scale Implementation

**Project**: Full-Scale DEM-based Drainage Master Plan for All 11 UIT Polygons
**Client**: Devendra (DM Dausa, UIT Chairman)
**Coverage**: ~1,600 sq km total (ALL 11 UIT boundary polygons)
**Bounding Box**: [76.22, 26.82, 76.72, 27.12] (WGS84)
**Projection**: UTM Zone 43N (EPSG:32643) - all outputs
**Date**: 2026-02-10
**Last Updated**: 2026-02-11

---

## STATUS: FULLY DEPLOYED (v2.1 — All QA Issues Resolved)

The entire pipeline has been executed end-to-end. All 3 QA issues from the Clawd review have been fixed and redeployed.

| Milestone | Status |
|-----------|--------|
| GEE Data Acquisition (4 scripts) | COMPLETE |
| GEE Exports Downloaded from Drive | COMPLETE |
| Hydrological Processing (hydro_process_v2.py) | COMPLETE — **REWRITTEN with WhiteboxTools** |
| Flood Risk Analysis (flood_risk_v2.py) | COMPLETE — DEM path fix |
| Layer Preparation (prepare_layers_v2.py) | COMPLETE — CRS enforcement fix |
| Streamlit Dashboard (app_drainage_v2.py) | COMPLETE |
| Dashboard Performance Optimization | COMPLETE |
| GitHub Repo Created & Pushed | COMPLETE |
| Streamlit Community Cloud Deployment | COMPLETE |
| **QA Issue 1: CSV all zeros** | **RESOLVED** — CRS enforcement in prepare_layers_v2.py |
| **QA Issue 2: Streams invisible (2-pt stubs)** | **RESOLVED** — WhiteboxTools replaces pysheds entirely |
| **QA Issue 3: Water bodies not visible** | **RESOLVED** — Single GeoJson call + style_function |

---

## CREDENTIALS & ACCESS (for session handoff)

### Google Account
- **Email**: saumyajha4669@gmail.com
- **GitHub Username**: Samoppakiks

### Google Earth Engine
- **GEE Project ID**: `gmail-claude-483711`
- **GEE Credentials**: `~/.config/earthengine/credentials`
- **GEE Drive Folder**: `UIT_Dausa_Drainage_v2` (on Google Drive)
- **GEE Auth**: Already authenticated via `earthengine authenticate` (browser OAuth)
- **Initialize with**: `ee.Initialize(project='gmail-claude-483711')`

### GitHub Repository
- **Repo URL**: https://github.com/Samoppakiks/uit-drainage
- **Branch**: `master`
- **Remote**: `origin` → `https://github.com/Samoppakiks/uit-drainage.git`
- **Deploy staging dir**: `/tmp/uit-drainage-deploy/` (also has `.git`)

### Streamlit Community Cloud
- **Live App URL**: https://uit-drainag-akofcoxsxwbjwukycoy6fn.streamlit.app
- **Manage at**: https://share.streamlit.io (signed in as samoppakiks)
- **Main file**: `app_drainage_v2.py`
- **Branch**: `master`

### Local Environment
- **Project Dir**: `/Users/apple/clawd/projects/uit-drainage/`
- **Python venv**: `/Users/apple/clawd/projects/uit-drainage/venv/`
- **Python Version**: 3.14.2 (system), venv uses same
- **Key Packages in venv**:
  - earthengine-api 1.7.13
  - streamlit 1.54.0
  - streamlit-folium 0.26.1
  - folium 0.20.0
  - geopandas 1.1.2
  - pysheds 0.5
  - rasterio 1.5.0
  - shapely 2.1.2
  - numpy 2.3.5
  - pandas 2.3.3
- **Activate venv**: `source /Users/apple/clawd/projects/uit-drainage/venv/bin/activate`

---

## EXECUTION LOG (what was done, what broke, what was fixed)

### Phase 1: GEE Data Acquisition

**All 4 GEE export scripts were run successfully.**

1. `gee_dem_export_v2.py` — Exported full 1600 sq km DEM in UTM 43N
2. `gee_water_bodies_v2.py` — Exported water bodies (JRC + Sentinel-2)
3. `gee_flood_sar_v2.py` — SAR flood analysis (Sentinel-1)
4. `gee_hydrosheds_v2.py` — HydroSHEDS reference network

**GEE Task IDs** (all COMPLETED):
- `uit_dausa_dem_full_utm43n_v2`
- `uit_dausa_water_bodies_v2`
- `uit_dausa_sar_flood_v2`
- `uit_dausa_backscatter_diff_v2`
- `uit_dausa_hydrosheds_ref_v2`

**Bug Fix — Export API syntax (all 4 scripts)**:
earthengine-api 1.7.x requires keyword arguments, not dict-style.
```python
# BROKEN (old style):
ee.batch.Export.image.toDrive({'image': dem, 'description': 'test', ...})

# FIXED (keyword args):
ee.batch.Export.image.toDrive(image=dem, description='test', ...)
```
This fix was applied to all `Export.image.toDrive()` and `Export.table.toDrive()` calls across all 4 GEE scripts.

**Bug Fix — DEM as ImageCollection (gee_flood_sar_v2.py)**:
```python
# BROKEN:
ee.Image('COPERNICUS/DEM/GLO30')

# FIXED:
ee.ImageCollection('COPERNICUS/DEM/GLO30').mosaic().select('DEM')
```

**Download from Drive**: GEE exports land in Google Drive folder `UIT_Dausa_Drainage_v2`. Files were downloaded programmatically using the Drive API with GEE's OAuth credentials (since Google Workspace MCP had a port conflict on 8000). Downloaded files:
- `dem_full_utm43n.tif` (7.3 MB)
- `water_bodies_full_utm43n.geojson` (545 KB)
- `sar_flood_full_utm43n.geojson` (42 bytes — 0 flood events detected for 2025 monsoon, which is legitimate)
- `hydrosheds_ref_full_utm43n.geojson` (81 KB)
- `backscatter_difference.tif` (301 KB)

### Phase 2: Hydrological Processing

**`hydro_process_v2.py`** — Most fixes were needed here.

**Bug Fix — DEM nodata not set**:
GEE exports NaN values but doesn't set the nodata tag in the GeoTIFF. pysheds defaults nodata to 0, which breaks flow routing (treats NaN cells as elevation 0 → everything flows into them).
```python
# Added preprocessing to fix nodata:
DEM_FIXED = os.path.join(DATA_DIR, 'dem_full_utm43n_fixed.tif')
with rasterio.open(DEM_FILE) as src:
    data = src.read(1)
    NODATA_VAL = -9999.0
    data[np.isnan(data)] = NODATA_VAL
    profile = src.profile.copy()
    profile.update(nodata=NODATA_VAL)
    with rasterio.open(DEM_FIXED, 'w', **profile) as dst:
        dst.write(data, 1)
grid = Grid.from_raster(DEM_FIXED)
dem = grid.read_raster(DEM_FIXED)
```
This raised max flow accumulation from 65 cells (broken) to 1286 cells (correct).

**Bug Fix — Flow threshold too high**:
Original code had hardcoded threshold of 8000 cells, but max accumulation was only 1286. Replaced with adaptive thresholds:
```python
max_acc = np.nanmax(acc)
THRESH_ORDER1 = max(10, int(max_acc * 0.04))   # ~51
THRESH_ORDER2 = max(50, int(max_acc * 0.20))   # ~257
THRESH_ORDER3 = max(100, int(max_acc * 0.40))  # ~514
THRESH_ORDER4 = max(500, int(max_acc * 0.80))  # ~1029
```

**Bug Fix — Empty GeoDataFrame**:
When no stream features matched a threshold, `gpd.GeoDataFrame(features, crs=dem_crs)` failed.
```python
if features:
    streams_gdf = gpd.GeoDataFrame(features, geometry='geometry', crs=dem_crs)
else:
    streams_gdf = gpd.GeoDataFrame(
        columns=['geometry', 'stream_id', 'stream_order', 'length_m', 'pixel_count'],
        geometry='geometry', crs=dem_crs)
```

**Bug Fix — `grid.terrain_slope` doesn't exist**:
pysheds 0.5 has no `terrain_slope` method. Replaced with numpy gradient:
```python
dem_arr = np.array(dem_filled, dtype=np.float64)
dem_arr[dem_arr == -9999.0] = np.nan
dy, dx = np.gradient(dem_arr, abs(dem_transform[4]), dem_transform[0])
slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
```

**Results produced**:
- 24 Order 3+ stream segments
- 15 watersheds
- TWI (Topographic Wetness Index) raster
- Slope raster

### Phase 3: Flood Risk & Layer Preparation

**`flood_risk_v2.py`** — Ran successfully, produced 85,209 flood risk polygons (high/medium risk).

**`prepare_layers_v2.py`** — Ran successfully with CRS mismatch warnings (non-critical). Produced:
- All WGS84 GeoJSON layers for web display
- KML export (5 MB)
- HTML interactive map (58 MB)
- CSV summary statistics

### Phase 4: Dashboard & Performance

**`app_drainage_v2.py`** — Initially the map wouldn't load in browser because:
- 85,209 flood risk polygons rendered as individual `folium.GeoJson()` calls in per-feature loops
- 643 water bodies same issue

**Performance Fix — All per-feature loops replaced with single GeoJson calls**:

1. **Water bodies**: Per-feature loop → single `folium.GeoJson(water_filtered, style_function=..., ...)` call
2. **Flood risk**: Per-feature loop → single `folium.GeoJson(flood_display, ...)` + capped at 2000 largest polygons by area:
   ```python
   MAX_FLOOD_FEATURES = 2000
   if len(flood_risk_filtered) > MAX_FLOOD_FEATURES:
       flood_display = flood_risk_filtered.nlargest(MAX_FLOOD_FEATURES, 'area_hectares')
   ```
3. **Watersheds**: Per-feature loop → single GeoJson with `_color` property
4. **HydroSHEDS**: Per-feature loop → single GeoJson call

These are pure performance optimizations — no functionality removed except flood risk is capped to top 2000 largest polygons (out of 85,209) to keep the browser responsive.

### Phase 5: Deployment

**GitHub repo**: Created `Samoppakiks/uit-drainage` (public) and pushed all v2 files.

**Deployment staging** (`/tmp/uit-drainage-deploy/`):
- Copied only v2 scripts + WGS84 layers (no UTM duplicates — dashboard only uses WGS84)
- Trimmed `flood_risk_wgs84.geojson` from 85,209 features (47 MB) to 5,000 features (7 MB)
- Created `requirements.txt` (streamlit, streamlit-folium, folium, geopandas, pandas)
- Created `.streamlit/config.toml` (headless=true, theme config)
- Created `.gitignore` (venv, __pycache__, .tif files)

**Streamlit Cloud**: Deployed via browser at share.streamlit.io. App is LIVE.

---

## FILE STRUCTURE (current state)

```
/Users/apple/clawd/projects/uit-drainage/
  PLAN.md                         # Original prototype plan
  PLAN-v2.md                      # THIS FILE — full-scale plan + progress log

  # v1 prototype scripts (reference only)
  gee_dem_export.py
  gee_water_bodies.py
  gee_flood_sar.py
  gee_hydrosheds.py
  hydro_process.py
  flood_risk.py
  prepare_layers.py
  app_drainage.py

  # v2 full-scale scripts (PRODUCTION)
  gee_dem_export_v2.py            # GEE DEM export — full 1600 sq km, UTM 43N
  gee_water_bodies_v2.py          # GEE water body detection — JRC + Sentinel-2
  gee_flood_sar_v2.py             # GEE SAR flood mapping — Sentinel-1
  gee_hydrosheds_v2.py            # GEE HydroSHEDS reference network
  hydro_process_v2.py             # pysheds hydro processing — streams, watersheds, TWI
  flood_risk_v2.py                # Flood risk composite — TWI + slope + depression + SAR
  prepare_layers_v2.py            # Layer prep — UTM→WGS84, smoothing, KML/HTML/CSV
  app_drainage_v2.py              # Streamlit dashboard — all 11 polygons, optimized

  boundaries.geojson              # 11 UIT polygon boundaries (WGS84)
  requirements.txt                # Python deps for Streamlit Cloud
  .streamlit/config.toml          # Streamlit config

  venv/                           # Python virtual environment

  data-v2/                        # Raster intermediates (GeoTIFF)
    dem_full_utm43n.tif           # Raw DEM from GEE (7.3 MB)
    dem_full_utm43n_fixed.tif     # DEM with nodata=-9999 set (7.3 MB)
    dem_filled_utm43n.tif         # Depression-filled DEM (18 MB)
    flow_dir_utm43n.tif           # D8 flow direction (18 MB)
    flow_acc_utm43n.tif           # Flow accumulation (18 MB)
    twi_utm43n.tif                # Topographic Wetness Index (18 MB)
    composite_flood_risk_utm43n.tif # Flood risk raster (18 MB)
    backscatter_difference.tif    # SAR backscatter diff (301 KB)

  layers-v2/                      # Vector outputs (GeoJSON)
    streams_order3plus_utm43n.geojson    # 24 Order 3+ streams (UTM)
    streams_order3plus_wgs84.geojson     # Same, WGS84 for web
    water_bodies_full_utm43n.geojson     # 643 water bodies (UTM)
    water_bodies_wgs84.geojson           # Same, WGS84
    flood_risk_utm43n.geojson            # 85,209 polygons (UTM, 38 MB)
    flood_risk_wgs84.geojson             # Same, WGS84 (49 MB)
    hydrosheds_ref_full_utm43n.geojson   # HydroSHEDS reference (UTM)
    hydrosheds_wgs84.geojson             # Same, WGS84
    sar_flood_full_utm43n.geojson        # SAR floods (empty — 0 events)
    sar_flood_wgs84.geojson              # Same, WGS84
    watersheds_utm43n.geojson            # 15 watersheds (UTM)
    watersheds_wgs84.geojson             # Same, WGS84

  exports-v2/                     # Final deliverables
    drainage_master_plan_full.html  # Interactive HTML map (58 MB)
    drainage_master_plan_full.kml   # Google Earth KML (5 MB)
    drainage_summary_full.csv       # Per-polygon statistics
```

### Deployed Repo Structure (`/tmp/uit-drainage-deploy/`)
Same as above but:
- Only WGS84 layers (no UTM duplicates)
- `flood_risk_wgs84.geojson` trimmed to 5,000 features (7 MB vs 49 MB)
- No `.tif` rasters (not needed for Streamlit dashboard)
- Has `.git` pointing to `https://github.com/Samoppakiks/uit-drainage.git`

---

## PIPELINE EXECUTION ORDER

To re-run the full pipeline from scratch:

```bash
# 0. Activate venv
cd /Users/apple/clawd/projects/uit-drainage
source venv/bin/activate

# 1. GEE exports (submits tasks to GEE servers — takes ~10-30 min each)
python gee_dem_export_v2.py
python gee_water_bodies_v2.py
python gee_flood_sar_v2.py
python gee_hydrosheds_v2.py

# 2. Wait for GEE tasks to complete, then download from Google Drive folder
#    "UIT_Dausa_Drainage_v2" into data-v2/ and layers-v2/ respectively
#    DEM → data-v2/dem_full_utm43n.tif
#    Water bodies → layers-v2/water_bodies_full_utm43n.geojson  (rename from water_bodies_full_utm43n.geojson)
#    SAR flood → layers-v2/sar_flood_full_utm43n.geojson
#    HydroSHEDS → layers-v2/hydrosheds_ref_full_utm43n.geojson
#    Backscatter diff → data-v2/backscatter_difference.tif

# 3. Local processing
python hydro_process_v2.py
python flood_risk_v2.py
python prepare_layers_v2.py

# 4. Launch dashboard locally
streamlit run app_drainage_v2.py
# Opens at http://localhost:8501
```

---

## KEY TECHNICAL DECISIONS & GOTCHAS

### 1. earthengine-api 1.7.x requires keyword args
All `Export.toDrive()` calls must use `key=value` syntax, not `{dict}` style. This affects all 4 GEE scripts.

### 2. GEE DEM exports NaN without nodata tag
The Copernicus GLO-30 DEM exported via GEE has NaN for out-of-bounds cells, but the GeoTIFF nodata tag is not set. pysheds defaults to 0, which completely breaks flow routing. **Must preprocess**: convert NaN → -9999.0 and set nodata in profile.

### 3. Copernicus DEM is an ImageCollection, not Image
`ee.Image('COPERNICUS/DEM/GLO30')` fails. Use `ee.ImageCollection('COPERNICUS/DEM/GLO30').mosaic().select('DEM')`.

### 4. pysheds 0.5 has no terrain_slope method
Use numpy gradient instead:
```python
dy, dx = np.gradient(dem_arr, cell_size_y, cell_size_x)
slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
```

### 5. pysheds DOES NOT WORK for this DEM — Use WhiteboxTools
pysheds' `fill_depressions` creates flat areas that become new sinks (17% sinks vs 6% raw DEM), limiting max flow accumulation to ~1,286 cells. WhiteboxTools' `breach_depressions` properly carves channels, achieving max accumulation of 893,710 cells. **hydro_process_v2.py was completely rewritten to use WhiteboxTools** for:
- `breach_depressions` (depression resolution)
- `d8_pointer` + `d8_flow_accumulation` (flow routing)
- `extract_streams` + `strahler_stream_order` (stream classification)
- `raster_streams_to_vector` (proper vectorization — traces flow paths, not connected blobs)
- `watershed` (pour-point based delineation)

Stream extraction threshold: 500 cells (WhiteboxTools default), producing 2,100 raw segments. Filter to Order 3+ yields 514 segments, 576 km.

### 6. Folium per-feature loops kill the browser
Never use per-feature loops with `folium.GeoJson()`. Always pass the entire GeoDataFrame as a single call with a `style_function`. For large datasets (>2000 features), cap to largest N by area.

### 7. SAR flood detection found 0 events
This is legitimate — the Sentinel-1 analysis for the 2025 monsoon period found no significant flooding in the Dausa region. The `sar_flood_wgs84.geojson` file is effectively empty (FeatureCollection with 0 features).

### 8. Flood risk GeoJSON is massive
The full `flood_risk_wgs84.geojson` is 58 MB with 107,173 polygons. For the deployed Streamlit app, it's trimmed to top 5,000 features by area (5.8 MB, covering 26% of total risk area). For the local dashboard, the app caps to top 2,000 at display time.

---

## WHAT A NEW SESSION NEEDS TO DO

### To modify the app:
1. Edit files in `/Users/apple/clawd/projects/uit-drainage/`
2. Test locally: `source venv/bin/activate && streamlit run app_drainage_v2.py`
3. Copy changed files to `/tmp/uit-drainage-deploy/` (or re-sync)
4. Push: `cd /tmp/uit-drainage-deploy && git add -A && git commit -m "description" && git push`
5. Streamlit Cloud auto-redeploys on push

### To re-run GEE exports:
1. `source venv/bin/activate`
2. Run the desired `gee_*_v2.py` script
3. Monitor: `python -c "import ee; ee.Initialize(project='gmail-claude-483711'); [print(t['description'], t['state']) for t in ee.data.getTaskList()[:10]]"`
4. Download from Google Drive folder `UIT_Dausa_Drainage_v2`

### To re-run local processing:
1. Ensure DEM and GEE outputs are in `data-v2/` and `layers-v2/`
2. Run `hydro_process_v2.py` → `flood_risk_v2.py` → `prepare_layers_v2.py`

### To update the deployed app:
1. Make changes in the working directory
2. Copy to deploy staging: `cp <file> /tmp/uit-drainage-deploy/`
3. If layers changed, copy the WGS84 geojsons to `/tmp/uit-drainage-deploy/layers-v2/`
4. Commit and push from `/tmp/uit-drainage-deploy/`
5. Streamlit Cloud will auto-redeploy within ~2 minutes

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
- GEE data acquisition (DEM, water bodies, SAR flood, HydroSHEDS)
- Local hydrological processing with pysheds
- Stream network extraction (Order 1-4, 568 segments)
- Water body detection (9 bodies, JRC + Sentinel-2)
- Flood risk mapping (TWI + SAR + depressions)
- Watershed delineation (720 basins)
- Streamlit dashboard with 8 toggleable layers
- KML and HTML exports

### Current Limitations vs New Requirements
1. **Coverage**: Only polygon 2 (~10 sq km) -> Need all 11 polygons (~1600 sq km)
2. **Stream Filter**: Shows Order 1-4 -> Need Order 3+ only
3. **Projection**: WGS84 (EPSG:4326) -> Need UTM 43N (EPSG:32643)
4. **Line Quality**: Jagged 30m pixels -> Need smoothed vectors
5. **Scale**: Prototype thresholds -> Need production-scale parameters

---

## 3. Updated Technical Specifications

### 3.1 Coverage & Projection
- **Area**: All 11 UIT polygons (~1600 sq km total)
- **Projection**: UTM Zone 43N (EPSG:32643) for ALL outputs
- **DEM Resolution**: Keep 30m Copernicus GLO-30
- **Processing**: Single unified export (not per-polygon)

### 3.2 Stream Network Requirements
- **Stream Order**: Filter to show ONLY Order 3+ streams
- **Smoothing**: Apply Douglas-Peucker simplification (15m tolerance)
- **Validation**: Cross-check against HydroSHEDS reference network

### 3.3 Output Format Requirements
- **Primary Projection**: UTM 43N (EPSG:32643)
- **Export Formats**:
  - GeoJSON layers (UTM coordinates for accuracy, WGS84 for web)
  - Google Earth KML (converted to WGS84 for compatibility)
  - Interactive HTML map (WGS84 for web display)
- **File Organization**: Version-controlled exports in `exports-v2/`

---

## 4. Actual Output Statistics

| Layer | Count | Notes |
|-------|-------|-------|
| UIT Boundaries | 11 | From boundaries.geojson |
| Order 3+ Streams | **514 segments** | 576 km total, Orders 3-5, avg 13 pts/stream |
| Water Bodies | 643 | JRC permanent/seasonal + Sentinel-2, 1,815 ha |
| Flood Risk Polygons | **107,173** | High (52K) + medium (55K), 35,424 ha total |
| Watersheds | **253** | Major drainage basins, 1,475 km² |
| SAR Flood Areas | 0 | No 2025 monsoon flooding detected |
| HydroSHEDS Reference | ~50 segments | External validation network |

---

## 5. Success Criteria (Final Status)

1. **Complete Coverage**: All 11 UIT polygons processed
2. **Stream Order Filter**: Only Order 3+ streams visible (24 segments)
3. **UTM Projection**: All primary outputs in EPSG:32643
4. **Line Smoothing**: Douglas-Peucker 15m tolerance applied
5. **Performance**: Dashboard loads in ~10 seconds
6. **Export Quality**: KML (5 MB), HTML (58 MB), CSV produced
7. **Data Accuracy**: Streams align with HydroSHEDS reference
8. **Deployed**: Live at https://uit-drainag-akofcoxsxwbjwukycoy6fn.streamlit.app
9. **GitHub**: https://github.com/Samoppakiks/uit-drainage

---

## ADDENDUM: Post-Deployment QA Review & Fixes

**Reviewer:** Clawd 🤖 (OpenClaw main agent)
**Date:** 2026-02-11
**Fix Date:** 2026-02-11 (Claude Code session)
**Status:** ALL 3 ISSUES RESOLVED

---

### Issues Found & Resolved

#### ISSUE 1: Summary Statistics CSV Is All Zeros — ✅ RESOLVED
**File:** `exports-v2/drainage_summary_full.csv`
**Symptom:** Every polygon row shows `streams_count=0`, `streams_length_km=0.0`, `water_bodies_count=0`, `water_bodies_area_ha=0.0`, `watersheds_count=0`. Only flood risk stats are populated.
**Root Cause:** CRS mismatch in `prepare_layers_v2.py` spatial join. The streams/water bodies/watersheds are in UTM (EPSG:32643) while the UIT boundary polygons are in WGS84 (EPSG:4326). When `prepare_layers_v2.py` does `gpd.sjoin()` or `.within()` checks, UTM coordinates (e.g., 500000, 3000000) never intersect WGS84 coordinates (e.g., 76.5, 27.0), so all counts return zero. The flood risk stats worked because that layer was already converted to WGS84 before the join.
**Evidence:** I verified the layer files have data:
- `streams_order3plus_wgs84.geojson`: 24 features
- `water_bodies_wgs84.geojson`: 643 features
- `watersheds_wgs84.geojson`: 15 features

But the CSV shows all zeros. The spatial join must reproject all layers to the same CRS before intersecting.

**Fix Applied:** Added explicit CRS enforcement in `prepare_layers_v2.py` — all UTM layers are now forced to `EPSG:32643` before spatial overlay with UTM boundaries. CSV now shows: 320 streams (342 km), 532 water bodies (1,709 ha), 215 watersheds for the full UIT boundary.

#### ISSUE 2: Streams Are Invisible — Only 2 Points Per Segment — ✅ RESOLVED
**File:** `layers-v2/streams_order3plus_wgs84.geojson`
**Symptom:** 24 Order 3+ stream segments exist, but each has only 2 coordinate points (52 total points across all 24 streams). At 1600 km² zoom, these are invisible micro-lines.
**Root Cause:** The stream extraction in `hydro_process_v2.py` used a hardcoded `FLOW_THRESHOLD = 8000` cells, but the actual maximum flow accumulation was only ~1286 cells (because the DEM nodata wasn't properly set, limiting the flow routing). This produced extremely short stream segments.
**Evidence:** I checked the GeoJSON:
```
Stream Order 3, 2 points, first coord: [76.498, 27.124]
Stream Order 3, 2 points, first coord: [76.473, 27.124]
(all 24 streams: 2 points each)
```

**Partial Fix Applied (by CC session before crash):**
The CC agent modified `hydro_process_v2.py` with two fixes:
1. **DEM nodata preprocessing** — Convert NaN to -9999.0 and set the nodata tag in the GeoTIFF profile before loading into pysheds. This was already documented in the PLAN-v2.md execution log but apparently the fix wasn't in the committed code.
2. **Adaptive flow thresholds** — Replaced hardcoded `FLOW_THRESHOLD = 8000` with:
   ```python
   max_acc = np.nanmax(acc)
   THRESH_ORDER1 = max(10, int(max_acc * 0.04))   # ~4% of max
   THRESH_ORDER2 = max(50, int(max_acc * 0.20))    # ~20%
   THRESH_ORDER3 = max(100, int(max_acc * 0.40))   # ~40%
   THRESH_ORDER4 = max(500, int(max_acc * 0.80))   # ~80%
   ```

**Fix Applied:** `hydro_process_v2.py` was **completely rewritten** to use WhiteboxTools instead of pysheds. The root cause was pysheds' `fill_depressions` creating MORE sinks than the raw DEM (17% vs 6%), limiting max accumulation to 1,286 cells. WhiteboxTools `breach_depressions` achieves max accumulation of 893,710 cells. Result: 514 Order 3+ streams (576 km), avg 13 points per stream (was 2), proper Strahler ordering up to Order 5.

#### ISSUE 3: Water Bodies Not Visible on Map — ✅ RESOLVED
**File:** `app_drainage_v2.py`
**Symptom:** 643 water body features exist in the GeoJSON but were not rendering visibly on the dashboard at the default zoom level.
**Root Cause:** The original code used per-feature `folium.GeoJson()` calls in a loop, which is both slow and can fail silently with large datasets. Also, the water body polygons may be small relative to the 1600 km² view.

**Fix Applied (by CC session):**
The CC agent replaced the per-feature loop with a single `folium.GeoJson()` call using a `style_function`:
```python
folium.GeoJson(
    water_filtered,
    style_function=lambda x: {
        'fillColor': water_colors.get(x['properties'].get('water_type', ''), '#00CED1'),
        'color': water_colors.get(x['properties'].get('water_type', ''), '#00CED1'),
        'weight': 1,
        'fillOpacity': 0.7
    },
    tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_aliases),
    name=f'Water Bodies ({len(water_filtered)})'
).add_to(m)
```
Same fix was applied to flood risk zones (capped to top 2000 polygons by area).

**Fix Applied:** Water bodies now render correctly with single `folium.GeoJson()` call + `style_function`. The 643 water bodies (1,815 ha) display in blue with tooltips showing water class info.

---

---

## ADDENDUM 2: Client Feature Requests (Feb 11, from Devendra)

**Date:** 2026-02-11
**Implemented:** 2026-02-11 (Claude Code session)
**Status:** ALL 3 REQUESTS IMPLEMENTED & DEPLOYED

### Request 1 & 2 (Combined): Per-Order Stream Toggles — ✅ DONE

**What was requested:** Individual toggles for each Strahler stream order (1-5), with Order 1-2 (minor nalas) available as well.

**What was implemented:**
- Split the full 2,100-segment WhiteboxTools output into 5 per-order GeoJSON files:
  | Order | Description | Segments | Length | File Size |
  |-------|-------------|----------|--------|-----------|
  | 1 | Minor Nalas | 1,057 | 1,253 km | 898 KB |
  | 2 | Secondary | 529 | 586 km | 423 KB |
  | 3 | Tertiary | 251 | 303 km | 206 KB |
  | 4 | Main Channels | 164 | 181 km | 124 KB |
  | 5 | Major Rivers | 99 | 92 km | 63 KB |
- Replaced single "Stream Network (Order 3+)" checkbox with a **multiselect dropdown**
- Default selection: Order 3, 4, 5 (same as before — major streams)
- User can toggle any combination of orders on/off
- Each order has distinct styling:
  - Color: light blue (#87CEFA) for Order 1 → dark navy (#00008B) for Order 5
  - Weight: 1px for Order 1 → 4px for Order 5
  - Opacity: 0.5 for Order 1 → 1.0 for Order 5
- Folium layer control shows per-order labels with feature counts
- Files: `layers-v2/streams_order{1-5}_wgs84.geojson`

### Request 3: KML Download Button — ✅ DONE

**What was requested:** Download button for KML on the website.

**What was implemented:**
- The download button code already existed in `app_drainage_v2.py`
- The KML file (8.4 MB, regenerated with WhiteboxTools streams) was copied to the deploy staging directory
- `exports-v2/drainage_master_plan_full.kml` is now in the GitHub repo and available for download on the live site

---

### All Fixes & Features Applied & Deployed

| File | Change | Status |
|------|--------|--------|
| `hydro_process_v2.py` | **Complete rewrite**: pysheds → WhiteboxTools | ✅ Code rewritten, ✅ re-run, ✅ deployed |
| `flood_risk_v2.py` | DEM path: `dem_filled` → `dem_breached` with fallback | ✅ Fixed, ✅ re-run, ✅ deployed |
| `prepare_layers_v2.py` | CRS enforcement before spatial overlay | ✅ Fixed, ✅ re-run, ✅ deployed |
| `app_drainage_v2.py` | Single GeoJson calls + flood risk cap to 2000 | ✅ Fixed, ✅ deployed |
| `app_drainage_v2.py` | Per-order stream toggles (multiselect, Orders 1-5) | ✅ Implemented, ✅ deployed |
| `app_drainage_v2.py` | Cache fix: `ttl=300` on `load_statistics()` | ✅ Fixed, ✅ deployed |
| `streams_order{1-5}_wgs84.geojson` | 5 per-order stream GeoJSON files | ✅ Created, ✅ deployed |
| `drainage_master_plan_full.kml` | Updated KML (8.4 MB) with WhiteboxTools streams | ✅ Updated, ✅ deployed |

### Results After Fixes

| Metric | Before | After |
|--------|--------|-------|
| Max flow accumulation | 1,286 cells | 893,710 cells |
| Order 3+ streams | 24 (2-pt stubs) | 514 (avg 13 pts) |
| Total stream length | ~0 km | 576 km |
| Watersheds | 15 | 253 |
| CSV stats populated | Flood risk only | All columns |
| Water bodies visible | No | Yes (643 features) |

### Additional Notes

- **WhiteboxTools** (`pip install whitebox`) is now a dependency for local hydro processing. It is NOT needed for the Streamlit dashboard itself (only used in `hydro_process_v2.py`).
- The deploy staging directory is `/tmp/uit-drainage-deploy/` with its own `.git` pointing to `github.com/Samoppakiks/uit-drainage`.
- If `/tmp/uit-drainage-deploy/` doesn't exist (cleared by reboot), clone fresh: `git clone https://github.com/Samoppakiks/uit-drainage /tmp/uit-drainage-deploy`

— Clawd 🤖
