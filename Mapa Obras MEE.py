import json
import re
import unicodedata
from pathlib import Path
from branca.element import Element
import geopandas as gpd
import numpy as np
import pandas as pd
import folium

# **1. Lista de Regiones de Chile**
regiones_chile = [
    "Arica y Parinacota", "Tarapaca", "Antofagasta", "Atacama", "Coquimbo", "Valparaiso", 
    "Metropolitana", "O'Higgins", "Maule", "Nuble", "Bio Bio", "Araucania", 
    "Los Rios", "Los Lagos", "Aysen", "Magallanes"
]

carpeta_admin = Path("divisiones_admin")
path_csv = "01-07-2026 Obras MEE.csv"

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

# **4. Cargar, procesar y aplicar Jittering de +-10m a obras duplicadas**
print("🔄 Cargando bases de datos nacionales...")
try:
    gdf_regiones_raw = gpd.read_file(carpeta_admin / "Regiones.geojson")
    gdf_comunas_raw = gpd.read_file(carpeta_admin / "Comunas.geojson")
    df_csv = pd.read_csv(path_csv)
    print("✅ Archivos base cargados exitosamente.")
except Exception as e:
    print(f"❌ Error al cargar los archivos: {e}")

df_csv["Region_Norm"] = df_csv["Region"].apply(normalizar_texto)
df_csv["UTM_Norte"] = pd.to_numeric(df_csv["UTM_Norte"], errors="coerce")
df_csv["UTM_Este"] = pd.to_numeric(df_csv["UTM_Este"], errors="coerce")
df_csv["Huso"] = pd.to_numeric(df_csv["Huso"], errors="coerce")

# Convertir explícitamente a float
df_csv["UTM_Este"] = df_csv["UTM_Este"].astype(float)
df_csv["UTM_Norte"] = df_csv["UTM_Norte"].astype(float)

# --- APLICACIÓN DE DESPLAZAMIENTO ALEATORIO (+-10 METROS) ---
filas_duplicadas = df_csv.duplicated(subset=["UTM_Este", "UTM_Norte", "Huso"], keep=False)

if filas_duplicadas.any():
    ruido_este = np.random.uniform(-10, 10, size=filas_duplicadas.sum())
    ruido_norte = np.random.uniform(-10, 10, size=filas_duplicadas.sum())
    
    df_csv.loc[filas_duplicadas, "UTM_Este"] += ruido_este
    df_csv.loc[filas_duplicadas, "UTM_Norte"] += ruido_norte
    print(f"⚡ Se aplicó dispersión de +-10m a {filas_duplicadas.sum()} obras con coordenadas duplicadas.")

# Reproyección UTM a WGS84 para todo el país
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
options_html = ""

# **6. Función de Estilo por Naturaleza y Construcción de Capas**
def estilo_naturaleza(feature):
    nat = str(feature["properties"].get("Naturaleza", "")).lower()
    if "superficial" in nat:
        return {
            "color": "#0056b3",      # Borde Azul DGA
            "fillColor": "#007bff",  # Relleno Azul DGA
            "fillOpacity": 0.8
        }
    else:
        return {
            "color": "#212529",      # Borde cercano a negro
            "fillColor": "#6c757d",  # Relleno Gris
            "fillOpacity": 0.8
        }

print("🛠️ Generando capas regionales...")

for region_nom in regiones_chile:
    reg_key = normalizar_texto(region_nom).replace(' ', '_')
    capa_reg = filtrar_layer_local(gdf_regiones_raw, region_nom)
    capa_com = filtrar_layer_local(gdf_comunas_raw, region_nom)
    
    target_norm = normalizar_texto(region_nom)
    gdf_obras_reg = gdf_obras_nac[gdf_obras_nac["Region_Norm"].str.contains(target_norm, na=False)].copy()

    if capa_reg.empty:
        print(f"⚠️ No se encontraron límites para: {region_nom}")
        continue

    # Cargar capas activas por defecto
    fg = folium.FeatureGroup(name=f"Región {region_nom}", overlay=True, show=True)

    # Dibujar Comunas
    if not capa_com.empty:
        capa_com.explore(
            m=fg, color="#333333", style_kwds={"fillOpacity": 0.04, "weight": 1.2, "dashArray": "3, 3"},
            tooltip=False, popup=False, highlight=False
        )

    # Dibujar Límite Regional
    capa_reg.explore(
        m=fg, color="black", style_kwds={"fillOpacity": 0, "weight": 2.5},
        tooltip=False, popup=False, highlight=False
    )

    # Dibujar Obras con explore() y estilo personalizado
    if not gdf_obras_reg.empty:
        gdf_obras_reg.drop(columns=["Region_Norm"], errors="ignore").explore(
            m=fg,
            style_kwds={"style_function": estilo_naturaleza},
            marker_kwds={"radius": 5},
            tooltip=["Codigo_Obra", "Usuario", "Comuna", "Naturaleza", "Ultimo_Caudal_Medido_ls"],
            popup=True,
            legend=False
        )

    fg.add_to(mapa_web)

    xmin, ymin, xmax, ymax = capa_reg.total_bounds
    region_dict_js[reg_key] = {
        "var": fg.get_name(),
        "bounds": [[ymin, xmin], [ymax, xmax]]
    }
    options_html += f'<option value="{reg_key}">{region_nom}</option>\n'

# **7. Inyectar Menú Desplegable con JavaScript (Soporta ver todo el país)**
menu_control_html = f"""
<div style="position: fixed; top: 12px; left: 60px; z-index: 1000; background: white; padding: 10px 14px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.3); font-family: Arial, sans-serif;">
    <label for="regionSelect" style="font-weight: bold; font-size: 13px; color: #333;">🗺️ Seleccionar Región:</label><br>
    <select id="regionSelect" onchange="filtrarRegion(this.value)" style="margin-top: 6px; padding: 6px; font-size: 12px; border-radius: 4px; border: 1px solid #ccc; width: 220px; cursor: pointer;">
        <option value="">-- Seleccionar Región --</option>
        {options_html}
    </select>
</div>

<script>
var regionDict = {json.dumps(region_dict_js)};

function filtrarRegion(selectedKey) {{
    var map = {mapa_web.get_name()};

    // Si selecciona "-- Mostrar Todo el País --"
    if (selectedKey === "") {{
        for (var key in regionDict) {{
            var fgVarName = regionDict[key].var;
            var fg = window[fgVarName];
            if (fg && !map.hasLayer(fg)) {{
                map.addLayer(fg);
            }}
        }}
        map.setView([-35.6751, -71.5430], 4);
    }} else {{
        // Si selecciona una región específica
        for (var key in regionDict) {{
            var fgVarName = regionDict[key].var;
            var fg = window[fgVarName];

            if (key === selectedKey) {{
                if (fg && !map.hasLayer(fg)) {{
                    map.addLayer(fg);
                }}
                map.fitBounds(regionDict[key].bounds);
            }} else {{
                if (fg && map.hasLayer(fg)) {{
                    map.removeLayer(fg);
                }}
            }}
        }}
    }}
}}
</script>
"""

mapa_web.get_root().html.add_child(Element(menu_control_html))
folium.LayerControl(collapsed=False).add_to(mapa_web)

# **8. Inyectar Leyenda de Simbología de Naturaleza**
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
</div>
"""

mapa_web.get_root().html.add_child(Element(leyenda_html))

# **9. Guardar Mapa Final**
archivo_salida = "mapa_nacional_interactivo.html"
mapa_web.save(archivo_salida)
print(f"\n🚀 ¡Éxito! Mapa nacional interactivo generado correctamente en '{archivo_salida}'.")
