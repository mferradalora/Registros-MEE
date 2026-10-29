#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import datetime
from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.responses import HTMLResponse
import pandas as pd

from database_mee import inicializar_db, guardar_mediciones, consultar_datos_locales, verificar_necesidad_scraping
from extractor_mee import obtener_mediciones_obra

inicializar_db()
app = FastAPI(title="Servicio de Registros MEE DGA")

# Cargar catálogo de obras en memoria
POSIBLES_RUTAS = ["catalogo_obras_mee.csv", "Listado_Obras_MEE.csv", "data/catalogo_obras_mee.csv"]
df_cat = pd.DataFrame()

for ruta in POSIBLES_RUTAS:
    if os.path.exists(ruta):
        df_cat = pd.read_csv(ruta)
        df_cat["Codigo_Obra"] = df_cat["Codigo_Obra"].fillna("").astype(str).str.strip()
        df_cat["ID_Obra"] = pd.to_numeric(df_cat["ID_Obra"], errors="coerce").fillna(0).astype(int)
        if "Fecha_Registro_DGA" in df_cat.columns:
            df_cat["Fecha_Clean"] = pd.to_datetime(df_cat["Fecha_Registro_DGA"], dayfirst=True, errors="coerce").dt.date
        else:
            df_cat["Fecha_Clean"] = datetime.date(2020, 1, 1)
        df_cat["Fecha_Clean"] = df_cat["Fecha_Clean"].fillna(datetime.date(2020, 1, 1))
        print(f"✅ Catálogo MEE cargado exitosamente desde '{ruta}' ({len(df_cat):,} obras).", flush=True)
        break


def obtener_info_obra(codigo_obra: str) -> dict:
    cod = codigo_obra.strip().upper()
    if not df_cat.empty:
        match = df_cat[df_cat["Codigo_Obra"].str.upper() == cod]
        if not match.empty:
            r = match.iloc[0]
            return {
                "codigo_obra": cod,
                "id_obra": int(r["ID_Obra"]),
                "usuario": str(r.get("Usuario", "S/I")),
                "rut": str(r.get("RUT_Usuario", "")),
                "naturaleza": str(r.get("Naturaleza", "")),
                "region": str(r.get("Region", "")),
                "comuna": str(r.get("Comuna", "")),
                "fecha_registro": r["Fecha_Clean"]
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
    info = obtener_info_obra(codigo)
    info["fecha_registro"] = info["fecha_registro"].strftime("%d/%m/%Y")
    return info


@app.get("/api/datos")
def api_datos(codigo: str = Query(...)):
    codigo = codigo.strip().upper()
    info = obtener_info_obra(codigo)

    if info["id_obra"] == 0:
        raise HTTPException(status_code=404, detail=f"La obra '{codigo}' no figura en el catálogo.")

    if verificar_necesidad_scraping(codigo):
        print(f"📡 Consultando servicio DGA MEE para obra {codigo}...", flush=True)
        df_nuevo = obtener_mediciones_obra(codigo, info["id_obra"], info["fecha_registro"])
        if not df_nuevo.empty:
            guardar_mediciones(df_nuevo)

    df_res = consultar_datos_locales(codigo)
    if df_res.empty:
        raise HTTPException(status_code=404, detail="No se encontraron registros de mediciones para esta obra.")

    df_res["usuario"] = info["usuario"]
    df_res["fecha_str"] = df_res["fecha_hora"].dt.strftime("%d-%m-%Y %H:%M")
    return df_res[["codigo_obra", "usuario", "fecha_str", "caudal_ls", "totalizador_m3", "nivel_m"]].to_dict(orient="records")


@app.get("/api/descargar_csv")
def descargar_csv(codigo: str = Query(...)):
    codigo = codigo.strip().upper()
    info = obtener_info_obra(codigo)
    df_res = consultar_datos_locales(codigo)

    if df_res.empty and info["id_obra"] > 0:
        df_nuevo = obtener_mediciones_obra(codigo, info["id_obra"], info["fecha_registro"])
        if not df_nuevo.empty:
            guardar_mediciones(df_nuevo)
            df_res = consultar_datos_locales(codigo)

    if df_res.empty:
        raise HTTPException(status_code=404, detail="Sin datos disponibles para exportar.")

    df_res["usuario"] = info["usuario"]
    csv_bytes = df_res[["codigo_obra", "usuario", "fecha_hora", "caudal_ls", "totalizador_m3", "nivel_m"]].to_csv(index=False, encoding="utf-8-sig")

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=MEE_{codigo}.csv"}
    )


@app.get("/visor", response_class=HTMLResponse)
def servir_visor(codigo: str = ""):
    codigo = codigo.strip().upper()
    info = obtener_info_obra(codigo)

    with open("visor_mee.html", "r", encoding="utf-8") as f:
        html = f.read()

    return (
        html.replace("{{CODIGO}}", codigo)
            .replace("{{USUARIO}}", info["usuario"])
            .replace("{{NATURALEZA}}", info["naturaleza"])
            .replace("{{COMUNA}}", info["comuna"])
    )
