import time
import random
import requests
import pandas as pd
from pathlib import Path

tiempo_inicio = time.time()

# -------------------------------------------------------------------------
# 1. PARÁMETROS Y OBRAS OBJETIVO
# -------------------------------------------------------------------------
# Códigos de obra a descargar (ejemplos)
obras_a_descargar = ["OB-0203-400", "OB-0203-361", "OB-0203-359"]

fecha_desde = '2020-01-01'
fecha_hasta = '2026-08-01'
path_csv = "Listado Obras MEE.csv"

# -------------------------------------------------------------------------
# 2. LECTURA DEL CSV Y MAPEO DIRECTO (Codigo_Obra -> ID_Obra)
# -------------------------------------------------------------------------
mapa_obras = {}

try:
    df_obras = pd.read_csv(path_csv)
    print(f"✅ CSV '{path_csv}' cargado correctamente ({len(df_obras)} registros base).")

    # Limpieza básica de datos
    df_obras = df_obras.dropna(subset=['Codigo_Obra', 'ID_Obra'])
    df_obras['Codigo_Obra'] = df_obras['Codigo_Obra'].astype(str).str.strip()
    df_obras['ID_Obra'] = df_obras['ID_Obra'].astype(int)

    # Mapeo clave-valor directo
    mapa_obras = dict(zip(df_obras['Codigo_Obra'], df_obras['ID_Obra']))

except FileNotFoundError:
    print(f"❌ Error: No se encontró el archivo '{path_csv}'.")
    raise SystemExit()
except Exception as e:
    print(f"❌ Error al procesar el CSV: {e}")
    raise SystemExit()

# -------------------------------------------------------------------------
# 3. AUTENTICACIÓN Y SESIÓN CON DGA SNIA
# -------------------------------------------------------------------------
def obtener_token():
    url_auth = "https://snia.mop.gob.cl/mee-auth-rest/v1/authorization"
    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json',
        'origin': 'https://snia.mop.gob.cl',
        'referer': 'https://snia.mop.gob.cl/cExtracciones2/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
    }
    payload = {
        'apiCode': 'MEESECINT',
        'apiKey': '73A58577C1CCB258DFD79116EAD8F',
        'app': 'exponline'
    }
    resp = requests.post(url_auth, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("accessToken")

print("🔑 Generando token de acceso con el servidor DGA...")
token_actual = obtener_token()
session = requests.Session()

# -------------------------------------------------------------------------
# 4. DESCARGA DE ARCHIVOS (.XLS)
# -------------------------------------------------------------------------
for obra_codigo in obras_a_descargar:
    if obra_codigo not in mapa_obras:
        print(f"⚠️ Alerta: La obra '{obra_codigo}' no figura en '{path_csv}'. Se omitirá.")
        continue

    id_obra = mapa_obras[obra_codigo]

    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'es-ES,es;q=0.9',
        'authorization': f'Bearer {token_actual}',
        'content-type': 'application/json',
        'origin': 'https://snia.mop.gob.cl',
        'referer': 'https://snia.mop.gob.cl/cExtracciones2/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
    }

    payload = {
        'metaData': {'paginator': None, 'token': None, 'userName': None},
        'data': {
            'fechaDesde': f'{fecha_desde}T03:00:00.000Z',
            'fechaHasta': f'{fecha_hasta}T02:59:59.000Z',
            'fechaDesdeLog': None,
            'fechaHastaLog': None,
            'codigoObraLog': None,
            'obras': [id_obra],
            'puntosRestitucion': [],
            'tipoReporte': {'clave': 4, 'valor': None},
            'anio': None,
            'mes': None,
            'naturaleza': 1,
            'todasAlertasObra': None,
            'tipoAlerta': None,
            'mideConCaudalimetro': True,
        },
    }

    max_reintentos = 3
    for intento in range(1, max_reintentos + 1):
        try:
            print(f"📡 Solicitando {obra_codigo} [ID: {id_obra}] (Intento {intento}/{max_reintentos})...")
            response = session.post(
                'https://snia.mop.gob.cl/extracciones/data/reporte/obrasDetallado',
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 401:
                print("🔄 Token expirado. Renovando autorización...")
                token_actual = obtener_token()
                headers['authorization'] = f'Bearer {token_actual}'
                continue

            if response.status_code == 200:
                archivo_salida = Path(f"reportes/{obra_codigo}.xls")
                archivo_salida.write_bytes(response.content)
                print(f"✅ Guardado correctamente: {archivo_salida.name}")
                break
            else:
                print(f"⚠️ Error HTTP {response.status_code}: {response.text[:100]}")

        except Exception as e:
            print(f"❌ Error de conexión: {e}")

        time.sleep(2 * intento)

    pausa = random.uniform(4, 8)
    time.sleep(pausa)

tiempo_total = (time.time() - tiempo_inicio) / 60
print(f"\n🚀 Extracción finalizada en {tiempo_total:.2f} minutos.")
