# Proyecto: Panel de Transporte CABA

## Descripción

Dashboard interactivo en **Streamlit + Folium** para visualizar líneas de colectivo
y sus paradas en la **Ciudad Autónoma de Buenos Aires y el Área Metropolitana de
Buenos Aires (AMBA)**, usando **datos abiertos** del Gobierno de la Ciudad (BA Data)
y la Secretaría de Transporte (RMBA).

## Estado actual

- **Tres apps separadas** comparten un módulo de datos común:
  - `app_transporte.py` → análisis de **transporte público** (recorridos, paradas,
    demanda SUBE, subte, ferrocarril). Es el `app.py` histórico refactorizado.
  - `app_acceso.py` → análisis de **acceso a la ciudad desde barrios populares**
    (cobertura RE-NABAP de colectivo/subte/ferro, KPIs de cobertura, resumen por partido).
  - `app_subte.py` → análisis de **viajes del Subte por molinete** (SBASE/BA Data):
    mapa de estaciones coloreadas y escaladas por viajes (con popup), comparación
    interanual (año y último mes completo), slider de franja horaria que recolorea
    todo, hora pico automática y perfiles horarios. No llama a `ensure_local_data()`
    (evita la descarga de ~190 MB de SUBE/AMBA): usa solo los loaders geojson on-demand.
  - `data_loaders.py` → **módulo compartido**: constantes/URLs, colores/libreas,
    funciones de geometría (haversine, simplificación), carga y transformación de
    todos los datasets (cacheadas con `@st.cache_data`), dibujo en Folium, helpers
    de formato y el CSS `THEME_CSS`.
  - `backup/app.py` conserva la app original como referencia histórica.
- `app_transporte.py`: hay un selector de **línea de colectivo**
  (dropdown con ~304 líneas AMBA + opción "Todas las líneas") y filtros de
  recorrido/sentido.
- **Filtro de jurisdicciones** (multiselect `CABA / NACIONAL / PROVINCIAL / MUNICIPAL`,
  default las 4; reemplaza al viejo toggle AMBA/CABA). Filtra recorridos, control de
  líneas del dropdown, mapas y captions; la **demanda SUBE es siempre AMBA** (se muestra
  un caption aclarándolo). `osm_force` aplica a cualquier línea sin paradas CABA, sin
  importar el filtro. En "Todas las líneas" el `fit_bounds` se calcula al bounding box
  de los recorridos visibles (fallback `AMBA_BUS_BOUNDS`).
- Hay dos **overlays opcionales**: `Subte (CABA)` (líneas + estaciones)
  y `Ferrocarril (AMBA)` (líneas `ambalineas.geojson` + estaciones
  `estaciones-de-ferrocarril.geojson` de BA Data, 230 paradas con nombre).
- Al seleccionar una línea: dibuja los **recorridos** (PolyLines coloreados por
  librea), muestra las **paradas** como CircleMarker con popup (dirección, barrio,
  comuna) y ajusta el zoom a los límites de la línea.
- **Paradas del conurbano**: las líneas que no tienen paradas CABA registradas (p.ej.
  RMBA municipales 500+ o provinciales que no entran a Capital) **fuerzan la capa
  OSM**: se cuentan y dibujan automáticamente las paradas de OpenStreetMap a ≤150 m
  del recorrido, sin tildar el checkbox.
- En "Todas las líneas" (AMBA): dibuja los ~1274 recorridos con **geometrías
  simplificadas** (`coords_simple`, decimación a ~30 m) como **una única capa
  `folium.GeoJson`** (`routes_to_geojson` + `GeoJsonTooltip` con línea/ramal/sentido);
  se colorean **por jurisdicción**: librea para CABA/nacional, verde provincial,
  naranja municipal (40.058 km acumulados, con `fit_bounds` al AMBA). En CABA sigue el
  **choropleth de demanda estimada por comuna** (`comunas.geojson` de BA Data): reparte
  los usos AMBA de cada línea entre sus paradas de CABA proporcional al nº de paradas.
