# Proyecto: Panel de Transporte CABA

## Descripción

Dashboard interactivo en **Streamlit + Folium** para visualizar líneas de colectivo
y sus paradas en la Ciudad Autónoma de Buenos Aires, usando **datos abiertos** del
Gobierno de la Ciudad (BA Data).

## Estado actual

- `app.py` es la única fuente de la app. Hay un selector de **línea de colectivo**
  (dropdown con 137 líneas + opción "Todas las líneas") y filtros de recorrido/sentido.
- Al seleccionar una línea: dibuja los **recorridos** (PolyLines coloreados por
  librea), muestra las **paradas** como CircleMarker con popup (dirección, barrio,
  comuna) y ajusta el zoom a los límites de la línea.
- En "Todas las líneas": dibuja los 1104 recorridos con **geometrías simplificadas**
  (`coords_simple`, decimación a ~30 m) para abaratar el render; opcionalmente
  superpone un **choropleth de demanda estimada por comuna** (`comunas.geojson` de
  BA Data): reparte los usos AMBA de cada línea entre sus paradas de CABA
  proporcional al nº de paradas por comuna.
- KPIs por línea (reemplazan a las viejas cajas de distancias Euclidiana/Manhattan):
  **longitud del recorrido** (precomputada como `longitud_m` en `build_routes_table`),
  **usos por día** (promedio del último mes completo) y **usos por km anual**
  (productividad = total 12 meses / km ida+vuelta). La caja SUBE conserva el
  promedio mensual, el total de 12 meses y 3 pills: vs año anterior, vs mes anterior
  y **vs mismo mes del año anterior**.
- **Benchmark de demanda**: dropdown para comparar la evolución contra el **Total
  AMBA** o una de las 20 líneas de mayor uso. El gráfico pasa a **base 100**
  (primer mes = 100) para comparar ritmos de crecimiento entre magnitudes distintas.
- **Vista "Tipo de día"**: barra con el promedio de usos diarios de la línea por
  `Día hábil / Sábado / Domingo` (últimos 12 meses completos), usando el agregado
  diario.
- **Cobertura RE-NABAP**: con el checkbox de barrios populares activo se cuentan los
  barrios cuyo centroide queda a ≤300 m del recorrido (familias y ~personas = ×4) y
  se marcan en el mapa.
- El gráfico y las cajas usan los últimos 12 meses; se descartan las líneas sin
  datos y el mes en curso si está incompleto.

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
- **Comunas**: `Comunas` (GeoJSON `comunas.geojson`, ~0,6 MB, 15 features con propiedad
  `comuna` 1..15). Usado para el choropleth de demanda por comuna. Ojo: el archivo
  trae **BOM**, por eso `load_geojson` lee con `utf-8-sig`.
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
  - https://cdn.buenosaires.gob.ar/datosabiertos/datasets/innovacion-transformacion-digital/comunas/comunas.geojson
  - https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2024.csv (usos SUBE 2024)
  - https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2025.csv (usos SUBE 2025)
  - https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2026.csv (usos SUBE 2026)

## Arquitectura de datos (importante)

- Los datos viven en la carpeta **`data/`** (local, NO versionada en git, está en `.gitignore`).
  - `data/paradas-de-colectivo.geojson`, `data/recorrido-colectivos.geojson`, `data/comunas.geojson`
  - `data/dat-ab-usos-2024.csv`, `data/dat-ab-usos-2025.csv` y `data/dat-ab-usos-2026.csv`
  - `data/sube_usos_mensuales.csv` y `data/sube_usos_diarios.csv` (**agregados derivados**,
    se regeneran solos; ~4 MB en total vs ~165 MB de los CSVs originales)
- `ensure_local_data()` crea `data/` y, si falta algún archivo, lo descarga de BA Data.
- `load_geojson(path, url)` lee el archivo local con `utf-8-sig` (tolera BOM, ej. comunas);
  si no existe, descarga.
