#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Módulo de extracción y normalización de series temporales MEE (DGA SNIA).
Detecta encabezados multinivel y parsea tanto HTML/XLS como Excel nativo.
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
    print("🔑 Solicitando token de autorización a DGA SNIA...", flush=True)
    resp = requests.post(URL_AUTH, json=AUTH_PAYLOAD, headers=HEADERS_BASE, timeout=15)
    resp.raise_for_status()
    token = resp.json().get("accessToken")
    print("🔑 Token DGA adquirido exitosamente.", flush=True)
    return token


def descargar_reporte_crudo(codigo_obra: str, id_obra: int, fecha_desde_dt: datetime.date):
    """Solicita el reporte de mediciones detallado a la DGA."""
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

    print(f"📡 Enviando solicitud a DGA para obra {codigo_obra} (ID: {id_obra}, Desde: {fecha_desde_dt})...", flush=True)
    resp = session.post(URL_REPORTE, headers=headers, json=payload, timeout=60)
    
    if resp.status_code == 401:
        print("🔄 Token expirado, renovando...", flush=True)
        token = obtener_token_dga()
        headers['authorization'] = f'Bearer {token}'
        resp = session.post(URL_REPORTE, headers=headers, json=payload, timeout=60)

    print(f"📦 Respuesta DGA recibida (Código HTTP: {resp.status_code}, Tamaño: {len(resp.content):,} bytes).", flush=True)
    resp.raise_for_status()
    return resp.content


def parsear_reporte_mee(content_bytes: bytes, codigo_obra: str) -> pd.DataFrame:
    """Convierte el archivo devuelto por la DGA detectando la fila real de datos."""
    if not content_bytes:
        return pd.DataFrame()

    df_raw = None

    # 1. Intentar lectura como tabla HTML (formato habitual de DGA bajo extensión .xls)
    try:
        dfs = pd.read_html(io.BytesIO(content_bytes))
        for d in dfs:
            texto_tabla = ' '.join(str(v).lower() for v in d.head(10).values.flatten())
            if "caudal" in texto_tabla or "código" in texto_tabla or "codigo" in texto_tabla:
                df_raw = d
                break
        if df_raw is None and len(dfs) > 0:
            df_raw = dfs[0]
    except Exception:
        pass

    # 2. Si no es HTML, intentar lectura directa con Excel
    if df_raw is None:
        try:
            df_raw = pd.read_excel(io.BytesIO(content_bytes), header=None)
        except Exception as e:
            print(f"❌ Error al interpretar archivo Excel: {e}", flush=True)
            return pd.DataFrame()

    if df_raw is None or df_raw.empty:
        print("⚠️ El archivo devuelto no contiene tablas válidas.", flush=True)
        return pd.DataFrame()

    # 3. Localizar dinámicamente la fila de encabezados reales
    header_idx = None
    for idx in range(min(15, len(df_raw))):
        fila_str = ' '.join(str(v).lower() for v in df_raw.iloc[idx].values)
        if ("código" in fila_str or "codigo" in fila_str or "nro" in fila_str) and ("caudal" in fila_str or "fecha" in fila_str):
            header_idx = idx
            break

    if header_idx is not None:
        print(f"🔍 Encabezados detectados en la fila {header_idx + 1}.", flush=True)
        new_cols = [str(v).strip() for v in df_raw.iloc[header_idx].values]
        df = df_raw.iloc[header_idx + 1:].copy()
        df.columns = new_cols
    else:
        df = df_raw.copy()

    # 4. Normalizar nombres de columnas
    col_map = {}
    for c in df.columns:
        c_clean = str(c).lower().strip()
        if "fecha" in c_clean and ("dd/mm/yyyy" in c_clean or "medici" in c_clean) and "registro" not in c_clean:
            col_map[c] = "fecha"
        elif "hora" in c_clean and "medici" in c_clean:
            col_map[c] = "hora"
        elif "caudal" in c_clean:
            col_map[c] = "caudal_ls"
        elif any(k in c_clean for k in ["totalizador", "volumen", "acumulado"]):
            col_map[c] = "totalizador_m3"
        elif any(k in c_clean for k in ["altura", "limnim", "freatico", "nivel", "profundidad"]):
            col_map[c] = "nivel_m"

    df = df.rename(columns=col_map).copy()

    # 5. Unificar Fecha y Hora en una sola columna temporal
    if "fecha" in df.columns and "hora" in df.columns:
        df["fecha_hora"] = df["fecha"].astype(str).str.strip() + " " + df["hora"].astype(str).str.strip()
    elif "fecha" in df.columns:
        df["fecha_hora"] = df["fecha"].astype(str).str.strip()
    elif "fecha_hora" not in df.columns:
        print(f"⚠️ Columnas presentes tras el mapeo: {list(df.columns)}", flush=True)
        return pd.DataFrame()

    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["fecha_hora"])

    # 6. Limpieza de columnas numéricas
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
    print(f"✅ Se procesaron exitosamente {len(df):,} filas de mediciones.", flush=True)
    return df[["codigo_obra", "fecha_hora", "caudal_ls", "totalizador_m3", "nivel_m"]]


def obtener_mediciones_obra(codigo_obra: str, id_obra: int, fecha_desde_dt: datetime.date) -> pd.DataFrame:
    try:
        raw_bytes = descargar_reporte_crudo(codigo_obra, id_obra, fecha_desde_dt)
        return parsear_reporte_mee(raw_bytes, codigo_obra)
    except Exception as e:
        print(f"❌ Error en el proceso de extracción para {codigo_obra}: {e}", flush=True)
        return pd.DataFrame()