- KPIs por línea (reemplazan a las viejas cajas de distancias Euclidiana/Manhattan):
  **longitud del recorrido** (precomputada como `longitud_m` en `build_routes_table`),
  **usos por día** (promedio del último mes completo) y **usos por km anual**
  (productividad = total 12 meses / km ida+vuelta). La caja SUBE conserva el
  promedio mensual, el total de 12 meses y 3 pills: vs año anterior, vs mes anterior
  y **vs mismo mes del año anterior**.
- **Vista "Tipo de día"**: barra con el promedio de usos diarios de la línea por
  `Día hábil / Sábado / Domingo / Feriado` (últimos 12 meses completos), usando el
  agregado diario. Los feriados nacionales (inamovibles, trasladables y puentes) se
  toman de `FERIADOS_ARG` (set estático 2024-2027, fuente api.argentinadatos.com);
  al entrar un año nuevo hay que actualizarlo.
- **Vista "Semana tipo"**: barra con el promedio de usos diarios por día de la semana
  (Lunes a Domingo) del mismo período de 12 meses.
- **Ranking de productividad AMBA**: tabla ordenable por **usos por
  km anual**, usos por día, usos 12m o variación interanual, con filtro de
  jurisdicción (CABA/NACIONAL, PROVINCIAL, MUNICIPAL) y selector top 10/20/50/Todas;
  exportable en CSV. El km de cada línea es la suma de `longitud_m` (ida+vuelta) de
  sus recorridos; usos por km = total 12m / km.
- **Cobertura RE-NABAP**: el análisis completo vive en **`app_acceso.py`** (el checkbox
  de `app_transporte.py` solo dibuja los polígonos como capa informativa). En
  `app_acceso.py` el checkbox de barrios populares está disponible **siempre**
  (no requiere seleccionar un colectivo) y mide los barrios cuya **frontera** cae a
  ≤300 m de la red de colectivo AMBA completa y/o de las redes de **subte y
  ferrocarril** activadas (familias y ~personas = ×4), los muestra en el mapa
  coloreados por estado (verde = con cobertura, rojo = sin) y arma un resumen por
  partido descargable en CSV. La cobertura usa **todos** los recorridos AMBA
  simultáneamente; por eso se calcula con una **grilla espacial** (`build_point_grid`
  + `_grid_matches`, células de 100 m) en vez de `stops_near_route` (que tardaba ~6 min
  para todo el AMBA; la grilla lo
  hace en ~1 s). Para no saturar el mapa, el colectivo está **oculto por defecto**;
  al seleccionar un barrio (select de la sidebar o **clic sobre el polígono** en el
  mapa, vía `last_object_clicked`/`last_clicked` de `st_folium` + point-in-polygon
  `_find_barrio_at`) se dibujan solo las líneas de transporte cercanas:
  colectivo a ≤ `BARRIO_BUS_RADIUS_M` (500 m) y subte/ferrocarril a ≤
  `BARRIO_RAIL_RADIUS_M` (1200 m), con sus estaciones recortadas a las líneas
  visibles. Los polígonos RE-NABAP se dibujan **debajo** de las líneas para no
  taparlas (orden de dibujo) y los trazos de colectivo llevan popup con
  línea/ramal/sentido (`draw_route(..., popup=...)`).
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
- **Recorridos RMBA (Secretaría de Transporte, datos.transporte.gob.ar)** — dataset
  `recorridos-de-lineas-de-transporte-rmba-jn`:
  - `rmba_nacional.geojson` (1172 features, JURISDICCI "NACIONAL", `LINEA`/`RAMAL`/
    `SENTIDO` IDA o VUELTA) → recurso `84947471-9c1e-4a23-8a2e-03a8c87c056f`.
  - `rmba_provincial.geojson` (600 features, JURISDICCI "PROVINCIAL", `SENTIDO` 0/1) →
    recurso `f95e25bc-a6b2-4a78-a04b-35fa437be96b`.
  - `rmba_municipal.geojson` (459 features `LineString`, `LINEA` 501..557) →
    recurso `f0f3791a-addc-4143-bb95-ef0e8bca5bd8`.
  - URL base de recursos: `https://datos.transporte.gob.ar/dataset/f87b93d4-ade2-44fc-a409-d3736ba9f3ba/resource/<id>/download/<archivo>`.
  - **Geometrías con >2 dims**: hay que sanitizar a `(lon, lat)` (2 dims) y aceptar
    `LineString` y `MultiLineString`. Se usa `_clean_route_coords()`.
  - Aportan **170 líneas nuevas** (7 nacionales + 106 provinciales + 57 municipales);
    147 de ellas tienen datos SUBE. La dedupe contra BA Data es **por número de línea**
    (BA Data ya cubre todo el AMBA con geometría casi idéntica a la nacional RMBA).
