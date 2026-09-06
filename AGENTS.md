# Proyecto: Panel de Transporte CABA

## Descripción

Dashboard interactivo en **Streamlit + Folium** para visualizar líneas de colectivo
y sus paradas en la Ciudad Autónoma de Buenos Aires, usando **datos abiertos** del
Gobierno de la Ciudad (BA Data).

## Estado actual

- `app.py` es la única fuente de la app. Hay un selector de **línea de colectivo**
  (dropdown con 137 líneas + opción "Todas las líneas").
- Al seleccionar una línea: dibuja los **recorridos** (PolyLines coloreados por
  sentido: ida #1a73e8, vuelta #e8710a), muestra las **paradas** como CircleMarker
  con popup (dirección, barrio, comuna) y ajusta el zoom a los límites de la línea.
- En "Todas las líneas": dibuja los 1104 recorridos, cada línea con un color de una
  paleta (10 colores cíclicos, `color_for_line()`).

## Fuentes de datos (BA Data, licencia CC-BY-2.5-AR)

- **Recorridos**: `Colectivos: recorridos` (GeoJSON `recorrido-colectivos.geojson`, ~11,8 MB)
  - 1104 features `MultiLineString`.
  - Propiedades útiles: `linea` (string "001"), `recorrido`, `sentido` (IDA/VUELTA),
    `modalidad`, `desde`, `hasta`.
- **Paradas**: `Colectivos: paradas` (GeoJSON `paradas-de-colectivo.geojson`, ~3,3 MB)
  - 6962 features `Point` (coordenadas lon/lat en la geometría).
  - Propiedades: `DIRECCION`, `BARRIO`, `COMUNA` y campos `L1`..`L6` (líneas que
    pasan por esa parada, string o null). Hay un valor corrupto `'V'` en algún campo
    L* que se descarta (solo se aceptan valores `isdigit()`).
- URL de descarga (fallback):
  - https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos-recorridos/recorrido-colectivos.geojson
  - https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos-paradas/paradas-de-colectivo.geojson

## Arquitectura de datos (importante)

- Los datos viven en la carpeta **`data/`** (local, NO versionada en git, está en `.gitignore`).
  - `data/paradas-de-colectivo.geojson`
  - `data/recorrido-colectivos.geojson`
- `ensure_local_data()` crea `data/` y, si falta algún archivo, lo descarga de BA Data.
- `load_geojson(path, url)` lee el archivo local; si no existe, descarga.
- Todo el procesamiento está cacheado con `@st.cache_data` (tablas de stops y routes
  en pandas), para no reparsear los 15 MB en cada rerun.
- `data/` está en `.gitignore`. Para regenerar testear offline borrar archivos localmente y la app descarga sola.

## Detalles técnicos / lecciones aprendidas

- **Sin reruns al interactuar con el mapa**: `st_folium` por defecto devuelve el
  estado del mapa (bounds, zoom, clics) en cada interacción y eso provoca que
  Streamlit re-ejecute el script. Se corrigió con `returned_objects=[]` en la
  llamada `st_folium(m, width="100%", height=650, returned_objects=[])`.
  → ESE CAMBIO AÚN NO ESTÁ COMMITEADO. Commit pendiente.
- Normalización de líneas: en recorridos la línea es "001" (3 dígitos), en paradas
  puede ser "22" o "1". Se normaliza con `str(linea).zfill(3)` en ambas tablas.
- Tabla de paradas se arma en formato largo (1 fila por parada × línea que la sirve)
  y se deduplica por `(linea, lat, lon)`.
- El mapa se reinicia en cada selector de línea (sin `key` en st_folium) para que
  se remonte con la línea nueva.

## Cómo correr la app

```
streamlit run app.py
```

- App suele correrse en puerto 8501: `streamlit run app.py --server.port 8501`
- Para probar sin navegador se usa AppTest:
  ```python
  from streamlit.testing.v1 import AppTest
  at = AppTest.from_file("app.py", default_timeout=120)
  at.run()
  at.selectbox[0].select("022")
  at.run()
  print(at.exception)  # debe ser vacío
  ```
- Verificar sintaxis: `python -m py_compile app.py`

## Git / GitHub

- Repo: `https://github.com/GuilleFerchero/transporte-caba.git` (rama `main`)
- Historial:
  - `38a6525` Primer commit: estructura inicial
  - `241d660` Agregar app.py (mapa base)
  - `b10849a` Visualización de líneas de colectivo y paradas con datos de BA Data
  - `1afb41d` Lectura local de `data/` con descarga como respaldo; `data/` en .gitignore
- **PENDIENTE**: commitear y pushear el cambio `returned_objects=[]` (app.py),
  y el AGENTS.md.

## Entorno

- Windows, shell PowerShell. Python 3.13.2.
- Librerías instaladas (global, sin venv): streamlit 1.62.0, folium 0.20.0,
  streamlit-folium 0.27.4, pandas 2.2.3, requests 2.32.3.

## Pendientes / ideas

- Commit + push del fix de reruns y de este AGENTS.md.
- Eventualmente: posiciones en tiempo real de colectivos (API de transporte, pero
  BA Data indica que las APIs/GTFS están suspendidos en revisión).