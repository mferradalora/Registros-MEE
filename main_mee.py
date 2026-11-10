#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Servicio API REST y visor de extracciones efectivas MEE (DGA Chile).
Optimizado con indexación en memoria O(1), validación de parámetros (regex),
manejo de concurrencia y exportaciones para MODFLOW y WEAP.
"""

import os
import re
import datetime
from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.responses import HTMLResponse
import pandas as pd

from database_mee import (
    inicializar_db,
    guardar_mediciones,
    consultar_datos_locales,
    verificar_necesidad_scraping,
    registrar_intento_scraping,
    consultar_extracciones_mensuales
)
from extractor_mee import obtener_mediciones_obra

inicializar_db()
app = FastAPI(
    title="Servicio MEE DGA - Hidrogeología & Hidrología",
    description="API de consulta, extracción y normalización de extracciones MEE para modelación hidrogeológica y balance hídrico."
)

# Patrón de validación oficial DGA: 'OB-XXXX-XXX' (obras) o 'OR-XXXX-XXX' (restituciones)
PATRON_CODIGO_OBRA = re.compile(r'^(OB|OR)-\d{3,5}-\d{1,5}$')

RUTA_CATALOGO = "data/catalogo_obras_mee.csv"
cat_dict = {}

if os.path.exists(RUTA_CATALOGO):
    df_cat = pd.read_csv(RUTA_CATALOGO, low_memory=False)
    df_cat["Codigo_Obra_Upper"] = df_cat["Codigo_Obra"].fillna("").astype(str).str.strip().str.upper()
    df_cat["ID_Obra"] = pd.to_numeric(df_cat["ID_Obra"], errors="coerce").fillna(0).astype(int)

    if "Fecha_Registro_DGA" in df_cat.columns:
        df_cat["Fecha_Clean"] = pd.to_datetime(
            df_cat["Fecha_Registro_DGA"], dayfirst=True, errors="coerce"
        ).dt.date
    else:
        df_cat["Fecha_Clean"] = datetime.date(2020, 1, 1)

    df_cat["Fecha_Clean"] = df_cat["Fecha_Clean"].fillna(datetime.date(2020, 1, 1))

    # Indexación a diccionario nativo para búsquedas O(1)
    cat_dict = (
        df_cat.drop_duplicates(subset=["Codigo_Obra_Upper"])
        .set_index("Codigo_Obra_Upper")
        .to_dict(orient="index")
    )
    print(f"✅ Catálogo MEE indexado en memoria: {len(cat_dict):,} obras desde '{RUTA_CATALOGO}'.", flush=True)
else:
    print(f"⚠️ Alerta: No se encontró el archivo en '{RUTA_CATALOGO}'. Verifica el directorio de ejecución.", flush=True)

def validar_codigo(codigo: str) -> str:
    """Valida y normaliza el identificador de la obra antes de cualquier consulta."""
    cod = codigo.strip().upper()
    if not PATRON_CODIGO_OBRA.match(cod):
        raise HTTPException(
            status_code=400,
            detail=f"Formato de código inválido: '{codigo}'. Debe seguir la nomenclatura DGA (ej. 'OB-1501-85')."
        )
    return cod


def obtener_info_obra(codigo_obra: str) -> dict:
    """Obtiene metadatos administrativos en O(1)."""
    cod = codigo_obra.strip().upper()
    r = cat_dict.get(cod)
    if r:
        return {
            "codigo_obra": cod,
            "id_obra": int(r["ID_Obra"]),
            "usuario": str(r.get("Usuario", "S/I")),
            "rut": str(r.get("RUT_Usuario", "")),
            "naturaleza": str(r.get("Naturaleza", "")),
            "region": str(r.get("Region", "")),
            "comuna": str(r.get("Comuna", "")),
            "fecha_registro": r.get("Fecha_Clean", datetime.date(2020, 1, 1))
        }
    return {
        "codigo_obra": cod,
        "id_obra": 0,
        "usuario": "Obra no identificada",
        "rut": "",
        "naturaleza": "",
        "region": "",
        "comuna": "",
        "fecha_registro": datetime.date(2020, 1, 1)
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/api/info_obra")
def api_info(codigo: str = Query(...)):
    cod = validar_codigo(codigo)
    info = obtener_info_obra(cod)
    info["fecha_registro"] = info["fecha_registro"].strftime("%d/%m/%Y")
    return info


@app.get("/api/datos")
def api_datos(codigo: str = Query(...)):
    cod = validar_codigo(codigo)
    info = obtener_info_obra(cod)

    if info["id_obra"] == 0:
        raise HTTPException(status_code=404, detail=f"La obra '{cod}' no figura en el catálogo nacional.")

    if verificar_necesidad_scraping(cod):
        print(f"📡 Sincronizando con DGA SNIA para obra {cod}...", flush=True)
        try:
            df_nuevo = obtener_mediciones_obra(cod, info["id_obra"], info["fecha_registro"])
            if not df_nuevo.empty:
                guardar_mediciones(df_nuevo)
        except Exception as e:
            print(f"⚠️ Error al conectar con servicio DGA para {cod}: {e}", flush=True)
        finally:
            registrar_intento_scraping(cod)

    df_res = consultar_datos_locales(cod)
    if df_res.empty:
        raise HTTPException(status_code=404, detail="No se encontraron mediciones registradas en el portal MEE.")

    df_res["usuario"] = info["usuario"]
    df_res["fecha_str"] = df_res["fecha_hora"].dt.strftime("%d-%m-%Y %H:%M")

    cols_salida = ["codigo_obra", "usuario", "fecha_str", "caudal_ls", "totalizador_m3", "nivel_m"]
    json_bytes = df_res[cols_salida].to_json(orient="records")

    return Response(content=json_bytes, media_type="application/json")


@app.get("/api/descargar_csv")
def descargar_csv(codigo: str = Query(...)):
    cod = validar_codigo(codigo)
    info = obtener_info_obra(cod)
    df_res = consultar_datos_locales(cod)

    if df_res.empty and info["id_obra"] > 0:
        try:
            df_nuevo = obtener_mediciones_obra(cod, info["id_obra"], info["fecha_registro"])
            if not df_nuevo.empty:
                guardar_mediciones(df_nuevo)
                df_res = consultar_datos_locales(cod)
        finally:
            registrar_intento_scraping(cod)

    if df_res.empty:
        raise HTTPException(status_code=404, detail="Sin datos disponibles para exportar.")

    df_res["usuario"] = info["usuario"]
    df_res["fecha_str"] = df_res["fecha_hora"].dt.strftime("%d-%m-%Y %H:%M")
    df_salida = df_res[["codigo_obra", "usuario", "fecha_str", "caudal_ls", "totalizador_m3", "nivel_m"]]
    csv_bytes = df_salida.to_csv(index=False, encoding="utf-8-sig")

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=MEE_{cod}.csv"}
    )


@app.get("/api/modflow_wel")
def exportar_modflow_wel(codigo: str = Query(...)):
    """
    Retorna la serie mensual agregada lista para armar el paquete Well (WEL) de MODFLOW.
    Unidades: Caudal medio de extracción en m³/día y m³/s.
    """
    cod = validar_codigo(codigo)
    df_mensual = consultar_extracciones_mensuales(cod)
    if df_mensual.empty:
        raise HTTPException(status_code=404, detail="No existen datos suficientes para generar serie MODFLOW.")

    # Inyección de metadatos espaciales para el archivo WEL
    info = obtener_info_obra(cod)
    df_mensual["usuario"] = info["usuario"]
    df_mensual["q_wel_m3_s"] = df_mensual["caudal_medio_ls"] / 1000.0

    cols = ["codigo_obra", "usuario", "anio", "mes", "caudal_medio_ls", "modflow_wel_m3_dia", "q_wel_m3_s", "volumen_m3"]
    csv_bytes = df_mensual[cols].to_csv(index=False, encoding="utf-8-sig")

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=MODFLOW_WEL_{cod}.csv"}
    )


@app.get("/api/weap_demand")
def exportar_weap_demand(codigo: str = Query(...)):
    """
    Retorna volúmenes mensuales en miles de m³ (o m³) para asignación en nodos
    de demanda o suministros subterráneos en el modelo WEAP.
    """
    cod = validar_codigo(codigo)
    df_mensual = consultar_extracciones_mensuales(cod)
    if df_mensual.empty:
        raise HTTPException(status_code=404, detail="No existen datos suficientes para generar serie WEAP.")

    cols = ["codigo_obra", "anio", "mes", "volumen_m3", "weap_volumen_miles_m3", "horas_reportadas"]
    csv_bytes = df_mensual[cols].to_csv(index=False, encoding="utf-8-sig")

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=WEAP_EXT_{cod}.csv"}
    )


@app.get("/visor", response_class=HTMLResponse)
def servir_visor(codigo: str = ""):
    cod = codigo.strip().upper() if codigo else ""
    info = obtener_info_obra(cod) if cod else {
        "usuario": "Seleccione una obra",
        "naturaleza": "-",
        "comuna": "-"
    }

    try:
        with open("visor_mee.html", "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Plantilla visor_mee.html no encontrada.")

    return (
        html.replace("{{CODIGO}}", cod)
            .replace("{{USUARIO}}", info["usuario"])
            .replace("{{NATURALEZA}}", info["naturaleza"])
            .replace("{{COMUNA}}", info["comuna"])
    )