- **Subte/ferrocarril (RMBA)** — `subte_lineas.geojson` (79, `LINEASUB`),
  `subte_estaciones.geojson` (86, `ESTACION`/`LINEA`), `ffcc_lineas.geojson`
  (23, `Linea`/`Descrip`). Las **estaciones de ferrocarril** se toman de BA Data
  (`estaciones-ferrocarril`, 230 paradas con `nombre`/`linea`/`ramal`/`long`/`lat`),
  no del KML `ambapuntos.kml` de RMBA (302 puntos sin nombres).
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
- **Viajes del Subte por molinete (SBASE/BA Data)** — dataset
  `subte-viajes-molinetes`: pasajeros por molinete y estación en rangos de **15 min**,
  con tipo de pasaje. Años 2013–2026 en **ZIP por año** descargables de la CDN:
  `https://cdn.buenosaires.gob.ar/datosabiertos/datasets/sbase/subte-viajes-molinetes/molinetes-<YYYY>.zip`.
  (`data.buenosaires.gob.ar` bloquea requests sin **User-Agent de navegador** —WAF—;
  la CDN funciona con cualquier UA. IDs de recurso (2024=`9faf4137-…`, 2025=`0d689701-…`,
  2026=`f4689712-…`) solo sirven para el `package_show` de la API CKAN; `datastore_search`
  da 404 para estos ZIP.)
  - Detalle del esquema (2024-2026 idéntico): CSV con **cada línea entera entre
    comillas**, separador `;`, BOM, fecha `D/M/YYYY`. Columnas:
    `FECHA;DESDE;Hasta>;LINEA;MOLINETE;ESTACION;pax_pagos;pax_pases_pagos;pax_franq;pax_TOTAL`.
    Hay un archivo por mes y grupo de líneas: `<YYYYMM>_PAX15min-ABC-…`, `-DEH-`, `-PM-`
    (2024: solo diciembre lleva la etiqueta `INCLUYEOTROMODOSDEPAGO`). Premetro =
    `LineaPM` (sin geometría en el geojson).
  - **Codificación**: 2024/2025 se leen con `latin-1`, 2026 con `utf-8-sig`
    (`_decode_molinete`). Se agrega a **hora** usando el inicio `DESDE` y `pax_TOTAL`
    (todas las modalidades de pago). Se descartan estaciones `#n/d`, `null`, `prueba`
    y vacías. 2026 es parcial (enero–junio). Ver `_ingest_molinete_zip()`.
  - Últimos agregados: 1.457.749 filas, 502.303.045 viajes, 2024–2026, 88 estaciones
    (81 con coords). La estación se normaliza por **alias** (`MOLINETES_STATION_ALIAS`,
    p.ej. `CARLOS PELLEGRINI→C. PELLEGRINI`, `FLORES→SAN JOSE DE FLORES`,
    `PALERMO→PALERMO - ACHÁVAL RODRÍGUEZ`, `HUMB——→HUMBERTO 1`) +
    `_canon_molinete_station` (alias → geojson → fallback a strip del
    `Plataforma .B`/` E`).
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
  - `data/rmba_nacional.geojson`, `data/rmba_provincial.geojson`, `data/rmba_municipal.geojson`
  - `data/subte_lineas.geojson`, `data/subte_estaciones.geojson`, `data/ffcc_lineas.geojson`,
    `data/ffcc_estaciones.geojson` (BA Data, con nombres)
  - `data/molinetes/molinete_<YYYY>.zip` (ZIP fuente de SBASE; `_ingest_molinete_zip`
    baja vía CDN si el ZIP de un año no existe localmente), `data/molinetes_subte.csv`
    (**agregado por hora/estación**, ~48 MB, `linea, fecha, hora, estacion, viajes`) y
    `data/molinetes_agg_meta.json` (sidecar `built_after`/`schema_version`).
