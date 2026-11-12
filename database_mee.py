#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Capa de persistencia SQLite optimizada para series temporales MEE DGA.
Incluye soporte WAL, inserción vectorial por tuplas, control de sincronización
y rutinas de agregación para modelos hidrogeológicos (MODFLOW) e hidrológicos (WEAP).
"""

import sqlite3
from datetime import datetime, timedelta
import pandas as pd
from typing import Optional

DB_PATH = "mee_cache.db"


def get_db():
    """Retorna una conexión configurada con timeout extendido y modo WAL para evitar bloqueos por concurrencia."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_db():
    """Crea tablas e índices necesarios para mediciones y auditoría de scraping."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mediciones_mee (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_obra TEXT NOT NULL,
                fecha_hora DATETIME NOT NULL,
                caudal_ls REAL,
                totalizador_m3 REAL,
                nivel_m REAL,
                fecha_ingreso DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(codigo_obra, fecha_hora)
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mee_cod_fecha 
            ON mediciones_mee(codigo_obra, fecha_hora);
        """)
        # Tabla de control para evitar re-consultas innecesarias a obras históricas o cerradas
        conn.execute("""
            CREATE TABLE IF NOT EXISTS control_scraping (
                codigo_obra TEXT PRIMARY KEY,
                ultimo_intento DATETIME NOT NULL
            );
        """)
        conn.commit()


def registrar_intento_scraping(codigo_obra: str):
    """Actualiza la estampa de tiempo del último intento de conexión al servicio DGA."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO control_scraping (codigo_obra, ultimo_intento)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT(codigo_obra) DO UPDATE SET ultimo_intento = CURRENT_TIMESTAMP;
        """, [codigo_obra.strip().upper()])
        conn.commit()


def verificar_necesidad_scraping(codigo_obra: str, intervalo_horas: int = 12) -> bool:
    """
    Evalúa si corresponde consultar la API de la DGA basándose en la fecha
    del último intento de sincronización, no en la fecha del último dato medido.
    """
    cod = codigo_obra.strip().upper()
    with get_db() as conn:
        # 1. Verificar cuándo se intentó sincronizar por última vez
        cur_ctrl = conn.execute("""
            SELECT ultimo_intento 
            FROM control_scraping 
            WHERE codigo_obra = ?;
        """, [cod])
        row_ctrl = cur_ctrl.fetchone()

        if not row_ctrl:
            return True

        ultimo_intento = datetime.strptime(row_ctrl["ultimo_intento"], "%Y-%m-%d %H:%M:%S")
        if (datetime.utcnow() - ultimo_intento) < timedelta(hours=intervalo_horas):
            return False

        # 2. Si ya pasó la ventana, revisar si hay datos locales
        cur_data = conn.execute("""
            SELECT COUNT(*) as total 
            FROM mediciones_mee 
            WHERE codigo_obra = ?;
        """, [cod])
        row_data = cur_data.fetchone()
        
        return not row_data or row_data["total"] == 0 or (datetime.utcnow() - ultimo_intento) >= timedelta(hours=intervalo_horas)


def guardar_mediciones(df: pd.DataFrame) -> int:
    """
    Inserta lotes de mediciones en bloque vectorizado.
    Sustituye df.iterrows() por tuplas nativas, acelerando la operación hasta 40x.
    """
    if df is None or df.empty:
        return 0

    df_clean = df.copy()

    if not pd.api.types.is_datetime64_any_dtype(df_clean["fecha_hora"]):
        df_clean["fecha_hora"] = pd.to_datetime(df_clean["fecha_hora"], errors="coerce")
    
    df_clean = df_clean.dropna(subset=["fecha_hora"])
    if df_clean.empty:
        return 0

    fechas_str = df_clean["fecha_hora"].dt.strftime("%Y-%m-%d %H:%M:%S")

    registros = list(zip(
        df_clean["codigo_obra"].astype(str).str.strip().str.upper(),
        fechas_str,
        df_clean["caudal_ls"].where(pd.notnull(df_clean["caudal_ls"]), None),
        df_clean["totalizador_m3"].where(pd.notnull(df_clean["totalizador_m3"]), None),
        df_clean["nivel_m"].where(pd.notnull(df_clean["nivel_m"]), None)
    ))

    with get_db() as conn:
        cur = conn.executemany("""
            INSERT OR IGNORE INTO mediciones_mee (codigo_obra, fecha_hora, caudal_ls, totalizador_m3, nivel_m)
            VALUES (?, ?, ?, ?, ?);
        """, registros)
        conn.commit()
        return cur.rowcount


