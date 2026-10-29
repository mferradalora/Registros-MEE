# 💧 Registros-MEE: Monitoreo de Extracciones Efectivas DGA Chile

Plataforma integral de cartografía interactiva, almacenamiento en base de datos local, visualización y descarga de series de tiempo de las obras registrada en el software de **Monitoreo de Extracciones Efectivas (MEE)** de la **Dirección General de Aguas (DGA)** del Ministerio de Obras Públicas de Chile. La información es consultada y extraída directamente desde el 
**Módulo de Consulta Publica de Extracciones [https://snia.mop.gob.cl/cExtracciones2/#/busquedaPublica](https://snia.mop.gob.cl/cExtracciones2/#/busquedaPublica)** de la DGA.

---

## 🗺️ Enlaces del Proyecto

* **Mapa Interactivo Nacional (GitHub Pages):**  
  👉 **[https://mferradalora.github.io/Registros-MEE/](https://mferradalora.github.io/Registros-MEE/)**
* **Servicio Backend y Visor de Series (Render):**  
  👉 **[https://registros-mee.onrender.com](https://registros-mee.onrender.com)**

---

## ⚙️ ¿Cómo Funciona el Proyecto?

El sistema opera bajo una arquitectura desacoplada diseñada para evitar la saturación y los tiempos de espera (*timeouts*) del servidor oficial de la DGA:

```text
[ Mapa en GitHub Pages ] (index.html)
           │
           │  Clic en "Ver y Descargar Mediciones MEE"
           ▼  (Envía código de la obra por URL)
[ Backend FastAPI en Render ] (main_mee.py)
           │
           ├── ¿Existen mediciones en la base de datos local?
           │        ├── SÍ ──> Retorna datos al instante (< 0.1 s).
           │        └── NO ──> extractor_mee.py autentica con JWT, consulta DGA SNIA, guarda en SQLite y retorna.
           ▼
[ Visor Ultraliviano ] (visor_mee.html)
     ├── Gráfico interactivo Chart.js (Caudal en l/s y Nivel freático/limnimétrico en m).
     ├── Encabezado con Código de Obra, Titular/Usuario y metadatos administrativos.
     └── Exportación directa a CSV: [codigo_obra, usuario, fecha_hora, caudal_ls, totalizador_m3, nivel_m].
```

👉 **Visor Cartográfico (Frontend estático):** Alojado en GitHub Pages, visualiza georreferenciadamente más de 18.000 obras de captación superficial y subterránea a lo largo de todo el país, con selector dinámico jerárquico por Región y Provincia. Cada punto despliega en su popup el código de obra, usuario, RUT, tipo de persona, cuenca, coordenadas UTM oficiales, fecha de registro y caudal de derecho promedio mensual.

👉 **Capa de Persistencia y Caché (SQLite):** Implementada en database_mee.py, almacena cada medición horaria o diaria rescatada, permitiendo que consultas posteriores sobre una misma obra respondan en milisegundos.

👉 **Motor de Extracción Resiliente:** En extractor_mee.py, adquiere dinámicamente credenciales JWT Bearer ante la DGA, consulta el servicio obrasDetallado, procesa los reportes binarios en formato Excel mediante python-calamine y normaliza las series temporales.

👉 **Visor Web de Series:** A través de visor_mee.html, genera visualizaciones interactivas de caudales y niveles con Chart.js y permite la descarga limpia de planillas CSV en memoria.

---

## 📂 Estructura del Repositorio

```text
Registros-MEE/
├── data/
│   ├── catalogo_obras_mee.csv   # Catálogo oficial nacional MEE DGA (18.731 obras georreferenciadas)
│   ├── Regiones_Chile.geojson   # Geometrías oficiales de límites regionales
│   └── Provincias_Chile.geojson # Geometrías oficiales de límites provinciales
├── database_mee.py              # Capa SQL: inicialización, almacenamiento y caché SQLite
├── extractor_mee.py             # Motor de autenticación JWT y parseo con Calamine del servicio DGA
├── index.html                   # Visor cartográfico nacional interactivo desplegado en GitHub Pages
├── main_mee.py                  # Backend FastAPI: endpoints API REST y servicio del visor HTML
├── mapa_mee.py                  # Script generador del mapa Folium con filtros y popups enriquecidos
├── requirements.txt             # Dependencias del servidor web, extracción y motores de lectura Excel
├── visor_mee.html               # Frontend ligero para visualización de curvas temporales y descarga CSV
├── LICENSE                      # Licencia MIT de código abierto
└── README.md                    # Documentación general del proyecto