- `ensure_local_data()` crea `data/` y, si falta algún archivo, lo descarga de BA Data
  (las fuentes AMBA —RMBA, subte/ferro— son tolerantes: si fallan, la app degrada a CABA).
- `load_geojson(path, url)` lee el archivo local con `utf-8-sig` (tolera BOM, ej. comunas);
  si no existe, descarga.
- **Agregados SUBE**: `_build_sube_aggregates()` lee los CSV diarios
  (`AMBA=SI` + colectivo + líneas CABA por patrón de código) una sola vez y escribe
  `sube_usos_mensuales.csv` (24 meses, formato largo `linea, fecha, transacciones`) y
  `sube_usos_diarios.csv` (últimos 12 meses `linea, fecha, transacciones, tipo_dia`
  con `Día hábil/Sábado/Domingo/Feriado`; los feriados salen de `FERIADOS_ARG`).
  El sidecar `sube_agregados_meta.json` guarda `built_after` y `schema_version`
  (`SUBE_AGG_SCHEMA_VERSION = 2`): si el esquema cambia (p.ej. nueva categoría de
  día) se regeneran los agregados aunque los fuentes no hayan cambiado. La frescura
  se resuelve con `_sube_aggregates_fresh()`: compara el `built_after` del sidecar
  contra el `mtime` máximo de los CSVs fuente. Si cambian los fuentes (año nuevo,
  mes nuevo) se regeneran. Se descarta el mes en curso si está incompleto (último
  día < fin de mes). La línea se normaliza con `zfill(3)`.
- `load_sube_transactions(token)` y `load_sube_daily(token)` leen los agregados (rápido)
  y se cachean con `@st.cache_data`; el `token = _sube_source_token()` (mtimes de fuentes)
  invalida la caché cuando cambian los datos. El gráfico/boxes usan `tail(12)`; las pills
  interanuales comparan los últimos 12 vs los 12 previos y el último mes vs el mismo mes
  del año anterior.
- **Agregados molinetes**: `_build_molinetes_aggregates()` ingesta los ZIP
  descargados (parsea cada fila, normaliza estación) y escribe
  `data/molinetes_subte.csv` (una fila por `linea, fecha, hora, estacion`) y el
  sidecar `molinetes_agg_meta.json`. La frescura usa `_molinetes_aggregates_fresh()`
  (compara `built_after` del sidecar contra el mtime del ZIP más nuevo; si solo hay
  un ZIP nuevo, no re-ingesta los otros años). `load_molinetes(token)` con
  `token = _molinetes_source_token()` lee el CSV agregado (~1 s, en vez de ~300 s de
  parsear los ZIP). `helper de nombres`: `load_subte_stations_geo()` devuelve una fila
  por estación del geojson con `nombre` normalizado (mismas reglas que molinetes) +
  lat/lon/línea.
- `build_routes_table` precomputa por recorrido: **`longitud_m`** (haversine punto a
  punto) y **`coords_simple`** (decimado ~30 m, usado solo en "Todas las líneas"). Así
  los km del caption y el mapa agregado NO recomputan por rerun (antes se sumaba con
  numpy por punto en cada rerun).
