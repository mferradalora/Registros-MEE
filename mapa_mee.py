#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generador de Mapa Interactivo MEE DGA con popup ampliado de metadatos y cálculo de Caudal Derecho.
Salida: index.html (Optimizado para GitHub Pages).
"""

import json
import re
import unicodedata
from pathlib import Path
from branca.element import Element
import geopandas as gpd
import numpy as np
import pandas as pd
import folium

# Configuración de URLs y directorios
RENDER_URL = "https://registros-mee.onrender.com".rstrip("/")
carpeta_admin = Path("data")
path_csv = Path("data/catalogo_obras_mee.csv")

regiones_provincias = {
    "Arica y Parinacota": ["Arica", "Parinacota"],
    "Tarapaca": ["Iquique", "Tamarugal"],
    "Antofagasta": ["Tocopilla", "El Loa", "Antofagasta"],
    "Atacama": ["Chañaral", "Copiapó", "Huasco"],
    "Coquimbo": ["Elqui", "Limarí", "Choapa"],
    "Valparaiso": ["Petorca", "Los Andes", "San Felipe", "Quillota", "Valparaíso", "San Antonio", "Isla de Pascua", "Marga Marga"],
    "Metropolitana": ["Chacabuco", "Santiago", "Cordillera", "Maipo", "Melipilla", "Talagante"],
    "O'Higgins": ["Cachapoal", "Colchagua", "Cardenal Caro"],
    "Maule": ["Curicó", "Talca", "Linares", "Cauquenes"],
    "Nuble": ["Diguillín", "Itata", "Punilla"],
    "Bio Bio": ["Bio-Bio", "Concepción", "Arauco"],
    "Araucania": ["Malleco", "Cautín"],
    "Los Rios": ["Valdivia", "Ranco"],
    "Los Lagos": ["Osorno", "Llanquihue", "Chiloé", "Palena"],
    "Aysen": ["Coyhaique", "Aysén", "General Carrera", "Capitán Prat"],
    "Magallanes": ["Última Esperanza", "Magallanes", "Tierra del Fuego", "Antártica Chilena"]
}


def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto_str = str(texto).lower()
    texto_str = ''.join(c for c in unicodedata.normalize('NFKD', texto_str) if unicodedata.category(c) != 'Mn')
    texto_str = re.sub(r'[^a-z0-9\s]', ' ', texto_str)
    return ' '.join(texto_str.split())


def filtrar_layer_local(gdf, region_nombre):
    if gdf.empty:
        return gdf.iloc[0:0]
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    region_norm = normalizar_texto(region_nombre)
    for col in gdf.columns:
        if col != gdf.geometry.name:
            col_norm = gdf[col].astype(str).apply(normalizar_texto)
            coincidencias = gdf[col_norm.str.contains(region_norm, na=False, regex=False)]
            if not coincidencias.empty:
                return coincidencias
    return gdf.iloc[0:0]


print(f"🔄 Cargando base de datos desde '{path_csv}'...")
gdf_regiones_raw = gpd.read_file(carpeta_admin / "Regiones_Chile.geojson")
gdf_provincias_raw = gpd.read_file(carpeta_admin / "Provincias_Chile.geojson")
df_csv = pd.read_csv(path_csv, low_memory=False)

# Sanitización de datos administrativos
df_csv["Provincia"] = df_csv["Provincia"].replace(r'^\s*$', np.nan, regex=True).fillna("Sin Provincia")
df_csv["Region_Norm"] = df_csv["Region"].apply(normalizar_texto)
df_csv["Provincia_Norm"] = df_csv["Provincia"].apply(normalizar_texto)

# Conversión y respaldo de coordenadas UTM originales
df_csv["UTM_Norte"] = pd.to_numeric(df_csv["UTM_Norte"], errors="coerce")
df_csv["UTM_Este"] = pd.to_numeric(df_csv["UTM_Este"], errors="coerce")
df_csv["Huso"] = pd.to_numeric(df_csv["Huso"], errors="coerce")

df_csv["UTM_Norte_Orig"] = df_csv["UTM_Norte"].copy()
df_csv["UTM_Este_Orig"] = df_csv["UTM_Este"].copy()

# Cálculo de Caudal Derecho (l/s) como el promedio de los 12 meses
meses_cols = [
    'Caudal_Ene_ls', 'Caudal_Feb_ls', 'Caudal_Mar_ls', 'Caudal_Abr_ls',
    'Caudal_May_ls', 'Caudal_Jun_ls', 'Caudal_Jul_ls', 'Caudal_Ago_ls',
    'Caudal_Sep_ls', 'Caudal_Oct_ls', 'Caudal_Nov_ls', 'Caudal_Dic_ls'
]
cols_existentes = [c for c in meses_cols if c in df_csv.columns]
if cols_existentes:
    df_caudales = df_csv[cols_existentes].apply(pd.to_numeric, errors='coerce')
    df_csv["Caudal_Derecho_ls"] = df_caudales.mean(axis=1, skipna=True)
else:
    df_csv["Caudal_Derecho_ls"] = np.nan

# Desplazamiento aleatorio (+-10 metros) para evitar superposición visual de puntos
filas_dup = df_csv.duplicated(subset=["UTM_Este", "UTM_Norte", "Huso"], keep=False)
if filas_dup.any():
    ruido_este = np.random.uniform(-10, 10, size=filas_dup.sum())
    ruido_norte = np.random.uniform(-10, 10, size=filas_dup.sum())
    df_csv.loc[filas_dup, "UTM_Este"] += ruido_este
    df_csv.loc[filas_dup, "UTM_Norte"] += ruido_norte

# Reproyección a WGS84 (EPSG:4326)
gdfs_obras_nac = []
for huso in [18, 19]:
    df_h = df_csv[df_csv["Huso"] == huso]
    if not df_h.empty:
        epsg = 32718 if huso == 18 else 32719
        gdf_h = gpd.GeoDataFrame(
            df_h,
            geometry=gpd.points_from_xy(df_h["UTM_Este"], df_h["UTM_Norte"]),
            crs=f"EPSG:{epsg}"
        ).to_crs(epsg=4326)
        gdfs_obras_nac.append(gdf_h)

gdf_obras_nac = pd.concat(gdfs_obras_nac, ignore_index=True) if gdfs_obras_nac else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
gdf_obras_nac["latitud"] = gdf_obras_nac.geometry.y
gdf_obras_nac["longitud"] = gdf_obras_nac.geometry.x

# Inicializar Mapa Base Folium
mapa_web = folium.Map(location=[-35.6751, -71.5430], zoom_start=4, tiles=None)
folium.TileLayer(tiles='OpenStreetMap', name='OpenStreetMap', overlay=False, control=True, show=True).add_to(mapa_web)
folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Híbrido (Google)', overlay=False, control=True, show=False).add_to(mapa_web)

region_dict_js = {}
prov_dict_js = {}
options_html = ""


def format_campo(val):
    """Devuelve 'nan' si el valor es nulo o vacío; de lo contrario su representación en texto."""
    if pd.isna(val) or val is None:
        return "nan"
    s = str(val).strip()
    return s if s != "" else "nan"


def crear_popup_obra(row):
    cod = str(row.get("Codigo_Obra", "S/C")).strip()
    nat = format_campo(row.get("Naturaleza", "Subterránea"))
    color_titulo = "#0056b3" if "superficial" in nat.lower() else "#212529"

    usuario = format_campo(row.get("Usuario"))
    rut_usuario = format_campo(row.get("RUT_Usuario"))
    tipo_persona = format_campo(row.get("Tipo_Persona"))
    comuna = format_campo(row.get("Comuna"))
    provincia = format_campo(row.get("Provincia"))
    region = format_campo(row.get("Region"))
    cuenca = format_campo(row.get("Cuenca"))

    # Coordenadas UTM originales en formato entero
    norte_orig = row.get("UTM_Norte_Orig")
    este_orig = row.get("UTM_Este_Orig")
    utm_norte = f"{int(round(norte_orig))}" if pd.notnull(norte_orig) else "nan"
    utm_este = f"{int(round(este_orig))}" if pd.notnull(este_orig) else "nan"

    fecha_reg = format_campo(row.get("Fecha_Registro_DGA"))

    # Caudal de derecho formateado (nan si no hay datos por mes)
    val_caudal = row.get("Caudal_Derecho_ls")
    if pd.isna(val_caudal):
        caudal_der = "nan"
    else:
        caudal_der = f"{round(float(val_caudal), 2)}"

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; min-width: 250px; line-height: 1.5;">
        <b style="color: {color_titulo}; font-size: 13px;">{cod}</b><br>
        <b>Usuario:</b> {usuario}<br>
        <b>Rut Usuario:</b> {rut_usuario}<br>
        <b>Tipo Persona:</b> {tipo_persona}<br>
        <b>Naturaleza:</b> {nat}<br>
        <b>Comuna:</b> {comuna}<br>
        <b>Provincia:</b> {provincia}<br>
        <b>Region:</b> {region}<br>
        <b>Cuenca:</b> {cuenca}<br>
        <b>UTM Norte:</b> {utm_norte}<br>
        <b>UTM Este:</b> {utm_este}<br>
        <b>Fecha Registro DGA:</b> {fecha_reg}<br>
        <b>Caudal Derecho (l/s):</b> {caudal_der}

        <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #e2e8f0; text-align: center;">
            <a href="{RENDER_URL}/visor?codigo={cod}" 
               target="_blank" 
               style="display: block; background-color: #0284c7; color: white; padding: 7px 10px; font-size: 11px; font-weight: bold; text-decoration: none; border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.15);">
                📥 Descargar Mediciones MEE
            </a>
        </div>
    </div>
    """


