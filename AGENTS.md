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
- Al seleccionar una línea: además del mapa muestra un **gráfico de línea** con el
  evolutivo mensual de **transacciones SUBE (usos)** por línea para todo el **AMBA**
  (fuente: dataset nacional "Cantidad de transacciones SUBE (usos) por fecha" de la
  Secretaría de Transporte) y el caption informa la **distancia del recorrido en km**
  (suma de distancias haversine punto a punto).
- El gráfico cubre los últimos 12 meses de usos diarios agregados por mes; se
  descartan las líneas sin datos y el mes en curso si está incompleto.

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
- **Transacciones SUBE**: Secretaría de Transporte (datos.transporte.gob.ar) →
  "SUBE - Cantidad de transacciones (usos) por fecha" (CSV diario por línea,
  `dat-ab-usos-2025.csv` y `dat-ab-usos-2026.csv`, ~65 MB y ~47 MB).
  - Una fila por día-línea. Columnas: `DIA_TRANSPORTE`, `NOMBRE_EMPRESA`, `LINEA`,
    `AMBA` (SI/NO), `TIPO_TRANSPORTE`, `JURISDICCION`, `PROVINCIA`, `MUNICIPIO`,
    `CANTIDAD`, `DATO_PRELIMINAR`. Cobertura diaria de todo el país; se filtra
    `AMBA=SI` + `TIPO_TRANSPORTE=COLECTIVO`.
  - Identificación de líneas CABA: las líneas nacionales salen como `JURISDICCION`
    `NACIONAL` (códigos `LINEA N`, `BSAS_LINEA_XXX`, `BS_ASLINEA_XXX`) o `C.A.B.A`
    (códigos `CABA_LINEA_XXX`, que desde 2026 son los dominantes). Se excluyen
    códigos con `RZ` (Zárate) y los numéricos pelados de municipios del interior.
    Ver `_is_caba_sube_row()`.
  - Coherencia verificada contra el dataset de demanda de BA Data (mediana +0,17%);
    las diferencias >5% son líneas largas de conurbano donde el dato nacional suma
    el AMBA completo, lo cual es el objetivo.
  - Hay recursos anuales; si el dataset renueva años hay que agregar/actualizar las
    URLs en `SUBE_USOS_2024_URL`/`SUBE_USOS_2025_URL`/`SUBE_USOS_2026_URL`. El loader
    lee 2024+2025+2026 y conserva **24 meses** (para comparaciones interanuales); el
    gráfico y el total de la caja usan siempre los últimos 12.
- URL de descarga (fallback):
  - https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos-recorridos/recorrido-colectivos.geojson
  - https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos-paradas/paradas-de-colectivo.geojson
  - https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2024.csv (usos SUBE 2024)
  - https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2025.csv (usos SUBE 2025)
  - https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2026.csv (usos SUBE 2026)

## Arquitectura de datos (importante)

- Los datos viven en la carpeta **`data/`** (local, NO versionada en git, está en `.gitignore`).
  - `data/paradas-de-colectivo.geojson`
  - `data/recorrido-colectivos.geojson`
  - `data/dat-ab-usos-2024.csv`, `data/dat-ab-usos-2025.csv` y `data/dat-ab-usos-2026.csv`
- `ensure_local_data()` crea `data/` y, si falta algún archivo, lo descarga de BA Data.
- `load_geojson(path, url)` lee el archivo local; si no existe, descarga.
- `load_sube_transactions()` lee los CSV de usos diarios (`AMBA=SI` + colectivo +
  líneas CABA por patrón de código), los agrega a **24 meses** (necesario para el
  comparativo interanual) y devuelve formato largo `(linea, fecha, transacciones)`.
  Se descarta el mes en curso si está incompleto (último día < fin de mes). La línea
  se normaliza con `zfill(3)`. El gráfico y el total/promedio de la caja usan siempre
  el último año (`tail(12)`); la caja SUBE muestra pills interanuales (últimos 12 vs
  los 12 previos) e intermensuales (último mes vs el anterior).
- `_route_distance_m(route_row)` suma distancias haversine punto a punto sobre las
  coordenadas del recorrido (devuelve metros). La distancia por línea (km) se resume
  en el caption.
- Todo el procesamiento está cacheado con `@st.cache_data` (tablas de stops y routes
  en pandas), para no reparsear los 15 MB en cada rerun.
- `data/` está en `.gitignore`. Para regenerar testear offline borrar archivos localmente y la app descarga sola.

## Detalles técnicos / lecciones aprendidas

- **Sin reruns al interactuar con el mapa**: `st_folium` por defecto devuelve el
  estado del mapa (bounds, zoom, clics) en cada interacción y eso provoca que
  Streamlit re-ejecute el script. Se corrigió con `returned_objects=[]` en la
  llamada `st_folium(m, width="100%", height=650, returned_objects=[])`.
  (Commiteado en `4e4013a`.)
- Normalización de líneas en SUBE nacional: los códigos son inconsistentes entre
  años y jurisdicciones. Regla usada en `_is_caba_sube_row()`: códigos con prefijo
  `CABA`/`BSAS_LINEA`/`BS_ASLINEA` → siempre CABA; los `LINEA N` pelados solo si
  `JURISDICCION` es `NACIONAL` o `C.A.B.A`; se descartan `RZ`. El número de línea
  se extrae como el primer grupo de dígitos (`re.search(r"\d+")`). NO filtras solo
  con `AMBA=SI`: colisionan líneas homónimas de Mercedes/Zárate (ej. `LINEA 1`,
  `RZ-1`).
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
  - `4e4013a` Evolutivo mensual de transacciones SUBE por línea + distancia en km;
    fix de reruns `returned_objects=[]`; AGENTS.md

## Entorno

- Windows, shell PowerShell. Python 3.13.2. La app corre en el venv `venv/` del repo.
- Librerías: streamlit 1.62.0, folium 0.20.0, streamlit-folium 0.27.4, pandas 2.2.3,
  requests 2.32.3.

## Pendientes / ideas

- Commit + push de la migración a la fuente nacional de usos SUBE (AMBA completo).
- Eventualmente: posiciones en tiempo real de colectivos (API de transporte, pero
  BA Data indica que las APIs/GTFS están suspendidos en revisión).