- `build_routes_table_amba(routes_fc, sources)` consolida BA Data + RMBA. La dedupe es
  **por número de línea** (`_norm_rmba_linea`, primer grupo de dígitos + `zfill(3)`): la
  geometría RMBA nacional es casi idéntica a BA Data, así que solo se agregan las líneas
  que BA Data no tiene. Columnas: `linea, recorrido, sentido, modalidad, desde, hasta,
  coords, coords_simple, longitud_m, jurisdiccion` (`CABA | NACIONAL | PROVINCIAL |
  MUNICIPAL`).
- **Paradas OSM / bbox**: `OSM_AMBA_BBOX = "(-35.20,-59.45,-34.00,-57.85)"` cubre el
  AMBA oeste completo (La Plata, Moreno, Ezeiza). Si se agrandó el bbox y quedó un
  `paradas_amba_osm.geojson` viejo localmente, borrarlo para que re-descargue.
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
- **Cobertura y score de proximidad**: el filtro espacial por radio
  (`stops_near_route`, haversine bacheada) es genérico: se reusa tanto para las
  paradas OSM del conurbano (≤150 m, sobre ~1 línea/recorrido) como para la cobertura
  RE-NABAP. Para RE-NABAP la cercanía se mide contra los **vértices de la frontera** de cada
  polígono (`load_renabap_points`), NO contra el centroide: barrios alargados (p.ej.
  Villa Itatí) bordean la ruta pero su centroide cae a >300 m y quedarían afuera. El
  centroide se usa solo para ubicar el marcador (`load_renabap_centroids`, promedio
  de vértices). En `app_acceso.py` la cobertura se mide contra **todo el AMBA a la vez**
  (~444k puntos de recorridos × ~22k vértices RE-NABAP); `stops_near_route` tardaba
  ~6 min, así que se usa `renabap_covered_ids` (grilla de 100 m sobre los puntos de red
  y búsqueda local de ≤±celdas vecinas para cada vértice de barrio, ~1 s).
- **Cobertura fija con caché tipo-token**: `bus_network`/`subte_network`/`ffcc_network`
  y `renabap_covered_ids`/`lines_near_barrio` se cachean con `@st.cache_data` pasando
  **tokens derivados de los `mtime`** de los fuentes (nunca DataFrames con columnas de
  listas como `coords`), evitando re-embeber ~444k coordenadas por rerun y el warning
  "unhashable type: 'list'". `lines_near_barrio(bar_id, radius_m, network)` devuelve
  los índices de fila de las líneas de esa red a ≤radio del barrio (el orden de filas
  coincide con el `routes_df` de la app).
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
- **Descargas opcionales resilientes (Cloud)**: en Streamlit Cloud el storage es
  efímero, así que cada sesión re-descarga los datos. La descarga de paradas OSM
  (Overpass) solía correr al arranque dentro de `ensure_local_data()` y un error
  HTTP del endpoint público (`overpass.kumi.systems` devuelve 429/502) rompía toda
  la app con pantalla roja. Ahora: (a) el OSM se descarga **lazy** recién al tildar
  el checkbox (con fallback a `overpass-api.de` vía `OSM_STOPS_URLS`); (b) los CSVs
  SUBE y el RE-NABAP de arranque degradan con warning en vez de lanzar; (c) las
  funciones de lectura (`_build_sube_aggregates`, `load_sube_daily`,
  `load_sube_transactions`, `load_renabap_centroids`) devuelven DataFrames vacíos
  con `st.warning` si fallan. Solo las fuentes core (paradas, recorridos, comunas)
  siguen fallando duro.

## Cómo correr la app

```
streamlit run app_transporte.py   # Transporte público (recorridos + demanda SUBE)
streamlit run app_acceso.py       # Acceso a la ciudad / cobertura RE-NABAP
streamlit run app_subte.py        # Viajes del Subte por molinete (SBASE)
```

