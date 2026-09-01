import json
import re
import unicodedata
from pathlib import Path
from branca.element import Element
import geopandas as gpd
import numpy as np
import pandas as pd
import folium

# **1. Diccionario de Regiones y sus Provincias**
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

carpeta_admin = Path("divisiones_admin")
path_csv = "Listado_Obras_MEE.csv"

# **2. Normalizador de Texto**
def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto_str = str(texto).lower()
    texto_str = ''.join(c for c in unicodedata.normalize('NFKD', texto_str) if unicodedata.category(c) != 'Mn')
    texto_str = re.sub(r'[^a-z0-9\s]', ' ', texto_str)
    return ' '.join(texto_str.split())

# **3. Función para filtrar capas vectoriales locales**
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

# **4. Cargar y procesar capas (Con Límite Provincial y Columna Provincia)**
print("🔄 Cargando bases de datos nacionales...")
try:
    gdf_regiones_raw = gpd.read_file(carpeta_admin / "Regiones_Chile.geojson")
    gdf_provincias_raw = gpd.read_file(carpeta_admin / "Provincias_Chile.geojson") # <-- CARGA DE PROVINCIAS
    df_csv = pd.read_csv(path_csv)
    print("✅ Archivos base cargados exitosamente.")
except Exception as e:
    print(f"❌ Error al cargar los archivos: {e}")

# Manejo de obras "Sin Provincia"
df_csv["Provincia"] = df_csv["Provincia"].replace(r'^\s*$', np.nan, regex=True)
df_csv["Provincia"] = df_csv["Provincia"].fillna("Sin Provincia")

df_csv["Region_Norm"] = df_csv["Region"].apply(normalizar_texto)
df_csv["Provincia_Norm"] = df_csv["Provincia"].apply(normalizar_texto)

df_csv["UTM_Norte"] = pd.to_numeric(df_csv["UTM_Norte"], errors="coerce").astype(float)
df_csv["UTM_Este"] = pd.to_numeric(df_csv["UTM_Este"], errors="coerce").astype(float)
df_csv["Huso"] = pd.to_numeric(df_csv["Huso"], errors="coerce")

# --- APLICACIÓN DE DESPLAZAMIENTO ALEATORIO (+-10 METROS) ---
filas_duplicadas = df_csv.duplicated(subset=["UTM_Este", "UTM_Norte", "Huso"], keep=False)
if filas_duplicadas.any():
    ruido_este = np.random.uniform(-10, 10, size=filas_duplicadas.sum())
    ruido_norte = np.random.uniform(-10, 10, size=filas_duplicadas.sum())
    df_csv.loc[filas_duplicadas, "UTM_Este"] += ruido_este
    df_csv.loc[filas_duplicadas, "UTM_Norte"] += ruido_norte

gdfs_obras_nac = []
for huso in [18, 19]:
    df_huso = df_csv[df_csv["Huso"] == huso]
    if not df_huso.empty:
        epsg_code = 32718 if huso == 18 else 32719
        gdf_h = gpd.GeoDataFrame(
            df_huso,
            geometry=gpd.points_from_xy(df_huso["UTM_Este"], df_huso["UTM_Norte"]),
            crs=f"EPSG:{epsg_code}"
        ).to_crs(epsg=4326)
        gdfs_obras_nac.append(gdf_h)

gdf_obras_nac = pd.concat(gdfs_obras_nac, ignore_index=True) if gdfs_obras_nac else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

# **5. Inicializar Mapa Nacional**
mapa_web = folium.Map(location=[-35.6751, -71.5430], zoom_start=4, tiles=None)
folium.TileLayer(tiles='OpenStreetMap', name='OpenStreetMap', overlay=False, control=True, show=True).add_to(mapa_web)
folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Híbrido (Google)', overlay=False, control=True, show=False).add_to(mapa_web)

region_dict_js = {}
prov_dict_js = {}
options_html = ""

def estilo_naturaleza(feature):
    nat = str(feature["properties"].get("Naturaleza", "")).lower()
    if "superficial" in nat:
        return {"color": "#0056b3", "fillColor": "#007bff", "fillOpacity": 0.8}
    else:
        return {"color": "#212529", "fillColor": "#6c757d", "fillOpacity": 0.8}

print("🛠️ Generando capas regionales y provinciales...")