print("🛠️ Generando capas y marcadores con metadatos actualizados...")

for region_nom, provincias in regiones_provincias.items():
    reg_key = normalizar_texto(region_nom).replace(' ', '_')
    capa_reg = filtrar_layer_local(gdf_regiones_raw, region_nom)

    target_norm_reg = normalizar_texto(region_nom)
    gdf_obras_reg = gdf_obras_nac[gdf_obras_nac["Region_Norm"].str.contains(target_norm_reg, na=False)].copy()

    if capa_reg.empty and gdf_obras_reg.empty:
        continue

    xmin, ymin, xmax, ymax = capa_reg.total_bounds if not capa_reg.empty else [gdf_obras_reg.longitud.min(), gdf_obras_reg.latitud.min(), gdf_obras_reg.longitud.max(), gdf_obras_reg.latitud.max()]

    region_dict_js[reg_key] = {
        "name": region_nom,
        "bounds": [[ymin, xmin], [ymax, xmax]],
        "provinces": [],
        "border_var": f"fg_border_{reg_key}"
    }
    options_html += f'<option value="{reg_key}">{region_nom}</option>\n'

    # Polígono regional estático
    fg_border = folium.FeatureGroup(name=f"Límite {region_nom}", overlay=True, show=True, control=False)
    if not capa_reg.empty:
        folium.GeoJson(
            capa_reg,
            interactive=False,
            style_function=lambda x: {"color": "black", "fillOpacity": 0, "weight": 2.2}
        ).add_to(fg_border)
    fg_border.add_to(mapa_web)

    obras_asignadas_idx = set()

    for prov_nom in provincias:
        prov_key = normalizar_texto(prov_nom).replace(' ', '_') + "_" + reg_key
        capa_prov = filtrar_layer_local(gdf_provincias_raw, prov_nom)

        target_norm_prov = normalizar_texto(prov_nom)
        gdf_obras_prov = gdf_obras_reg[gdf_obras_reg["Provincia_Norm"].str.contains(target_norm_prov, na=False)].copy()
        obras_asignadas_idx.update(gdf_obras_prov.index)

        fg_prov = folium.FeatureGroup(name=f"Prov. {prov_nom}", overlay=True, show=True, control=False)

        if not capa_prov.empty:
            folium.GeoJson(
                capa_prov,
                interactive=False,
                style_function=lambda x: {"color": "#475569", "fillOpacity": 0.02, "weight": 1.2, "dashArray": "4, 4"}
            ).add_to(fg_prov)
            pxmin, pymin, pxmax, pymax = capa_prov.total_bounds
            p_bounds = [[pymin, pxmin], [pymax, pxmax]]
        else:
            p_bounds = region_dict_js[reg_key]["bounds"]

        # Marcadores con el nuevo popup
        for _, row in gdf_obras_prov.iterrows():
            es_sup = "superficial" in str(row.get("Naturaleza", "")).lower()
            folium.CircleMarker(
                location=[row["latitud"], row["longitud"]],
                radius=5,
                color="#0056b3" if es_sup else "#212529",
                fill=True,
                fill_color="#007bff" if es_sup else "#6c757d",
                fill_opacity=0.85,
                weight=1.5,
                tooltip=f"<b>{row.get('Codigo_Obra', '')}</b> - {row.get('Usuario', '')}",
                popup=folium.Popup(crear_popup_obra(row), max_width=340)
            ).add_to(fg_prov)

        fg_prov.add_to(mapa_web)
        prov_dict_js[prov_key] = {"name": prov_nom, "var": fg_prov.get_name(), "bounds": p_bounds}
        region_dict_js[reg_key]["provinces"].append(prov_key)

    # Obras huérfanas sin provincia asignada
    obras_huerfanas = gdf_obras_reg[~gdf_obras_reg.index.isin(obras_asignadas_idx)]
    if not obras_huerfanas.empty:
        h_key = "sin_prov_" + reg_key
        fg_huerfana = folium.FeatureGroup(name="Sin Provincia", overlay=True, show=True, control=False)
        for _, row in obras_huerfanas.iterrows():
            es_sup = "superficial" in str(row.get("Naturaleza", "")).lower()
            folium.CircleMarker(
                location=[row["latitud"], row["longitud"]],
                radius=5,
                color="#0056b3" if es_sup else "#212529",
                fill=True,
                fill_color="#007bff" if es_sup else "#6c757d",
                fill_opacity=0.85,
                weight=1.5,
                tooltip=f"<b>{row.get('Codigo_Obra', '')}</b> - {row.get('Usuario', '')}",
                popup=folium.Popup(crear_popup_obra(row), max_width=340)
            ).add_to(fg_huerfana)
        fg_huerfana.add_to(mapa_web)
        prov_dict_js[h_key] = {"name": "Obras sin Provincia", "var": fg_huerfana.get_name(), "bounds": region_dict_js[reg_key]["bounds"]}
        region_dict_js[reg_key]["provinces"].append(h_key)