- `backup/app.py` se conserva como referencia histórica (backup de la app original).
- App suele correrse en puerto 8501: `streamlit run app_transporte.py --server.port 8501`
- Para probar sin navegador se usa AppTest:
  ```python
  from streamlit.testing.v1 import AppTest
  at = AppTest.from_file("app_acceso.py", default_timeout=300)
  at.run()
  print(at.exception)  # debe ser vacío
  ```
- Verificar sintaxis: `python -m py_compile data_loaders.py app_transporte.py app_acceso.py app_subte.py`

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
- Librerías: streamlit 1.63.0, folium 0.20.0, streamlit-folium 0.27.4, pandas 3.0.5,
  numpy 2.5.2, altair 6.2.2, requests 2.32.3.

## Pendientes / ideas

- Eventualmente: posiciones en tiempo real de colectivos (API de transporte, pero
  BA Data indica que las APIs/GTFS están suspendidos en revisión).
- Pulir: en "Todas las líneas" AMBA el render de 1274 recorridos ya se dibuja como una
  sola capa `folium.GeoJson` (`routes_to_geojson`, –1 capa en vez de ~1274 PolyLines);
  sigue pendiente evaluar el peso en Cloud del primer render y regenerar
  `paradas_amba_osm.geojson` si se amplía el bbox.
- **Usos SUBE por hora (día vs noche)**: descartado por ahora. No existe dataset abierto
  por hora por línea; lo único horario es el estudio de "un día hábil promedio" por
  hexágono/modo (sin línea) y "Subte: viajes por molinete" de SBASE (solo subte). Si se
  quisiera un día, habría que estimar repartiendo el total diario con un perfil horario
  típico (con disclaimer) o limitarse a subte.

- **Mantenimiento molinetes (`app_subte.py`)**: al publicarse el ZIP de un año nuevo
  hay que descargarlo a `data/molinetes/` (o dejar que `_ingest_molinete_zip` lo baje
  de la CDN) y regenerar el agregado; la app muestra el año más cargado de base
  (por ahora 2025) y marca como "parcial" los años incompletos. El ZIP de 2026 es
  parcial (enero–junio).

- **Acceso desde barrios populares (`app_acceso.py`)**: la grilla `_grid_matches`
  ya cubre todo el AMBA en ~1 s; ideas a futuro: corredores hacia destinos clave
  (microcentro, intercambiadores, estaciones terminales), distancia a la estación
  más cercana por modo, y exportación por barrio (CSV con distancia mínima por red)
  para organizaciones sociales.

## Deploy

- Las apps viven en **Streamlit Community Cloud** (`https://share.streamlit.io`,
  repo `GuilleFerchero/transporte-caba`, rama `main`). Hay **tres entrypoints
  candidatos**: `app_transporte.py` (transporte público), `app_acceso.py`
  (acceso a la ciudad) y `app_subte.py` (subte por molinete), cada uno como una
  app separada del mismo repo.
  `requirements.txt` fija las versiones del entorno; el primer
  render de cada sesión descarga ~190 MB de datos (los CSVs de SUBE y GeoJSON) y
  el free tier suspende la app por inactividad (almacenamiento efímero).
- **Docker (alternativa a Cloud)**: ya hay `Dockerfile` (python:3.12-slim +
  `requirements.txt` + healthcheck + `CMD streamlit run app_transporte.py
  --server.address=0.0.0.0`) y `docker-compose.yml` que monta el volumen nombrado
  `transporte-data:/app/data` (los datos se descargan **una sola vez** y el arranque
  queda en segundos, sin límites de memoria ni suspensión por inactividad). Correr
  con `docker compose up -d --build` y apuntar a `http://localhost:8501`. Para cambio
  de app, editar el `CMD` del Dockerfile (entrypoints: `app_transporte.py` /
  `app_acceso.py`).