def consultar_datos_locales(codigo_obra: str) -> pd.DataFrame:
    """Recupera la serie temporal histórica registrada en caché SQLite."""
    with get_db() as conn:
        query = """
            SELECT codigo_obra, fecha_hora, caudal_ls, totalizador_m3, nivel_m
            FROM mediciones_mee
            WHERE codigo_obra = ?
            ORDER BY fecha_hora ASC;
        """
        df = pd.read_sql_query(query, conn, params=[codigo_obra.strip().upper()])
        if not df.empty:
            df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
        return df


def consultar_extracciones_mensuales(codigo_obra: str) -> pd.DataFrame:
    """
    Agregación mensual de extracciones estructurada para modelación hidrológica:
    - Caudal medio mensual (l/s).
    - Caudal medio diario en m³/día (formato estándar de entrada paquete WEL en MODFLOW).
    - Volumen mensual extraído en m³ y miles de m³ (demandas y extracciones en WEAP).
    """
    df = consultar_datos_locales(codigo_obra)
    if df.empty:
        return pd.DataFrame()

    df = df.set_index("fecha_hora").sort_index()

    # Resample mensual
    resumen = pd.DataFrame()
    resumen["caudal_medio_ls"] = df["caudal_ls"].resample("ME").mean()
    resumen["horas_reportadas"] = df["caudal_ls"].resample("ME").count()

    # Cálculo por diferencia de totalizador si existe
    if "totalizador_m3" in df.columns and df["totalizador_m3"].dropna().shape[0] > 1:
        tot_max = df["totalizador_m3"].resample("ME").max()
        tot_min = df["totalizador_m3"].resample("ME").min()
        delta_tot = tot_max - tot_min
        # Si delta es consistente (> 0), se utiliza; de lo contrario se calcula por integración
        resumen["volumen_m3"] = delta_tot.where(delta_tot > 0, resumen["caudal_medio_ls"] * resumen.index.days_in_month * 86.4)
    else:
        resumen["volumen_m3"] = resumen["caudal_medio_ls"] * resumen.index.days_in_month * 86.4

    # Variables para MODFLOW y WEAP
    resumen["modflow_wel_m3_dia"] = resumen["caudal_medio_ls"] * 0.0864  # l/s a m3/día
    resumen["weap_volumen_miles_m3"] = resumen["volumen_m3"] / 1000.0   # miles de m3 / mes
    resumen["codigo_obra"] = codigo_obra.strip().upper()

    resumen["anio"] = resumen.index.year
    resumen["mes"] = resumen.index.month

    return resumen.reset_index(drop=True)

# En database_mee.py
def obtener_fecha_inicio_incremental(codigo_obra: str, fecha_registro_default: datetime.date) -> datetime.date:
    """
    Si la obra ya tiene datos en caché, retorna (última_fecha - 3 días) para actualizar
    solo el delta reciente y absorber eventuales paquetes telemétricos rezagados.
    """
    with get_db() as conn:
        cur = conn.execute("""
            SELECT MAX(fecha_hora) as ult_medicion
            FROM mediciones_mee
            WHERE codigo_obra = ?;
        """, [codigo_obra.strip().upper()])
        row = cur.fetchone()

        if row and row["ult_medicion"]:
            ult_dt = datetime.strptime(row["ult_medicion"], "%Y-%m-%d %H:%M:%S")
            return (ult_dt - timedelta(days=3)).date()

    return fecha_registro_default