# Controles interactivos JavaScript
menu_control_html = f"""
<div style="position: fixed; top: 12px; left: 60px; z-index: 1000; background: white; padding: 10px 14px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.3); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; min-width: 240px;">
    <label for="regionSelect" style="font-weight: bold; font-size: 13px; color: #333;">🗺️ Seleccionar Región:</label><br>
    <select id="regionSelect" onchange="cambiarRegion(this.value)" style="margin-top: 6px; margin-bottom: 12px; padding: 6px; font-size: 12px; border-radius: 4px; border: 1px solid #ccc; width: 100%; cursor: pointer;">
        <option value="">-- Todo el País --</option>
        {options_html}
    </select>
    <br>
    <label for="provinciaSelect" style="font-weight: bold; font-size: 13px; color: #333;">📍 Seleccionar Provincia:</label><br>
    <select id="provinciaSelect" onchange="cambiarProvincia(this.value)" style="margin-top: 6px; padding: 6px; font-size: 12px; border-radius: 4px; border: 1px solid #ccc; width: 100%; cursor: pointer; background-color: #f8f9fa;" disabled>
        <option value="">-- Todas las Provincias --</option>
    </select>
</div>

<script>
var regionDict = {json.dumps(region_dict_js)};
var provDict = {json.dumps(prov_dict_js)};

function mostrarTodo() {{
    var map = {mapa_web.get_name()};
    for (var r in regionDict) {{
        var fgBorder = window[regionDict[r].border_var];
        if (fgBorder && !map.hasLayer(fgBorder)) map.addLayer(fgBorder);
        regionDict[r].provinces.forEach(function(pKey) {{
            var fgProv = window[provDict[pKey].var];
            if (fgProv && !map.hasLayer(fgProv)) map.addLayer(fgProv);
        }});
    }}
}}

function ocultarTodo() {{
    var map = {mapa_web.get_name()};
    for (var r in regionDict) {{
        var fgBorder = window[regionDict[r].border_var];
        if (fgBorder && map.hasLayer(fgBorder)) map.removeLayer(fgBorder);
        regionDict[r].provinces.forEach(function(pKey) {{
            var fgProv = window[provDict[pKey].var];
            if (fgProv && map.hasLayer(fgProv)) map.removeLayer(fgProv);
        }});
    }}
}}

function cambiarRegion(regKey) {{
    var map = {mapa_web.get_name()};
    var provSelect = document.getElementById("provinciaSelect");
    provSelect.innerHTML = '<option value="">-- Todas las Provincias --</option>';
    ocultarTodo();

    if (regKey === "") {{
        provSelect.disabled = true;
        provSelect.style.backgroundColor = "#f8f9fa";
        mostrarTodo();
        map.setView([-35.6751, -71.5430], 4);
    }} else {{
        provSelect.disabled = false;
        provSelect.style.backgroundColor = "#ffffff";
        var fgBorder = window[regionDict[regKey].border_var];
        if (fgBorder && !map.hasLayer(fgBorder)) map.addLayer(fgBorder);

        regionDict[regKey].provinces.forEach(function(pKey) {{
            var pData = provDict[pKey];
            var fgProv = window[pData.var];
            if (fgProv && !map.hasLayer(fgProv)) map.addLayer(fgProv);
            var opt = document.createElement("option");
            opt.value = pKey;
            opt.text = pData.name;
            provSelect.add(opt);
        }});
        map.fitBounds(regionDict[regKey].bounds);
    }}
}}

function cambiarProvincia(provKey) {{
    var map = {mapa_web.get_name()};
    var regKey = document.getElementById("regionSelect").value;
    if (!regKey) return;
    ocultarTodo();

    var fgBorder = window[regionDict[regKey].border_var];
    if (fgBorder && !map.hasLayer(fgBorder)) map.addLayer(fgBorder);

    if (provKey === "") {{
        regionDict[regKey].provinces.forEach(function(pKey) {{
            var fgProv = window[provDict[pKey].var];
            if (fgProv && !map.hasLayer(fgProv)) map.addLayer(fgProv);
        }});
        map.fitBounds(regionDict[regKey].bounds);
    }} else {{
        var fgProv = window[provDict[provKey].var];
        if (fgProv && !map.hasLayer(fgProv)) map.addLayer(fgProv);
        map.fitBounds(provDict[provKey].bounds);
    }}
}}
</script>
"""

