#!/usr/bin/env python
# coding: utf-8

# In[1]:


import json
import requests
import time
import random
tiempo_inicio = time.time()

# Lista de obras que interesa descargar de los rios maipo y mapocho
#obras_a_descargar = ["OB-1302-1045", "OB-1302-1073", "OB-1302-1085", "OB-1302-1086", "OB-1302-1087", "OB-1302-1134", "OB-1302-1138", "OB-1302-1432", "OB-1303-1021", 
#                     "OB-1303-1072", "OB-1303-1128", "OB-1303-1255", "OB-1303-1280", "OB-1304-1026", "OB-1304-1097", "OB-1304-1109", "OB-1304-1122", "OB-1304-1156",
#                     "OB-1304-1157", "OB-1304-1158", "OB-1304-1168", "OB-1304-1177", "OB-1304-1193", "OB-1304-1369", "OB-1304-1370", "OB-1304-1748", "OB-1305-1005", 
#                     "OB-1305-1103", "OB-1305-1104", "OB-1305-1105", "OB-1305-1112", "OB-1305-1113", "OB-1305-1338", "OB-1305-1345", "OB-1305-1437", "OB-1305-1438", 
#                     "OB-1305-1519", "OB-1305-1853", "OB-0506-2224", "OB-0506-2226", "OB-0506-2524", "OB-0506-2605", "OB-0506-2631", "OB-0506-2710", "OB-0506-2711", 
#                     "OB-0506-2789", "OB-0506-2791", "OB-0506-2792", "OB-0506-2797", "OB-0506-2805", "OB-0506-2849", "OB-0506-2871", "OB-0506-2872", "OB-0506-2895", 
#                     "OB-0506-3015", "OB-0506-3026", "OB-0506-3120", "OB-0506-3194"]

# Lista de obras que interesa descargar de la subcuenca del estero puangue
obras_a_descargar = ["OB-1305-1139", "OB-1305-1148", "OB-1305-1149", "OB-1305-1373", "OB-1305-1374", "OB-1305-1375", "OB-1305-1740", "OB-1305-1849", "OB-1305-1855", "OB-1305-1856", "OB-1305-1857"]

# Formato fecha año-mes-dia. Si quiero datos hasta el dia n en la fecha debo escribir el dia n+1
fecha_desde = '2020-01-01'
fecha_hasta = '2026-08-01'

# Lista con los nombres de tus archivos con el listado de codigos de obras de ID de obra
archivos_json = [
    'datos_obras/obras_rm.json', 
    'datos_obras/obras_valparaiso.json', 
    'datos_obras/obras_arica.json', 
    'datos_obras/obras_atacama.json', 
    'datos_obras/obras_coquimbo_sub.json', 
    'datos_obras/obras_coquimbo_sup.json',
    'datos_obras/obras_antofagasta.json', 
    'datos_obras/obras_tarapaca.json'
]

# Aquí guardaremos todos los códigos e IDs combinados
mapa_obras_unificado = {}

for nombre_archivo in archivos_json:
    try:
        # Abrimos cada archivo en modo lectura
        with open(nombre_archivo, 'r', encoding='utf-8') as f:
            contenido = json.load(f)
            
            # Asumiendo que las obras están dentro de una lista llamada "data"
            lista_obras = contenido.get('data', [])
            
            # Recorremos cada obra del archivo
            for obra in lista_obras:
                if 'codigoObra' in obra and 'idObra' in obra:
                    codigo = obra['codigoObra']
                    id_obra = obra['idObra']
                    
                    # Agregamos el par al diccionario unificado
                    mapa_obras_unificado[codigo] = id_obra
                    
        print(f"✅ Archivo '{nombre_archivo}' procesado con éxito.")
        
    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo '{nombre_archivo}'. Revisa que esté en la misma carpeta.")
    except Exception as e:
        print(f"❌ Ocurrió un error leyendo '{nombre_archivo}': {e}")

def obtener_token():
    url_auth = "https://snia.mop.gob.cl/mee-auth-rest/v1/authorization"
    
    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json',
        'origin': 'https://snia.mop.gob.cl',
        'referer': 'https://snia.mop.gob.cl/cExtracciones2/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/150.0.0.0 Safari/537.36'
    }

    payload = {
        'apiCode': 'MEESECINT',
        'apiKey': '73A58577C1CCB258DFD79116EAD8F',
        'app': 'exponline'
    }

    response = requests.post(url_auth, json=payload, headers=headers)
    
    if response.status_code == 200:
        datos = response.json()
        return datos.get("accessToken")
    else:
        raise Exception(f"No se pudo generar el token. Estado HTTP: {response.status_code}\nRespuesta: {response.text}")