- **Agregados SUBE**: `_build_sube_aggregates()` lee los CSV diarios
  (`AMBA=SI` + colectivo + líneas CABA por patrón de código) una sola vez y escribe
  `sube_usos_mensuales.csv` (24 meses, formato largo `linea, fecha, transacciones`) y
  `sube_usos_diarios.csv` (últimos 12 meses `linea, fecha, transacciones, tipo_dia`
  con `Día hábil/Sábado/Domingo`). La frescura se resuelve con
  `_sube_aggregates_fresh()`: compara el `built_after` del sidecar
  `sube_agregados_meta.json` contra el `mtime` máximo de los CSVs fuente. Si cambian
  los fuentes (año nuevo, mes nuevo) se regeneran. Se descarta el mes en curso si está
  incompleto (último día < fin de mes). La línea se normaliza con `zfill(3)`.
- `load_sube_transactions(token)` y `load_sube_daily(token)` leen los agregados (rápido)
  y se cachean con `@st.cache_data`; el `token = _sube_source_token()` (mtimes de fuentes)
  invalida la caché cuando cambian los datos. El gráfico/boxes usan `tail(12)`; las pills
  interanuales comparan los últimos 12 vs los 12 previos y el último mes vs el mismo mes
  del año anterior.
- `build_routes_table` precomputa por recorrido: **`longitud_m`** (haversine punto a
  punto) y **`coords_simple`** (decimado ~30 m, usado solo en "Todas las líneas"). Así
  los km del caption y el mapa agregado NO recomputan por rerun (antes se sumaba con
  numpy por punto en cada rerun).
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
- **Benchmark base 100**: comparar una línea (~10⁵-10⁶ usos/mes) contra el Total AMBA
  (~10⁷-10⁸) en ejes absolutos aplasta la serie chica. Se indexa cada serie a 100 en
  el primer mes (`_index_series`) y se superponen dos `mark_line` con `alt.layer`.
- **Cobertura y score de proximidad**: el filtro espacial por radio
  (`stops_near_route`, haversine bacheada) es genérico: se reusa tanto para las
  paradas OSM del conurbano (≤150 m) como para los centroides RE-NABAP (≤300 m).
  Los centroides de barrio se aproximan como el promedio de vértices de los polígonos.
- **Choropleth por comuna**: es una **estimación** (reparto proporcional al nº de
  paradas de CABA de cada línea), no demanda real por parada; el expander "Sobre los
  datos" lo aclara. El campo `COMUNA` de paradas trae un valor corrupto `76` que se
  descarta filtrando a 1..15. `folium.Choropleth` recibe `threshold_scale` con
  cuantiles para acotar la leyenda.
- **Agregados en disco**: los CSVs originales (~165 MB) solo se leen la primera vez
  (o cuando cambian); después se usan `sube_usos_mensuales.csv` (~160 KB) y
  `sube_usos_diarios.csv` (~4 MB). La caché de `st.cache_data` se invalida con un
  token derivado de los `mtime` de los fuentes (`_sube_source_token`), porque
  `st.cache_data` no observa archivos por sí solo.

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

- Commit + push de las fases de mejora: KPIs de transporte (usos/día, usos/km),
  benchmark base 100, vista tipo de día, cobertura RE-NABAP, choropleth por comuna
  y agregados SUBE en disco.
- Eventualmente: posiciones en tiempo real de colectivos (API de transporte, pero
  BA Data indica que las APIs/GTFS están suspendidos en revisión).

## Deploy

- La app vive en **Streamlit Community Cloud** (`https://share.streamlit.io`,
  repo `GuilleFerchero/transporte-caba`, rama `main`, entrypoint `app.py`,
  Python 3.12). `requirements.txt` fija las versiones del entorno; el primer
  render de cada sesión descarga ~190 MB de datos (los CSVs de SUBE y GeoJSON) y
  el free tier suspende la app por inactividad (almacenamiento efímero).
- **Ventaja de un `Dockerfile` (por qué lo queremos algún día):** con un
  contenedor (`python:3.12-slim` + `pip install -r requirements.txt` +
  `CMD streamlit run app.py`) la app corre en cualquier VPS, **los datos viven en
  un volumen persistente** (se descargan una sola vez, no en cada despertar) y el
  arranque queda en segundos y siempre disponible, sin los límites de memoria y
  de suspensión del Cloud gratuito; también permite escalar/aislar por proyecto.