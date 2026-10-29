#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timedelta
import pandas as pd

DB_PATH = "mee_cache.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_db():
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
        conn.commit()


def guardar_mediciones(df: pd.DataFrame):
    if df is None or df.empty:
        return 0

    registros = []
    for _, r in df.iterrows():
        f_str = r["fecha_hora"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(r["fecha_hora"], "strftime") else str(r["fecha_hora"])
        registros.append((
            str(r["codigo_obra"]).strip(),
            f_str,
            float(r["caudal_ls"]) if pd.notnull(r["caudal_ls"]) else None,
            float(r["totalizador_m3"]) if pd.notnull(r["totalizador_m3"]) else None,
            float(r["nivel_m"]) if pd.notnull(r["nivel_m"]) else None
        ))

    with get_db() as conn:
        cur = conn.executemany("""
            INSERT OR IGNORE INTO mediciones_mee (codigo_obra, fecha_hora, caudal_ls, totalizador_m3, nivel_m)
            VALUES (?, ?, ?, ?, ?);
        """, registros)
        conn.commit()
        return cur.rowcount


def consultar_datos_locales(codigo_obra: str):
    with get_db() as conn:
        query = """
            SELECT codigo_obra, fecha_hora, caudal_ls, totalizador_m3, nivel_m
            FROM mediciones_mee
            WHERE codigo_obra = ?
            ORDER BY fecha_hora ASC;
        """
        df = pd.read_sql_query(query, conn, params=[codigo_obra.strip()])
        if not df.empty:
            df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
        return df


def verificar_necesidad_scraping(codigo_obra: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("""
            SELECT MAX(fecha_hora) as ult_medicion, COUNT(*) as total
            FROM mediciones_mee
            WHERE codigo_obra = ?;
        """, [codigo_obra.strip()])
        row = cur.fetchone()

        if not row or row["total"] == 0 or row["ult_medicion"] is None:
            return True

        # Si pasaron más de 12 horas desde la última fecha registrada, actualizar
        ult = datetime.strptime(row["ult_medicion"], "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - ult) > timedelta(hours=12)
