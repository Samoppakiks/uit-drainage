#!/usr/bin/env python3
"""
Streamlit Dashboard v2: UIT Dausa Drainage Master Plan (Full Scale)
Interactive dashboard for all 11 UIT polygons with Order 3+ streams,
UTM-based measurements, and complete drainage analysis
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import geopandas as gpd
import pandas as pd
import json
import os
from pathlib import Path

st.set_page_config(
    page_title="UIT Dausa Drainage Master Plan v2",
    page_icon="🌊",
    layout="wide"
)

# Setup paths
BASE_DIR = Path(__file__).parent
LAYERS_DIR = BASE_DIR / 'layers-v2'
EXPORTS_DIR = BASE_DIR / 'exports-v2'

@st.cache_data
def load_layer(layer_name, projection='wgs84'):
    """Load a layer file if it exists."""
    if projection == 'wgs84':
        layer_file = LAYERS_DIR / f'{layer_name}_wgs84.geojson'
    else:
        layer_file = LAYERS_DIR / f'{layer_name}_utm43n.geojson'
    
    if layer_file.exists():
        return gpd.read_file(layer_file)
    return None

@st.cache_data
def load_boundaries():
    """Load UIT boundary polygons."""
    boundary_file = BASE_DIR / 'boundaries.geojson'
    gdf = gpd.read_file(boundary_file)
    if gdf.crs != 'EPSG:4326':
        gdf = gdf.to_crs('EPSG:4326')
    return gdf

@st.cache_data 
def load_statistics():
    """Load per-polygon statistics."""
    stats_file = EXPORTS_DIR / 'drainage_summary_full.csv'
    if stats_file.exists():
        return pd.read_csv(stats_file)
    return None

# Page header
st.title("🌊 UIT Dausa — Drainage Master Plan v2")
st.caption("Full-scale drainage analysis covering all 11 UIT polygons (~1600 km²)")

# Load data
boundaries = load_boundaries()
statistics = load_statistics()

if boundaries is None:
    st.error("❌ Could not load UIT boundaries")
    st.stop()

# Sidebar controls
st.sidebar.header("🎛️ Map Controls")

# Polygon selector
polygon_names = [f"Polygon {idx}: {row.get('name', 'Unnamed').strip()}" 
                for idx, row in boundaries.iterrows()]
polygon_names.insert(0, "All Polygons")

selected_polygon = st.sidebar.selectbox(
    "Select UIT Polygon:",
    options=range(len(polygon_names)),
    format_func=lambda x: polygon_names[x]
)

# Layer toggles
st.sidebar.subheader("📍 Layer Visibility")

show_boundaries = st.sidebar.checkbox("UIT Boundaries", True)
show_streams = st.sidebar.checkbox("🌊 Stream Network (Order 3+)", True)
show_water = st.sidebar.checkbox("💧 Water Bodies", True)  
show_flood_risk = st.sidebar.checkbox("⚠️ Flood Risk Zones", True)
show_watersheds = st.sidebar.checkbox("🏞️ Watersheds", False)
show_sar_flood = st.sidebar.checkbox("📡 SAR Flood History", False)
show_hydrosheds = st.sidebar.checkbox("🗺️ HydroSHEDS Reference", False)

# Base map selector
base_map = st.sidebar.selectbox(
    "Base Map:",
    ["Google Satellite", "Google Maps", "OpenStreetMap"]
)

# Load layers
streams = load_layer('streams_order3plus')
water_bodies = load_layer('water_bodies')
flood_risk = load_layer('flood_risk')
watersheds = load_layer('watersheds')
sar_flood = load_layer('sar_flood')
hydrosheds = load_layer('hydrosheds')

# Calculate map center and zoom
if selected_polygon == 0:  # All polygons
    bounds = boundaries.total_bounds
    zoom_start = 10
else:
    polygon_idx = selected_polygon - 1
    single_polygon = boundaries.iloc[[polygon_idx]]
    bounds = single_polygon.total_bounds
    zoom_start = 12

center_lat = (bounds[1] + bounds[3]) / 2
center_lon = (bounds[0] + bounds[2]) / 2

# Create map
tile_configs = {
    "Google Satellite": {
        'tiles': 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        'attr': 'Google Satellite'
    },
    "Google Maps": {
        'tiles': 'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
        'attr': 'Google Maps'
    },
    "OpenStreetMap": {
        'tiles': 'OpenStreetMap',
        'attr': 'OpenStreetMap'
    }
}

tile_config = tile_configs[base_map]
m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=zoom_start,
    tiles=tile_config['tiles'],
    attr=tile_config['attr']
)

# Add alternative base layers
for name, config in tile_configs.items():
    if name != base_map:
        if config['tiles'] == 'OpenStreetMap':
            folium.TileLayer('OpenStreetMap', name=name).add_to(m)
        else:
            folium.TileLayer(
                tiles=config['tiles'],
                attr=config['attr'],
                name=name
            ).add_to(m)

# Filter layers to selected polygon if needed
def filter_to_polygon(gdf, polygon_idx):
    """Filter GeoDataFrame to intersect with selected polygon."""
    if gdf is None or gdf.empty:
        return gdf
    
    target_polygon = boundaries.iloc[[polygon_idx]]
    
    # Ensure same CRS
    if gdf.crs != target_polygon.crs:
        if gdf.crs == 'EPSG:32643':  # UTM to WGS84
            gdf = gdf.to_crs('EPSG:4326')
        elif target_polygon.crs != 'EPSG:4326':
            target_polygon = target_polygon.to_crs(gdf.crs)
    
    # Return intersection
    try:
        return gpd.overlay(gdf, target_polygon, how='intersection')
    except:
        return gdf  # Return original if intersection fails

if selected_polygon > 0:  # Single polygon selected
    polygon_idx = selected_polygon - 1
    streams_filtered = filter_to_polygon(streams, polygon_idx)
    water_filtered = filter_to_polygon(water_bodies, polygon_idx)
    flood_risk_filtered = filter_to_polygon(flood_risk, polygon_idx)
    watersheds_filtered = filter_to_polygon(watersheds, polygon_idx)
    sar_flood_filtered = filter_to_polygon(sar_flood, polygon_idx)
    hydrosheds_filtered = filter_to_polygon(hydrosheds, polygon_idx)
else:  # All polygons
    streams_filtered = streams
    water_filtered = water_bodies
    flood_risk_filtered = flood_risk
    watersheds_filtered = watersheds
    sar_flood_filtered = sar_flood
    hydrosheds_filtered = hydrosheds

# Add UIT boundaries
if show_boundaries:
    if selected_polygon > 0:
        # Highlight selected polygon
        selected_boundary = boundaries.iloc[[selected_polygon - 1]]
        folium.GeoJson(
            selected_boundary,
            style_function=lambda x: {
                'fillColor': 'yellow',
                'color': '#ff0000',
                'weight': 4,
                'dashArray': '5,5',
                'fillOpacity': 0.1
            },
            tooltip=folium.GeoJsonTooltip(['name', 'layer']),
            name='Selected UIT Polygon'
        ).add_to(m)
        
        # Add other boundaries in lighter style
        other_boundaries = boundaries.drop(boundaries.index[selected_polygon - 1])
        folium.GeoJson(
            other_boundaries,
            style_function=lambda x: {
                'fillColor': 'none',
                'color': '#cc0000', 
                'weight': 2,
                'opacity': 0.5,
                'dashArray': '10,5'
            },
            name='Other UIT Polygons'
        ).add_to(m)
    else:
        # All boundaries
        folium.GeoJson(
            boundaries,
            style_function=lambda x: {
                'fillColor': 'none',
                'color': '#ff0000',
                'weight': 3,
                'dashArray': '5,5'
            },
            tooltip=folium.GeoJsonTooltip(['name', 'layer']),
            name='UIT Boundaries'
        ).add_to(m)

# Add stream network (Order 3+ only)
if show_streams and streams_filtered is not None and not streams_filtered.empty:
    stream_colors = {3: '#4169E1', 4: '#0000CD', 5: '#00008B', 6: '#000080'}
    stream_weights = {3: 2, 4: 3, 5: 4, 6: 5}
    
    folium.GeoJson(
        streams_filtered,
        style_function=lambda x: {
            'color': stream_colors.get(int(x['properties'].get('stream_order', 3)), '#4169E1'),
            'weight': stream_weights.get(int(x['properties'].get('stream_order', 3)), 2),
            'opacity': 0.8
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[c for c in ['stream_order', 'length_m_smoothed'] if c in streams_filtered.columns],
            aliases=[a for c, a in [('stream_order', 'Order'), ('length_m_smoothed', 'Length (m)')] if c in streams_filtered.columns]
        ),
        name=f'Streams Order 3+ ({len(streams_filtered)})'
    ).add_to(m)

# Add water bodies
if show_water and water_filtered is not None and not water_filtered.empty:
    water_colors = {
        'permanent_jrc': '#0000FF',
        'seasonal_jrc': '#4682B4',
        'post_monsoon_s2': '#00CED1',
        'pre_monsoon_s2': '#87CEEB'
    }

    tooltip_fields = [c for c in ['water_type', 'area_hectares'] if c in water_filtered.columns]
    tooltip_aliases = [a for c, a in [('water_type', 'Type'), ('area_hectares', 'Area (ha)')] if c in water_filtered.columns]

    folium.GeoJson(
        water_filtered,
        style_function=lambda x: {
            'fillColor': water_colors.get(x['properties'].get('water_type', ''), '#00CED1'),
            'color': water_colors.get(x['properties'].get('water_type', ''), '#00CED1'),
            'weight': 1,
            'fillOpacity': 0.7
        },
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_aliases) if tooltip_fields else None,
        name=f'Water Bodies ({len(water_filtered)})'
    ).add_to(m)

# Add flood risk zones — cap to largest polygons to avoid browser overload
if show_flood_risk and flood_risk_filtered is not None and not flood_risk_filtered.empty:
    risk_colors = {'high': '#FF0000', 'medium': '#FFA500', 'low': '#FFFF00'}

    # Limit to top 2000 polygons by area to keep browser responsive
    MAX_FLOOD_FEATURES = 2000
    if len(flood_risk_filtered) > MAX_FLOOD_FEATURES:
        flood_display = flood_risk_filtered.nlargest(MAX_FLOOD_FEATURES, 'area_hectares')
        flood_label = f'Flood Risk (top {MAX_FLOOD_FEATURES}/{len(flood_risk_filtered)})'
    else:
        flood_display = flood_risk_filtered
        flood_label = f'Flood Risk ({len(flood_risk_filtered)})'

    tooltip_fields = [c for c in ['risk_label', 'area_hectares'] if c in flood_display.columns]
    tooltip_aliases = [a for c, a in [('risk_label', 'Risk'), ('area_hectares', 'Area (ha)')] if c in flood_display.columns]

    folium.GeoJson(
        flood_display,
        style_function=lambda x: {
            'fillColor': risk_colors.get(x['properties'].get('risk_label', ''), '#888'),
            'color': risk_colors.get(x['properties'].get('risk_label', ''), '#888'),
            'weight': 0.5,
            'fillOpacity': 0.4
        },
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_aliases) if tooltip_fields else None,
        name=flood_label
    ).add_to(m)

# Add watersheds
if show_watersheds and watersheds_filtered is not None and not watersheds_filtered.empty:
    import random
    random.seed(42)
    palette = [f'#{random.randint(50,220):02x}{random.randint(50,220):02x}{random.randint(50,220):02x}' for _ in range(20)]

    # Add a color column for styling
    ws_display = watersheds_filtered.copy()
    ws_display['_color'] = [palette[i % len(palette)] for i in range(len(ws_display))]

    tooltip_fields = [c for c in ['watershed_id', 'area_km2'] if c in ws_display.columns]
    tooltip_aliases = [a for c, a in [('watershed_id', 'Watershed'), ('area_km2', 'Area (km²)')] if c in ws_display.columns]

    folium.GeoJson(
        ws_display,
        style_function=lambda x: {
            'fillColor': x['properties'].get('_color', '#888'),
            'color': '#333',
            'weight': 0.5,
            'fillOpacity': 0.2
        },
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_aliases) if tooltip_fields else None,
        name=f'Watersheds ({len(ws_display)})'
    ).add_to(m)

# Add SAR flood areas
if show_sar_flood and sar_flood_filtered is not None and not sar_flood_filtered.empty:
    fg_sar = folium.FeatureGroup(name=f'SAR Flood History ({len(sar_flood_filtered)})')
    
    for idx, sar in sar_flood_filtered.iterrows():
        area_ha = sar.get('area_hectares', 0)
        intensity = sar.get('flood_intensity_db', 0)
        
        folium.GeoJson(
            sar.geometry,
            style_function=lambda x: {
                'fillColor': '#800080',
                'color': '#800080',
                'weight': 1,
                'fillOpacity': 0.5
            },
            tooltip=f"SAR Flood Area<br>Area: {area_ha:.1f} ha<br>Intensity: {intensity:.1f} dB"
        ).add_to(fg_sar)
    
    fg_sar.add_to(m)

# Add HydroSHEDS reference
if show_hydrosheds and hydrosheds_filtered is not None and not hydrosheds_filtered.empty:
    tooltip_fields = [c for c in ['RIV_ORD', 'LENGTH_UTM_KM'] if c in hydrosheds_filtered.columns]
    tooltip_aliases = [a for c, a in [('RIV_ORD', 'Order'), ('LENGTH_UTM_KM', 'Length (km)')] if c in hydrosheds_filtered.columns]

    folium.GeoJson(
        hydrosheds_filtered,
        style_function=lambda x: {
            'color': '#00FF00',
            'weight': 3,
            'opacity': 0.7,
            'dashArray': '8,4'
        },
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_aliases) if tooltip_fields else None,
        name=f'HydroSHEDS Reference ({len(hydrosheds_filtered)})'
    ).add_to(m)

# Add layer control
folium.LayerControl().add_to(m)

# Main layout
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("🗺️ Interactive Drainage Map")
    map_data = st_folium(m, width=None, height=700, returned_objects=[])

with col2:
    st.subheader("📊 Summary Statistics")
    
    if statistics is not None:
        if selected_polygon > 0:
            # Single polygon stats
            polygon_idx = selected_polygon - 1
            polygon_stats = statistics.iloc[polygon_idx]
            
            st.metric("Polygon", f"{polygon_idx}: {polygon_stats.get('polygon_name', 'Unnamed')}")
            st.metric("Area", f"{polygon_stats.get('area_km2', 0):.1f} km²")
            
            # Stream statistics
            st.markdown("**🌊 Streams (Order 3+)**")
            total_length = polygon_stats.get('streams_length_km', 0)
            total_count = polygon_stats.get('streams_count', 0)
            st.write(f"Total length: {total_length} km")
            st.write(f"Total segments: {total_count}")
            
            for order in [3, 4, 5, 6]:
                count = polygon_stats.get(f'streams_order{order}_count', 0)
                if count > 0:
                    st.write(f"  Order {order}: {count} segments")
            
            # Water body statistics
            st.markdown("**💧 Water Bodies**")
            water_count = polygon_stats.get('water_bodies_count', 0)
            water_area = polygon_stats.get('water_bodies_area_ha', 0)
            st.write(f"Count: {water_count}")
            st.write(f"Total area: {water_area:.1f} ha")
            
            # Flood risk statistics  
            st.markdown("**⚠️ Flood Risk**")
            flood_area = polygon_stats.get('flood_risk_area_ha', 0)
            st.write(f"Total risk area: {flood_area:.1f} ha")
            
            for risk in ['high', 'medium', 'low']:
                zones = polygon_stats.get(f'flood_risk_{risk}_zones', 0)
                if zones > 0:
                    st.write(f"  {risk.title()}: {zones} zones")
        
        else:
            # All polygons summary
            st.markdown("**📋 All UIT Polygons Summary**")
            
            total_area = statistics['area_km2'].sum()
            st.metric("Total Area", f"{total_area:.1f} km²")
            
            if 'streams_length_km' in statistics.columns:
                total_stream_length = statistics['streams_length_km'].sum()
                st.metric("Total Stream Length", f"{total_stream_length:.1f} km")
            
            if 'water_bodies_area_ha' in statistics.columns:
                total_water_area = statistics['water_bodies_area_ha'].sum()
                st.metric("Total Water Area", f"{total_water_area:.1f} ha")
            
            if 'flood_risk_area_ha' in statistics.columns:
                total_flood_area = statistics['flood_risk_area_ha'].sum()
                st.metric("Total Flood Risk Area", f"{total_flood_area:.1f} ha")
    
    else:
        st.warning("📊 Statistics not available")
        st.write("Run prepare_layers_v2.py to generate statistics")

# Export section
st.subheader("📥 Download Exports")

export_cols = st.columns(3)

with export_cols[0]:
    kml_file = EXPORTS_DIR / 'drainage_master_plan_full.kml'
    if kml_file.exists():
        with open(kml_file, 'rb') as f:
            st.download_button(
                "🌍 Google Earth KML",
                f.read(),
                file_name="uit_dausa_drainage_full.kml",
                mime="application/vnd.google-earth.kml+xml"
            )

with export_cols[1]:
    html_file = EXPORTS_DIR / 'drainage_master_plan_full.html'
    if html_file.exists():
        with open(html_file, 'rb') as f:
            st.download_button(
                "🗺️ HTML Map",
                f.read(), 
                file_name="uit_dausa_drainage_map.html",
                mime="text/html"
            )

with export_cols[2]:
    csv_file = EXPORTS_DIR / 'drainage_summary_full.csv'
    if csv_file.exists():
        with open(csv_file, 'rb') as f:
            st.download_button(
                "📊 Statistics CSV",
                f.read(),
                file_name="uit_dausa_drainage_stats.csv", 
                mime="text/csv"
            )

# Footer information
st.markdown("---")
st.markdown("**🎯 Client Requirements Fulfilled:**")
st.write("""
✅ **Stream Order 3+**: Only major drainage channels displayed  
✅ **UTM Zone 43N**: Accurate measurements in native projection  
✅ **Full Coverage**: All 11 UIT polygons (~1600 km²)  
✅ **Line Smoothing**: Removed DEM artifacts from stream vectors  
✅ **Complete Exports**: KML + HTML + GeoJSON layers
""")

st.caption("""
**Data Sources:** Copernicus GLO-30 DEM, JRC Global Surface Water, Sentinel-1/2, HydroSHEDS  
**Processing:** pysheds (hydrology), UTM-based measurements, Douglas-Peucker smoothing  
**Coverage:** Dausa District UIT boundaries (~1600 km²)
""")