for obra in obras_a_descargar:
    id_obra = mapa_obras_unificado[obra]
    
    # Pausa aleatoria entre ejecucion del ciclo for para no colapsar pagina DGA
    pausa = random.uniform(5, 15)

    cookies = {
        '_ga_K8F0QZJDMD': 'GS2.1.s1773340527$o1$g0$t1773340537$j50$l0$h0',
        '_ga_9XJDGWBNRQ': 'GS2.1.s1784057028$o2$g1$t1784057045$j43$l0$h0',
        '_ga_Q0QGTVEB6T': 'GS2.1.s1785256583$o6$g1$t1785256630$j13$l0$h0',
        '_ga': 'GA1.1.1351968614.1766061456',
        '_ga_Y8S34E0V2R': 'GS2.1.s1785419181$o31$g1$t1785422416$j60$l0$h1725299284',
    }

    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'es-ES,es;q=0.9',
        'authorization': f'Bearer {obtener_token()}',
        'content-type': 'application/json',
        'origin': 'https://snia.mop.gob.cl',
        'referer': 'https://snia.mop.gob.cl/cExtracciones2/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
    }

    json_data = {
        'metaData': {
            'paginator': None,
            'token': None,
            'userName': None,
        },
        'data': {
            'fechaDesde': f'{fecha_desde}T03:00:00.000Z',
            'fechaHasta': f'{fecha_hasta}T02:59:59.000Z',
            'fechaDesdeLog': None,
            'fechaHastaLog': None,
            'codigoObraLog': None,
            'obras': [
                id_obra, # <-- ¡Ojo con este ID!
            ],
            'puntosRestitucion': [],
            'tipoReporte': {
                'clave': 4,
                'valor': None,
            },
            'anio': None,
            'mes': None,
            'naturaleza': 1,
            'todasAlertasObra': None,
            'tipoAlerta': None,
            'mideConCaudalimetro': True,
        },
    }

    print(f"Solicitando archivo {obra} al servidor de la DGA...")
    response = requests.post(
        'https://snia.mop.gob.cl/extracciones/data/reporte/obrasDetallado',
        cookies=cookies,
        headers=headers,
        json=json_data,
    )
    
    # --- GUARDAR EL ARCHIVO ---
    if response.status_code == 200:
        # Si la petición es exitosa, abrimos (o creamos) un archivo local en modo escritura binaria ("wb")
        nombre_archivo = f"{obra}.xls"
        
        with open(nombre_archivo, "wb") as f:
            f.write(response.content) # Guardamos los bytes recibidos en el archivo
            
        print(f"¡Éxito! El archivo se ha guardado como: {nombre_archivo}. Pausa de {pausa:.1f} segundos")
    else:
        print(f"Error al descargar. Código de estado: {response.status_code}")
        print("Detalle del error:", response.text)
    
    # Ejecuto el ciclo for con pausas entre requests 
    time.sleep(pausa)

tiempo_fin = time.time()
tiempo_total_minutos = (tiempo_fin - tiempo_inicio)/60
print(f"\n¡Proceso terminado!")
print(f"El código demoró {tiempo_total_minutos:.2f} minutos en ejecutarse.")


# In[2]:


import glob
import pandas as pd

lista_archivos = glob.glob("*.xls")

print(f"Se encontraron {len(lista_archivos)} archivos para unir.")

lista_dataframes = []

for archivo in lista_archivos:
    try:
        # Leer el archivo saltando las 4 primeras filas
        df = pd.read_excel(archivo, skiprows=4)
        
        # Eliminar la columna 'Nro. Fila' si existe
        if 'Nro. Fila' in df.columns:
            df = df.drop(columns=['Nro. Fila', 'Estado', 'Obra habilitada?', 'Canal de transmisión'])
            
        # ==========================================
        # NUEVO: ELIMINAR FILAS EN BLANCO
        # ==========================================
        # Opción A: Eliminar filas que estén COMPLETAMENTE vacías
        df = df.dropna(how='all')
        
        # Opción B (Más estricta y segura): Eliminar la fila si no tiene Código de Obra
        # Asegúrate de que el nombre de la columna coincida exactamente ('Código Obra')
        if 'Código Obra' in df.columns:
            df = df.dropna(subset=['Código Obra'])
        # ==========================================
            
        lista_dataframes.append(df)
        print(f"✔️ {archivo} procesado.")
        
    except Exception as e:
        print(f"❌ Error procesando {archivo}: {e}")

# Unir y guardar
if lista_dataframes:
    print("\nUniendo los archivos sin filas en blanco, por favor espera...")
    df_unificado = pd.concat(lista_dataframes, ignore_index=True)

    # Transformar "Fecha Registro Obra"
    if 'Fecha Registro Obra' in df_unificado.columns:
        df_unificado['Fecha Registro Obra'] = pd.to_datetime(
            df_unificado['Fecha Registro Obra'], 
            dayfirst=True,     # Indica que el formato es DD/MM/YYYY
            errors='coerce'    # Si hay un error (ej. texto inválido), lo deja en blanco (NaT) en vez de detener el script
        ).dt.date              # .dt.date elimina la hora (00:00:00) y deja solo la fecha
        
    # Transformar "Fecha (dd/mm/yyyy)"
    if 'Fecha (dd/mm/yyyy)' in df_unificado.columns:
        df_unificado['Fecha (dd/mm/yyyy)'] = pd.to_datetime(
            df_unificado['Fecha (dd/mm/yyyy)'], 
            dayfirst=True, 
            errors='coerce'
        ).dt.date
        
    archivo_salida_excel = "mediciones_consolidadas.xlsx"
    
    df_unificado.to_excel(archivo_salida_excel, index=False)
    
    print("\n¡Proceso completado exitosamente!")
    print(f"Total de registros reales consolidados: {len(df_unificado)} filas.")
    print(f"Archivo limpio guardado como: '{archivo_salida_excel}'")

else:
    print("\nNo se procesó ningún archivo.")

