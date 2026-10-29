#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Módulo de extracción y normalización de series temporales MEE (DGA SNIA).
"""

import io
import datetime
import requests
import pandas as pd

URL_AUTH = "https://snia.mop.gob.cl/mee-auth-rest/v1/authorization"
URL_REPORTE = "https://snia.mop.gob.cl/extracciones/data/reporte/obrasDetallado"

AUTH_PAYLOAD = {
    'apiCode': 'MEESECINT',
    'apiKey': '73A58577C1CCB258DFD79116EAD8F',
    'app': 'exponline'
}

HEADERS_BASE = {
    'accept': 'application/json, text/plain, */*',
    'content-type': 'application/json',
    'origin': 'https://snia.mop.gob.cl',
    'referer': 'https://snia.mop.gob.cl/cExtracciones2/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
}


def obtener_token_dga():
    """Genera token JWT Bearer en el servicio REST de la DGA."""
    resp = requests.post(URL_AUTH, json=AUTH_PAYLOAD, headers=HEADERS_BASE, timeout=15)
    resp.raise_for_status()
    return resp.json().get("accessToken")


def descargar_reporte_crudo(codigo_obra: str, id_obra: int, fecha_desde_dt: datetime.date):
    """Descarga el reporte detallado desde la API de la DGA."""
    token = obtener_token_dga()
    session = requests.Session()

    fecha_desde_iso = f"{fecha_desde_dt.strftime('%Y-%m-%d')}T03:00:00.000Z"
    fecha_hasta_iso = f"{datetime.date.today().strftime('%Y-%m-%d')}T02:59:59.000Z"
    es_restitucion = str(codigo_obra).strip().upper().startswith("OR")

    headers = dict(HEADERS_BASE)
    headers['authorization'] = f'Bearer {token}'

    payload = {
        'metaData': {'paginator': None, 'token': None, 'userName': None},
        'data': {
            'fechaDesde': fecha_desde_iso,
            'fechaHasta': fecha_hasta_iso,
            'fechaDesdeLog': None,
            'fechaHastaLog': None,
            'codigoObraLog': None,
            'obras': [] if es_restitucion else [int(id_obra)],
            'puntosRestitucion': [int(id_obra)] if es_restitucion else [],
            'tipoReporte': {'clave': 4, 'valor': None},
            'anio': None,
            'mes': None,
            'naturaleza': 2 if es_restitucion else 1,
            'todasAlertasObra': None,
            'tipoAlerta': None,
            'mideConCaudalimetro': not es_restitucion,
        },
    }

    resp = session.post(URL_REPORTE, headers=headers, json=payload, timeout=45)
    if resp.status_code == 401:
        token = obtener_token_dga()
        headers['authorization'] = f'Bearer {token}'
        resp = session.post(URL_REPORTE, headers=headers, json=payload, timeout=45)

    resp.raise_for_status()
    return resp.content


def parsear_reporte_mee(content_bytes: bytes, codigo_obra: str) -> pd.DataFrame:
    """Convierte el archivo XLS/HTML devuelto por DGA en un DataFrame normalizado."""
    if not content_bytes:
        return pd.DataFrame()

    df_raw = None
    # 1. Intentar lectura como tabla HTML (formato común devuelto con extensión .xls)
    try:
        dfs = pd.read_html(io.BytesIO(content_bytes))
        for d in dfs:
            cols = [str(c).lower() for c in d.columns]
            if any("fecha" in c or "caudal" in c for c in cols):
                df_raw = d
                break
        if df_raw is None and len(dfs) > 0:
            df_raw = dfs[0]
    except Exception:
        pass

    # 2. Si falla HTML, intentar lectura directa con Excel
    if df_raw is None:
        try:
            df_raw = pd.read_excel(io.BytesIO(content_bytes))
        except Exception:
            return pd.DataFrame()

    if df_raw.empty:
        return pd.DataFrame()

    # Si hay encabezados multinivel, aplanarlos
    if isinstance(df_raw.columns, pd.MultiIndex):
        df_raw.columns = ['_'.join(str(c) for c in col).strip() for col in df_raw.columns]

    # Mapeo flexible de columnas
    col_map = {}
    for c in df_raw.columns:
        c_clean = str(c).lower().strip()
        if "fecha" in c_clean and ("hora" in c_clean or "medici" in c_clean):
            col_map[c] = "fecha_hora"
        elif "fecha" in c_clean and "fecha_hora" not in col_map.values():
            col_map[c] = "fecha"
        elif "hora" in c_clean and "fecha_hora" not in col_map.values():
            col_map[c] = "hora"
        elif "caudal" in c_clean:
            col_map[c] = "caudal_ls"
        elif "totalizador" in c_clean or "volumen" in c_clean or "acumulado" in c_clean:
            col_map[c] = "totalizador_m3"
        elif "nivel" in c_clean or "freatico" in c_clean:
            col_map[c] = "nivel_m"

    df = df_raw.rename(columns=col_map).copy()

    # Combinar fecha y hora si vinieron separadas
    if "fecha" in df.columns and "hora" in df.columns and "fecha_hora" not in df.columns:
        df["fecha_hora"] = df["fecha"].astype(str).str.strip() + " " + df["hora"].astype(str).str.strip()
    elif "fecha" in df.columns and "fecha_hora" not in df.columns:
        df["fecha_hora"] = df["fecha"]

    if "fecha_hora" not in df.columns:
        return pd.DataFrame()

    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["fecha_hora"])

    # Limpieza de columnas numéricas
    for metrica in ["caudal_ls", "totalizador_m3", "nivel_m"]:
        if metrica in df.columns:
            df[metrica] = (
                df[metrica]
                .astype(str)
                .str.replace(" ", "", regex=False)
                .str.replace(",", ".", regex=False)
                .str.extract(r'([-+]?\d*\.?\d+)', expand=False)
            )
            df[metrica] = pd.to_numeric(df[metrica], errors="coerce")
        else:
            df[metrica] = None

    df["codigo_obra"] = codigo_obra
    df = df.sort_values(by="fecha_hora").reset_index(drop=True)
    return df[["codigo_obra", "fecha_hora", "caudal_ls", "totalizador_m3", "nivel_m"]]


def obtener_mediciones_obra(codigo_obra: str, id_obra: int, fecha_desde_dt: datetime.date) -> pd.DataFrame:
    """Función de alto nivel que descarga y entrega el DataFrame limpio."""
    try:
        raw_bytes = descargar_reporte_crudo(codigo_obra, id_obra, fecha_desde_dt)
        return parsear_reporte_mee(raw_bytes, codigo_obra)
    except Exception as e:
        print(f"Error extrayendo reporte MEE para {codigo_obra}: {e}", flush=True)
        return pd.DataFrame()
