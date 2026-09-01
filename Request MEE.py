import time
import random
import requests
import datetime
import pandas as pd
from pathlib import Path

tiempo_inicio = time.time()

# -------------------------------------------------------------------------
# 1. PARÁMETROS Y CONFIGURACIÓN
# -------------------------------------------------------------------------
obras_a_descargar = ["OR-1302-3", "OB-0601-16"]
path_csv = "Listado_Obras_MEE.csv"

# Fecha límite superior dinámica (hoy)
fecha_hasta_dt = datetime.date.today()
fecha_hasta_str = fecha_hasta_dt.strftime('%Y-%m-%d')

# Directorio de salida local / repositorio
dir_salida = Path("reportes")
dir_salida.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------------------
# 2. LECTURA DEL CSV Y MAPEO DINÁMICO (ID + Fecha Registro DGA)
# -------------------------------------------------------------------------
mapa_obras = {}

try:
    df_obras = pd.read_csv(path_csv)
    print(f"✅ CSV '{path_csv}' cargado correctamente ({len(df_obras)} registros base).")

    # Limpieza básica de datos esenciales
    df_obras = df_obras.dropna(subset=['Codigo_Obra', 'ID_Obra'])
    df_obras['Codigo_Obra'] = df_obras['Codigo_Obra'].astype(str).str.strip()
    df_obras['ID_Obra'] = df_obras['ID_Obra'].astype(int)

    # Parseo seguro de Fecha_Registro_DGA a YYYY-MM-DD
    if 'Fecha_Registro_DGA' in df_obras.columns:
        df_obras['Fecha_Clean'] = pd.to_datetime(
            df_obras['Fecha_Registro_DGA'], dayfirst=True, errors='coerce'
        ).dt.strftime('%Y-%m-%d')
    else:
        df_obras['Fecha_Clean'] = '2020-01-01'

    # Asignar fecha por defecto '2020-01-01' en caso de valores nulos
    df_obras['Fecha_Clean'] = df_obras['Fecha_Clean'].fillna('2020-01-01')

    # Diccionario estructurado {Codigo_Obra: {'id': ID_Obra, 'fecha_registro': Fecha}}
    for _, row in df_obras.iterrows():
        mapa_obras[row['Codigo_Obra']] = {
            'id': row['ID_Obra'],
            'fecha_registro': row['Fecha_Clean']
        }

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
# 4. DESCARGA DE ARCHIVOS (.XLS) CON VENTANA TEMPORAL DINÁMICA
# -------------------------------------------------------------------------
for obra_codigo in obras_a_descargar:
    if obra_codigo not in mapa_obras:
        print(f"⚠️ Alerta: La obra '{obra_codigo}' no figura en '{path_csv}'. Se omitirá.")
        continue

    id_obra = mapa_obras[obra_codigo]['id']
    fecha_desde_str = mapa_obras[obra_codigo]['fecha_registro']

    # Definición de ISO Timestamps para el Payload
    fecha_desde_iso = f"{fecha_desde_str}T03:00:00.000Z"
    fecha_hasta_iso = f"{fecha_hasta_str}T02:59:59.000Z"

    # Evaluador de restitución por prefijo
    es_restitucion = obra_codigo.upper().startswith("OR")

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
            'fechaDesde': fecha_desde_iso,
            'fechaHasta': fecha_hasta_iso,
            'fechaDesdeLog': None,
            'fechaHastaLog': None,
            'codigoObraLog': None,
            'obras': [] if es_restitucion else [id_obra],
            'puntosRestitucion': [id_obra] if es_restitucion else [],
            'tipoReporte': {'clave': 4, 'valor': None},
            'anio': None,
            'mes': None,
            'naturaleza': 2 if es_restitucion else 1,
            'todasAlertasObra': None,
            'tipoAlerta': None,
            'mideConCaudalimetro': not es_restitucion,
        },
    }

    tipo_txt = "Restitución" if es_restitucion else "Extracción"
    max_reintentos = 3

    for intento in range(1, max_reintentos + 1):
        try:
            print(f"📡 Solicitando {obra_codigo} ({tipo_txt}) [ID: {id_obra}] | Rango fechas: {fecha_desde_str} -> {fecha_hasta_str} (Intento {intento}/{max_reintentos})...")
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
                archivo_salida = dir_salida / f"{obra_codigo}.xls"
                archivo_salida.write_bytes(response.content)
                print(f"✅ Guardado correctamente: {archivo_salida.name}")
                break
            else:
                print(f"⚠️ Error HTTP {response.status_code}: {response.text[:100]}")

        except Exception as e:
            print(f"❌ Error de conexión: {e}")

        time.sleep(2 * intento)

    pausa = random.uniform(5, 10)
    time.sleep(pausa)

tiempo_total = (time.time() - tiempo_inicio) / 60
print(f"\n🚀 Extracción finalizada en {tiempo_total:.2f} minutos.")