leyenda_html = """
<div style="position: fixed; bottom: 30px; right: 10px; z-index: 1000; background-color: white; padding: 10px 14px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.3); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px;">
    <b style="font-size: 13px; color: #333;">Naturaleza de Obra</b>
    <div style="display: flex; align-items: center; margin-top: 6px;">
        <span style="height: 12px; width: 12px; background-color: #007bff; border: 1.5px solid #0056b3; border-radius: 50%; display: inline-block; margin-right: 8px;"></span>
        <span>Superficial</span>
    </div>
    <div style="display: flex; align-items: center; margin-top: 4px;">
        <span style="height: 12px; width: 12px; background-color: #6c757d; border: 1.5px solid #212529; border-radius: 50%; display: inline-block; margin-right: 8px;"></span>
        <span>Subterránea</span>
    </div>
    <hr style="margin: 8px 0 6px 0; border: 0; border-top: 1px solid #eee;">
    <div style="font-size: 11px; color: #666; font-weight: normal;">DGA - Monitoreo de Extracciones</div>
</div>
"""

mapa_web.get_root().html.add_child(Element(menu_control_html))
mapa_web.get_root().html.add_child(Element(leyenda_html))
folium.LayerControl(collapsed=False).add_to(mapa_web)

archivo_salida = "index.html"
mapa_web.save(archivo_salida)
print(f"\n🚀 ¡Éxito! Mapa nacional interactivo MEE generado en '{archivo_salida}'.")
