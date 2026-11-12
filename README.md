# 💧 Registros-MEE: Monitoreo de Extracciones Efectivas DGA Chile

Plataforma implementada en [GitHub Pages](https://docs.github.com/es/pages) y [Render](https://render.com/) que permite visualizar y descargar la información reportada por los usuarios en el software de **Monitoreo de Extracciones Efectivas (MEE)** de la **Dirección General de Aguas (DGA)** del Ministerio de Obras Públicas de Chile. La información es consultada y extraída directamente desde el 
**[Módulo de Consulta Publica de Extracciones](https://snia.mop.gob.cl/cExtracciones2/#/busquedaPublica)** de la DGA.

Toda la información de las Obras presentada en la plataforma se obtiene directamente de la plataforma de la DGA sin modificaciones.

---

## 🗺️ Enlaces del Proyecto

* **Mapa Interactivo Nacional (GitHub Pages):**  
  👉 **[https://mferradalora.github.io/Registros-MEE/](https://mferradalora.github.io/Registros-MEE/)**
* **Servicio Backend y Visor de Series (Render):**  
  👉 **[https://registros-mee.onrender.com](https://registros-mee.onrender.com)**

---

## ⚙️ ¿Cómo funciona el proyecto?

La plataforma funciona mediante un mapa interactivo desarrollado en GitHub Page y un servicio Backend implementado en Render.

👉 **Mapa interactivo:** Alojado en GitHub Pages, permite visualizar la ubicación de más de 18.000 obras de captación y restitución superficial y subterránea a lo largo de todo el país y explorar por región y provincia. Cada punto despliega en un popup el código de obra, usuario, RUT, tipo de persona, naturaleza, comuna, provincia, región, cuenca, coordenadas UTM Norte y Este, fecha de registro de la obra en la DGA y el caudal de derecho promedio mensual.

👉 **Visor Web de Series:** Mediante el servicio Backend implementado en Render, es posible visualizar los registros reportados por los usuarios para cada Obra y descargar las series de tiempo de caudales y niveles en formato CSV.

```text
[ Mapa en GitHub Pages ] (index.html)
           │
           │  Explorar Obras a nivel nacional o por región y provincia
           │  Seleccionar obra y clic en "Ver y Descargar Mediciones MEE"
           ▼  Envía código de la obra por URL
[ Backend FastAPI en Render ] (main_mee.py)
           │
           ├── ¿Existen mediciones en la base de datos local?
           │        ├── SÍ ──> Retorna las series de tiempo de los registros existentes.
           │        └── NO ──> extractor_mee.py autentica con JWT, consulta DGA SNIA, guarda en SQLite y retorna las series de tiempo.
           ▼
[ Visor Ultraliviano ] (visor_mee.html)
     ├── Gráfico interactivo Chart.js (Caudal en l/s y Nivel freático/limnimétrico en m).
     ├── Encabezado con Código de Obra, Titular/Usuario y metadatos administrativos.
     └── Exportación de los registros al hacer clic en el botón "Descargar CSV".
```

---

## 📂 Estructura del Repositorio

```text
Registros-MEE/
├── data/
│   ├── catalogo_obras_mee.csv   # Catálogo de obras registradas en MEE DGA (18.731 obras georreferenciadas)
│   ├── Regiones_Chile.geojson   # Límites regionales
│   └── Provincias_Chile.geojson # Límites provinciales
├── database_mee.py              # Capa SQL: inicialización, almacenamiento y caché SQLite
├── extractor_mee.py             # Motor de autenticación JWT y parseo con Calamine del servicio DGA
├── index.html                   # Mapa interactivo desplegado en GitHub Pages
├── main_mee.py                  # Backend FastAPI: endpoints API REST y servicio del visor HTML
├── mapa_mee.py                  # Script generador del mapa Folium con filtros y popups enriquecidos
├── requirements.txt             # Dependencias del servidor web, extracción y motores de lectura Excel
├── visor_mee.html               # Frontend ligero para visualización registros y descarga CSV
├── LICENSE                      # Licencia MIT de código abierto
└── README.md                    # Documentación general del proyecto