# **6. Construcción de Capas por Región y Provincia**
for region_nom, provincias in regiones_provincias.items():
    reg_key = normalizar_texto(region_nom).replace(' ', '_')
    capa_reg = filtrar_layer_local(gdf_regiones_raw, region_nom)
    
    target_norm_reg = normalizar_texto(region_nom)
    gdf_obras_reg = gdf_obras_nac[gdf_obras_nac["Region_Norm"].str.contains(target_norm_reg, na=False)].copy()

    if capa_reg.empty:
        continue

    xmin, ymin, xmax, ymax = capa_reg.total_bounds
    
    region_dict_js[reg_key] = {
        "name": region_nom,
        "bounds": [[ymin, xmin], [ymax, xmax]],
        "provinces": [],
        "border_var": f"fg_border_{reg_key}"
    }
    options_html += f'<option value="{reg_key}">{region_nom}</option>\n'

    fg_border = folium.FeatureGroup(name=f"Límite {region_nom}", overlay=True, show=True, control=False)
    capa_reg.explore(m=fg_border, color="black", style_kwds={"fillOpacity": 0, "weight": 2.5}, tooltip=False, popup=False, highlight=False)
    fg_border.add_to(mapa_web)

    obras_asignadas_idx = set()

    for prov_nom in provincias:
        prov_key = normalizar_texto(prov_nom).replace(' ', '_') + "_" + reg_key
        
        # Obtener Polígono de la Provincia
        capa_prov = filtrar_layer_local(gdf_provincias_raw, prov_nom)
        
        # Filtrar Obras mediante el atributo Provincia_Norm del CSV
        target_norm_prov = normalizar_texto(prov_nom)
        gdf_obras_prov = gdf_obras_reg[gdf_obras_reg["Provincia_Norm"].str.contains(target_norm_prov, na=False)].copy()
        
        obras_asignadas_idx.update(gdf_obras_prov.index)

        fg_prov = folium.FeatureGroup(name=f"Prov. {prov_nom}", overlay=True, show=True, control=False)
        
        if not capa_prov.empty:
            capa_prov.explore(m=fg_prov, color="#333333", style_kwds={"fillOpacity": 0.04, "weight": 1.5, "dashArray": "5, 5"}, tooltip=False, popup=False, highlight=False)
            pxmin, pymin, pxmax, pymax = capa_prov.total_bounds
            p_bounds = [[pymin, pxmin], [pymax, pxmax]]
        else:
            p_bounds = region_dict_js[reg_key]["bounds"]

        if not gdf_obras_prov.empty:
            # Agregamos "Provincia" al Tooltip para que se pueda visualizar
            gdf_obras_prov.drop(columns=["Region_Norm", "Provincia_Norm", "Tiene_Derecho_Glosa", "Tiene_Medicion_Glosa", "Tipo_Medidor", "Tiene_Telemetria"], errors="ignore").explore(
                m=fg_prov, style_kwds={"style_function": estilo_naturaleza}, marker_kwds={"radius": 5},
                tooltip=["Codigo_Obra", "Usuario", "Provincia", "Naturaleza", "Ultimo_Caudal_Medido_ls"],
                popup=True, legend=False
            )

        fg_prov.add_to(mapa_web)
        
        prov_dict_js[prov_key] = {
            "name": prov_nom,
            "var": fg_prov.get_name(),
            "bounds": p_bounds
        }
        region_dict_js[reg_key]["provinces"].append(prov_key)

    # Capturar obras que tienen atributo vacío ("Sin Provincia")
    obras_huerfanas = gdf_obras_reg[~gdf_obras_reg.index.isin(obras_asignadas_idx)]
    if not obras_huerfanas.empty:
        h_key = "sin_prov_" + reg_key
        fg_huerfana = folium.FeatureGroup(name="Sin Provincia", overlay=True, show=True, control=False)
        obras_huerfanas.drop(columns=["Region_Norm", "Provincia_Norm", "Tiene_Derecho_Glosa", "Tiene_Medicion_Glosa", "Tipo_Medidor", "Tiene_Telemetria"], errors="ignore").explore(
            m=fg_huerfana, style_kwds={"style_function": estilo_naturaleza}, marker_kwds={"radius": 5},
            tooltip=["Codigo_Obra", "Usuario", "Provincia", "Naturaleza", "Ultimo_Caudal_Medido_ls"], 
            popup=True, legend=False
        )
        fg_huerfana.add_to(mapa_web)
        prov_dict_js[h_key] = {"name": "Obras sin Provincia", "var": fg_huerfana.get_name(), "bounds": region_dict_js[reg_key]["bounds"]}
        region_dict_js[reg_key]["provinces"].append(h_key)

# **7. Inyectar Menús Desplegables con JavaScript**
menu_control_html = f"""
<div style="position: fixed; top: 12px; left: 60px; z-index: 1000; background: white; padding: 10px 14px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.3); font-family: Arial, sans-serif; min-width: 240px;">
    
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

mapa_web.get_root().html.add_child(Element(menu_control_html))
folium.LayerControl(collapsed=False).add_to(mapa_web)

# **8. Inyectar Leyenda de Simbología de Naturaleza con Fecha al Pie**
leyenda_html = """
<div style="position: fixed; bottom: 30px; right: 10px; z-index: 1000; background-color: white; padding: 10px 14px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.3); font-family: Arial, sans-serif; font-size: 12px;">
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
    <div style="font-size: 11px; color: #666; font-weight: normal;">Actualización: Julio 2026</div>
</div>
"""

mapa_web.get_root().html.add_child(Element(leyenda_html))

# **9. Guardar Mapa Final**
archivo_salida = "Mapa_Obras_MEE.html"
mapa_web.save(archivo_salida)
print(f"\n🚀 ¡Éxito! Mapa nacional interactivo con límites provinciales generado en '{archivo_salida}'.")
