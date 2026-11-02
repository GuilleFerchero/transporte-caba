# Auditoría técnica — Panel de Transporte CABA

**Alcance:** `app_transporte.py`, `app_subte.py`, `app_acceso.py`,
`data_loaders.py`, `build_data_bundle.py`, `requirements.txt`, `Dockerfile`,
`docker-compose.yml`, `.gitignore` y residuos del working tree.

**Método:** lectura completa de los módulos, análisis AST de imports/funciones/
variables, `git ls-files`, inspección de bytes de `requirements.txt` y
verificación de referencias cruzadas. No se modificó ningún archivo existente:
este informe es el único archivo nuevo.

**Leyenda de riesgo** (riesgo de tocar el punto indicado, ponderado por el
impacto si se deja como está):

- **Bajo:** cambio localizado, sin efecto en runtime o solo cosmético.
- **Medio:** puede afectar una app, la frescura de los datos o el deploy.
- **Alto:** puede dejar una app sin datos o exponer claves/datos sensibles.

**Resumen priorizado (de menor a mayor riesgo):**

| # | Hallazgo | Riesgo |
|---|---|---|
| 1 | Logs, `__pycache__`, `backup/app.py`, `venv/` como residuos | Bajo |
| 2 | Código muerto e imports sin usar (11 puntos) | Bajo |
| 3 | Duplicación de helpers menores entre tableros | Bajo |
| 4 | `requirements.txt` con dependencias transitivas sobre-pinneadas | Bajo |
| 5 | `data_bundle/` y Docker: **no** son residuos (evidencia) | Bajo |
| 6 | `.gitignore` no cubre `.venv/` | Medio |
| 7 | `requirements.txt` codificado en UTF-16 LE con BOM | Medio |
| 8 | Constantes del bundle duplicadas entre loader y builder | Medio |
| 9 | Años, feriados y snapshot RE-NABAP hardcodeados | Medio |
| 10 | `data_loaders.py` monolítico (2.281 líneas, 104 funciones) | Medio |
| 11 | Descargas sin reintento y escritura no atómica | Medio |
| 12 | `except Exception: pass` y fallbacks silenciosos | Medio |
| 13 | Bundle obsoleto no detectable y `bundle_available()` incompleto | Medio |
| 14 | Colisión de etiquetas de barrios en `app_acceso.py` | Medio |
| 15 | Sin tests ni CI; sin `.dockerignore` | Medio |
| 16 | El guard de SUBE ignora `data_bundle/` (deja sin SUBE en Cloud) | **Alto** |
| 17 | `COPY . .` sin `.dockerignore` puede hornear `secrets.toml`/`data/` | **Alto** |

---

## 1. Archivos y carpetas que parecen no usarse o ser residuos

Ordenados de menor a mayor riesgo.

### 1.1 Logs sueltos en la raíz — riesgo Bajo

**Evidencia:** `acceso_err.log`, `acceso_out.log`, `acceso_stderr.log`,
`acceso_stdout.log`, `app_streamlit.log`, `app_streamlit_err.log`,
`opencode_streamlit_server.log`, `opencode_streamlit_server_err.log`,
`transporte_err.log`, `transporte_out.log`, `transporte_stderr.log`,
`transporte_stdout.log` (12 archivos, ~10 KB en total). Ningún `.py` los lee.
Están cubiertos por `.gitignore:6` (`*.log`), por lo que no están versionados
(`git ls-files '*.log'` no devuelve nada).

**Riesgo:** contienen rutas locales (`C:\Users\Guille\...`) y las IP LAN/pública
del equipo (`181.46.138.21`, `192.168.0.145`) en las líneas de "External URL".
No hay tokens ni claves.

**Propuesta:** borrarlos localmente y, si se quiere evitar que vuelvan a
aparecer, agregar `*.log` ya está cubierto; opcionalmente documentar que los
logs de ejecución van a `%TEMP%` o a una carpeta ignorada.

### 1.2 `__pycache__/` con bytecode de versiones y apps viejas — riesgo Bajo

**Evidencia:** `.gitignore:3-4` (`__pycache__/`, `*.pyc`), pero localmente hay
`.pyc` de Python 3.12 y 3.13 y un `app.cpython-313.pyc` que corresponde a
`backup/app.py` (mtime 13/9/2026). No están versionados.

**Propuesta:** borrar la carpeta; no requiere cambios de código.

### 1.3 `backup/app.py` — residuo versionado de 1.830 líneas — riesgo Bajo

**Evidencia:** `git ls-files` incluye `backup/app.py` (67.726 bytes, 1.830
líneas). Ningún módulo lo importa (`grep` de `backup` en `*.py` sin resultados).
Es una copia standalone del `app.py` histórico: redefine sus propias URLs,
loaders y `_THEME_CSS` (por ejemplo `backup/app.py:1197`, `1227`, `1648`), en
lugar de importar `data_loaders.py`. Ya divergió: conserva
`_is_caba_sube_row` y `_index_series` que hoy no se usan en el código vivo
(`backup/app.py:656`, `1214`), y mantiene el toggle AMBA/CABA y el benchmark
(`backup/app.py:1278`, `1325`).

**Propuesta:** sacarlo del repo (o moverlo a una rama/tag histórico). Mantenerlo
versionado duplica ~1.300 líneas de lógica y garantiza que se desincronice.

### 1.4 `venv/` — no es residuo, pero está mal cubierto — riesgo Bajo

**Evidencia:** `.gitignore:1` ignora solo `venv/`. El `AGENTS.md` global del
usuario indica usar `.venv`. Si en esta máquina se crea `.venv`, quedaría como
untracked y podría commitearse por error.

**Propuesta:** agregar `.venv/` a `.gitignore` (ver 6.9 por el impacto en Docker).

### 1.5 `data_bundle/` — **sí se usa**, no es residuo — riesgo Bajo (no tocar a ciegas)

**Evidencia de uso:**

- `data_loaders.py:105-112` define `bundle_available()` a partir de
  `data_bundle/bundle_meta.json`.
- `data_loaders.py:135-147` (`_read_parquet_bundle`) es la primera rama de
  `load_stops_df` (880), `load_routes_df` (889), `load_subte_lines` (972),
  `load_subte_stations` (981), `load_ffcc_lines` (990), `load_ffcc_stations`
  (999), `load_molinetes` (1223), `load_sube_transactions` (1387) y
  `load_sube_daily` (1403).
- `data_loaders.py:733-734` evita descargar fuentes crudas cuando hay bundle.
- `build_data_bundle.py:88-177` lo regenera y `requirements.txt:23` incluye
  `pyarrow`, necesario para leer parquet.
- `data_bundle/` está versionado (`git ls-files`) y pesa ~6,9 MB; es una
  decisión de deploy documentada en `AGENTS.md`.

**Propuesta:** no eliminarlo. Sí conviene revisar los riesgos 13 (frescura) y 8
(constantes duplicadas).

### 1.6 `Dockerfile` y `docker-compose.yml` — opcionales, no residuos — riesgo Bajo

**Evidencia:** no son importados por ninguna app; son un entrypoint alternativo
documentado en `AGENTS.md`. `Dockerfile:19` solo levanta `app_transporte.py` y
`docker-compose.yml:1-12` define un único servicio. No hay `.dockerignore`
(ver 6.2 y 6.14).

**Propuesta:** conservarlos, pero documentar que el `CMD` debe cambiarse a mano
para `app_acceso.py`/`app_subte.py` y agregar `.dockerignore`.

### 1.7 `data/` y `data/paradas_amba_osm.geojson` — caché local intencional — riesgo Bajo

**Evidencia:** `.gitignore:5` ignora `data/`; `data_loaders.py:48-78` define las
rutas y `ensure_local_data()` (730-780) descarga solo lo faltante. En el working
tree hay ~420 MB de fuentes y agregados (`dat-ab-usos-*.csv`, `molinetes_subte.csv`
de 48 MB, `paradas_amba_osm.geojson` de 4,5 MB, zips de molinetes de 206 MB).
No está versionado.

**Riesgo:** `paradas_amba_osm.geojson` se reutiliza para siempre si existe
(`load_osm_stops`, 1766-1779): no se refresca ni se valida contra el bbox actual
(ver 6.10).

**Propuesta:** no versionar; documentar el borrado manual cuando cambie el bbox.

### 1.8 `.streamlit/config.toml` y `AGENTS.md` — se usan — riesgo Bajo

`config.toml` define el tema que consumen las tres apps; `AGENTS.md` es
documentación operativa. No son residuos.

---

## 2. Código duplicado entre los tres tableros y funciones unificables

### 2.1 Bootstrap de página repetido (Bajo)

- `st.set_page_config(...)` + `st.markdown(THEME_CSS, unsafe_allow_html=True)`:
  `app_transporte.py:62-68`, `app_subte.py:55-61`, `app_acceso.py:52-58`.
- Cabecera: `app_transporte.py:74-86`, `app_subte.py:500-513`,
  `app_acceso.py:64-76` (el HTML ya está centralizado en `app_header_html`, pero
  el armado de chips se repite).

**Propuesta:** `init_page(title, icon, header...)` en `data_loaders.py` (o un
nuevo `ui_common.py`) que haga `set_page_config`, inyecte `THEME_CSS` y renderice
la cabecera.

### 2.2 `ensure_local_data()` repetido (Bajo)

`app_transporte.py:88-89` y `app_acceso.py:78-79` repiten el mismo `for message
in ensure_local_data(): st.caption(message)`. `app_subte.py` no lo llama a
propósito. Un helper `show_data_messages()` lo elimina.

### 2.3 Color por jurisdicción duplicado (Bajo)

`app_transporte.py:332-337` (`_todos_color`) y `app_acceso.py:118-123`
(`_bus_color`) son la misma función: librea para CABA/nacional, `JUR_COLOR` para
provincial/municipal, gris por defecto.

**Propuesta:** mover a `data_loaders.py` como `route_jurisdiction_color(row)` y
usarla en ambos.

### 2.4 Capa GeoJSON de recorridos duplicada (Bajo)

`app_transporte.py:339-352` y `app_acceso.py:300-319` construyen el mismo
`folium.GeoJson(routes_to_geojson(...))` con `style_function`, `GeoJsonTooltip`
y (en acceso) `GeoJsonPopup`. Solo cambian pesos/opacidades.

**Propuesta:** un `add_routes_layer(m, df, color_func, weight, opacity, popup=...)`
en el módulo de dibujo.

### 2.5 Overlay de subte/ferrocarril duplicado (Medio)

`app_transporte.py:443-467` y `app_acceso.py:321-352` repiten el mismo bloque:
cargar líneas/estaciones, iterar `draw_route`, `draw_subte_stations`,
`draw_ffcc_stations`. `app_acceso` agrega el recorte por `near_subte_idx` /
`near_ffcc_idx`; `app_transporte` agrega `popup` a subte.

**Riesgo:** unificar toca dos apps y las diferencias son sutiles (filtrado por
barrio y popups). Hacerlo con parámetros opcionales y verificar con AppTest.

### 2.6 Guard de disponibilidad de SUBE duplicado y **defectuoso** (Alto)

`app_transporte.py:97-100` y `app_acceso.py:388-391` deciden si hay SUBE con
`os.path.exists(SUBE_MONTHLY_FILE) or any(os.path.exists(p) for p in
SUBE_SOURCE_FILES)`. Esa condición **no contempla `data_bundle/`**: en un clon
limpio (Streamlit Cloud) `data/` no existe y `ensure_local_data()` retorna antes
de descargar (`data_loaders.py:733-734`), por lo que `load_sube_transactions()`
nunca se llama aunque `data_bundle/sube_mensual.parquet` esté presente.

**Impacto:** en Cloud desaparecen la vista de demanda, las pills y el ranking de
productividad de `app_transporte.py` (usos en 149 y 536) y el bloque de demanda
de `app_acceso.py` (387-425), sin error visible.

**Propuesta:** crear un `sube_available()` en `data_loaders.py` que devuelva
`True` si `bundle_available()` y existe `BUNDLE_SUBE_MENSUAL_FILE`, o si existen
los archivos crudos; usar ese helper en ambas apps. Es una corrección, no una
funcionalidad nueva.

### 2.7 Pills de variación duplicadas (Bajo)

`app_subte.py:191-195` (`_delta_span`) repite la lógica de
`data_loaders.py:2085-2094` (`_delta_pill_html`): signo, flecha, color y
formato. La diferencia es que una usa estilos inline y la otra clases CSS.

**Propuesta:** una sola función con un parámetro de estilo, o reutilizar
`_delta_pill_html` dentro del popup.

### 2.8 Cálculo de "últimos 12 meses" repetido (Bajo)

La misma ventana aparece en `app_transporte.py:235-239` y `551-553`,
`app_acceso.py:395` y `data_loaders.py:2038`. Un helper
`last_12_months(fechas)` evita que las definiciones se desalineen (por ejemplo,
si un día se cambia a 24 meses en un solo lugar).

### 2.9 Detección de picos por estación duplicada (Bajo)

`app_subte.py:582-585` (para el popup del mapa) y `app_subte.py:765-767` (para la
tabla de hora pico) recorren `per_file.groupby(["linea","estacion"])` y llaman a
`_peak_windows` con el mismo código.

**Propuesta:** calcular una vez un `DataFrame` de picos y reutilizarlo en ambos
lugares.

### 2.10 `_kpi` vs `_metric_box_html` (Bajo)

`app_subte.py:285-286` define un wrapper `_kpi` de una línea; las otras apps
llaman directo a `_metric_box_html` + `st.markdown`. Unificar el patrón (por
ejemplo, un `metric_box(...)` que ya haga el `st.markdown`) reduce ruido.

### 2.11 Constantes del bundle duplicadas (Medio)

`build_data_bundle.py:53-63` redefine `BUNDLE_ROUTES_FILE`, `BUNDLE_STOPS_FILE`,
`BUNDLE_SUBE_MENSUAL_FILE`, `BUNDLE_SUBE_DIARIO_FILE`, `BUNDLE_MOLINETES_FILE`,
`BUNDLE_SUBTE_LINES_FILE`, `BUNDLE_SUBTE_STATIONS_FILE`,
`BUNDLE_FFCC_LINES_FILE`, `BUNDLE_FFCC_STATIONS_FILE`, `BUNDLE_COMUNAS_FILE` y
`BUNDLE_RENABAP_FILE`, aunque `data_loaders.py:92-102` ya las exporta (el builder
solo importa `BUNDLE_DIR`, `BUNDLE_META_FILE` y `BUNDLE_SCHEMA_VERSION`).

**Riesgo:** si se renombra un archivo en un solo lado, el builder escribe un
nombre y los loaders leen otro; no falla fuerte, cae al flujo crudo y puede
disparar descargas enormes.

**Propuesta:** importar todas las constantes desde `data_loaders.py` y eliminar
las locales.

### 2.12 `SUBTECC_SOURCES` vs `AMBA_OVERLAY_SOURCES` (Bajo)

`build_data_bundle.py:67-72` repite las tuplas `(archivo, URL, descripción)` que
ya existen en `data_loaders.py:157-162` (`AMBA_OVERLAY_SOURCES`). Conviene
derivar una de la otra.

---

## 3. Funciones, imports y variables sin usar

Todo lo de esta sección es riesgo **Bajo**: son eliminaciones locales, sin
efecto en runtime.

### 3.1 Imports sin usar

| Archivo:línea | Elemento | Evidencia |
|---|---|---|
| `data_loaders.py:5` | `import io` | 0 usos en el módulo (AST + grep). |
| `app_transporte.py:7` | `GeoJsonPopup` | Solo aparece en el import; la app usa `folium.Popup` (417). |
| `app_subte.py:11-13` | `ACCENT_SOFT` | Solo aparece en el import; no se usa en el archivo. |

### 3.2 Funciones sin usar

| Archivo:línea | Función | Evidencia |
|---|---|---|
| `data_loaders.py:698-702` | `_index_series` | 0 referencias en el código vivo; solo sobrevive en `backup/app.py:1214`. |
| `data_loaders.py:1266-1273` | `_is_caba_sube_row` | 0 referencias; la misma regla está inline en `_read_sube_daily_all` (`data_loaders.py:1301-1304`). |
| `data_loaders.py:1672-1673` | `geo_route_style` | 0 referencias; el `style_function` se define inline en las apps (`app_transporte.py:341`, `app_acceso.py:302`). |

### 3.3 Constantes sin usar

| Archivo:línea | Constante | Evidencia |
|---|---|---|
| `data_loaders.py:32` | `OSM_STOPS_URL` | Se usa `OSM_STOPS_URLS` (28-31, 1733); esta es solo un alias no consumido. |
| `data_loaders.py:237` | `ACCENT_SOFT` | Única aparición además de la definición: el import muerto de `app_subte.py:13`. |
| `data_loaders.py:238` | `INK` | 0 usos; las apps usan `INK_DIM`/`INK_FAINT`. |
| `data_loaders.py:241-242` | `CARD_BG`, `CARD_BORDER` | 0 usos; el CSS usa los hex directamente. |
| `data_loaders.py:302` | `TEMA_MAPA_OPTS` | 0 usos; `tema_mapa_selector` usa `list(MAP_THEMES)` (1448). |
| `data_loaders.py:353-354` | `BENCH_NINGUNO`, `BENCH_AMBA` | 0 usos en el código vivo; solo en `backup/app.py`. |

### 3.4 Variables y parámetros sin usar

- `app_subte.py:369`: `ndays` se desempaqueta y nunca se usa. Además
  `_weekday_avg` está anotada `-> pd.DataFrame` (`app_subte.py:92`) pero devuelve
  una tupla `(per, ndays)` (`app_subte.py:101`, `105`). Corregir la anotación o
  dejar de devolver `ndays`.
- `app_subte.py:77`: `_clamp_end(mol, start, end, year)` no usa `start`.
- `app_subte.py:785`: `_barra(v)` no usa `v` (lo exige la firma de `Styler.map`;
  conviene renombrarlo a `_` o documentarlo).

No se detectaron variables locales asignadas y no leídas en las tres apps fuera
de estos casos.

---

## 4. Dependencias de `requirements.txt` que sobran o faltan

### 4.1 Codificación UTF-16 LE con BOM (Medio)

**Evidencia:** los primeros bytes del archivo son `FF FE`; el texto decodificado
como UTF-16LE es correcto (40 líneas, `altair==6.2.2` ... `xyzservices==2026.9.1`).
No es UTF-8.

**Riesgo:** `pip` acepta BOM UTF-16 (usa `auto_decode`), por lo que hoy instala;
pero herramientas de diff, linters, Dependabot/renovate y editores que asuman
UTF-8 pueden mostrarlo o parsearlo mal. Un re-guardado accidental como UTF-8 sin
BOM es inocuo; el problema es el estado actual.

**Propuesta:** volver a guardarlo como UTF-8 (sin BOM) y verificar en el commit
que el diff sea legible.

### 4.2 Dependencias directas: no falta ninguna (Bajo)

Las únicas librerías importadas por el código son:

| Paquete | Dónde se importa | Línea en requirements |
|---|---|---|
| `altair` | `app_transporte.py:4`, `app_subte.py:4` | 1 |
| `folium` | los tres tableros y `data_loaders.py:15` | 8 |
| `numpy` | los tres tableros y `data_loaders.py:11` | 18 |
| `pandas` | los tres tableros y `data_loaders.py:13` | 20 |
| `pyarrow` | implícito en `pd.read_parquet` (`data_loaders.py:141`) | 23 |
| `requests` | `data_loaders.py:12` | 28 |
| `streamlit` | los tres tableros y `data_loaders.py:14` | 31 |
| `streamlit-folium` | los tres tableros | 32 |

No hay imports de `scipy`, `geopandas`, `shapely`, `matplotlib` ni `plotly`.

### 4.3 Dependencias transitivas sobre-pinneadas (Bajo)

Las otras 32 entradas (`anyio`, `attrs`, `branca`, `certifi`,
`charset-normalizer`, `click`, `h11`, `httptools`, `idna`, `itsdangerous`,
`Jinja2`, `jsonschema`, `jsonschema-specifications`, `MarkupSafe`, `narwhals`,
`packaging`, `pillow`, `protobuf`, `pydeck`, `python-dateutil`,
`python-multipart`, `referencing`, `rpds-py`, `starlette`, `toml`,
`typing_extensions`, `tzdata`, `urllib3`, `uvicorn`, `watchdog`, `websockets`,
`xyzservices`) son dependencias de `streamlit`, `streamlit-folium`, `folium`,
`altair`, `pandas` o `requests` (verificado con `importlib.metadata` del venv).
No sobran desde el punto de vista de "no se usan", pero fijarlas a mano:

- impide resolver combinaciones compatibles al actualizar Streamlit/Folium;
- hace que un `pip install` futuro pueda fallar por conflictos que pip resolvería
  solo;
- oculta cuáles son las dependencias reales del proyecto.

**Propuesta:** dejar solo las 8 directas en `requirements.txt` y, si se quiere
reproducibilidad exacta, generar un `requirements.lock`/`pip freeze` aparte para
Docker/Cloud. `toml` es además un paquete en modo mantenimiento (Streamlit ya
migró a `tomllib` en versiones recientes), pero sigue siendo requerido por la
versión fijada.

### 4.4 Faltan dependencias de desarrollo (Medio)

No hay `pytest`, `ruff`/`flake8` ni `mypy` en requirements ni en un
`requirements-dev.txt`, y no hay carpeta `tests/` ni workflow de CI. La app se
valida a mano con `py_compile`/AppTest (ver `AGENTS.md`). Si se quiere sostener
la auditoría en el tiempo, conviene un archivo de desarrollo separado.

### 4.5 Python del Docker vs entorno local (Bajo)

`Dockerfile:1` usa `python:3.12-slim`; el venv local y los `.pyc` indican 3.13.2
(y también hay 3.12). Las versiones fijadas tienen wheels para ambas, pero el
desajuste complica reproducir un fallo de dependencias. Documentar la versión
soportada (por ejemplo en un `README`/`.python-version`) evita sorpresas.

---

## 5. Problemas de estructura

### 5.1 `data_loaders.py` es un módulo monolítico (Medio)

**Evidencia:** 84.113 bytes, 2.281 líneas, 104 funciones y 109 asignaciones de
nivel superior. Mezcla, en un solo archivo:

- URLs y constantes de fuentes (21-513);
- descargas y validación (708-780);
- construcción de tablas de paradas/recorridos (786-893);
- subte/ferrocarril (896-1003);
- ingesta de molinetes (1006-1255);
- normalización y agregados SUBE (1258-1415);
- colores de librea (1418-1440);
- tema de mapa, rampas y leyendas (1443-1561);
- dibujo Folium (1564-1707);
- OSM (1710-1779);
- RE-NABAP y grilla espacial (1782-2007);
- comunas (2010-2049);
- formateo y HTML (2052-2094);
- CSS completo de la app (2100-2281).

Además importa `streamlit` y `folium` en el tope (12-16), por lo que
`build_data_bundle.py` —un script de build— depende de la librería de UI y de
Folium solo para reutilizar builders.

**Propuesta (sin cambiar comportamiento):** dividir en módulos por
responsabilidad (`config/constantes`, `sources/descargas`, `transforms`,
`spatial`, `map_style`, `ui/format`) y dejar `data_loaders.py` como fachada que
re-exporte lo usado por las apps. Hacerlo en pasos, corriendo
`python -m py_compile` y AppTest después de cada paso. Es el cambio de mayor
esfuerzo del informe: conviene posponerlo hasta tener tests mínimos.

### 5.2 `app_subte.py` y `app_transporte.py` son grandes pero cohesivos (Bajo)

850 y 644 líneas respectivamente. `app_subte.py` concentra helpers de gráficos
(`_perfil_chart`, `_ranking_chart`, `_peak_*`, `_franja_banda`) que podrían vivir
en un `subte_charts.py`. No es urgente.

### 5.3 Constantes y años hardcodeados (Medio)

- `data_loaders.py:24-26`, `54-56`, `745-747`, `1276`: URLs y archivos SUBE
  2024/2025/2026 repetidos en cuatro bloques.
- `data_loaders.py:66-70`: `MOLINETES_FILES` fija 2024-2026.
- `app_subte.py:324`: `default_year = 2025` fijo; el año por defecto no sigue al
  año más reciente con datos completos.
- `data_loaders.py:190-206`: `FERIADOS_ARG` es un set estático 2024-2027; en
  2028 los feriados se contarán como hábiles (afecta `tipo_dia` y promedios).
- `data_loaders.py:27`: la URL de RE-NABAP apunta al snapshot
  `renabap-2023-12-06.geojson`.

**Propuesta:** centralizar la lista de años en una constante (por ejemplo
`SUBE_YEARS`, `MOLINETE_YEARS`) y derivar URLs/nombres de archivo; para
feriados, agregar una comprobación explícita de cobertura del año consultado
(advertir si falta) en lugar de asumir. No es funcionalidad nueva: es evitar
resultados incorrectos por datos desactualizados.

### 5.4 Rutas y parámetros escritos a mano (Medio)

- `build_data_bundle.py:8`: la ayuda usa `venv\\Scripts\\python`, exclusivo de
  Windows; no funciona en Linux/Docker.
- `app_subte.py:316`: mensaje con la ruta literal `data/molinetes/`.
- `data_loaders.py:34`: `OSM_AMBA_BBOX` hardcodeado; `_osm_stops_query`
  (538-544) lo interpola.
- `app_acceso.py:49-50`: `BARRIO_BUS_RADIUS_M` y `BARRIO_RAIL_RADIUS_M` viven en
  la app, mientras `RENABAP_RADIUS_M` vive en el loader; los tres umbrales
  espaciales están dispersos.
- `app_acceso.py:144-149`: las etiquetas de barrio se arman como
  `"barrio · partido"` y se usan como clave de diccionario; si dos barrios del
  mismo partido comparten nombre, una etiqueta pisa a la otra y el clic/selector
  puede resolver al `id` equivocado (ver 6.9).
- `app_transporte.py:114`: `sorted(..., key=int)` asume que todas las líneas son
  numéricas; si una fuente trae un valor vacío o alfanumérico, revienta el
  sidebar.
- `Dockerfile:19` y `docker-compose.yml:1-12`: entrypoint único y un solo
  servicio para tres apps.

**Propuesta:** mover los umbrales a constantes del loader (o un módulo
`config.py`), usar `Path` consistentemente, y hacer el orden de líneas tolerante
(`key=lambda s: (len(s), s)` o intentar `int` con fallback). Para Docker,
documentar/parametrizar el entrypoint sin cambiar el comportamiento por defecto.

### 5.5 `build_data_bundle.py` duplica el mapa de fuentes del loader (Medio)

Además de las constantes (2.11), `build_data_bundle.py:121-132` mantiene dos
diccionarios (`builders` y `targets`) con las mismas cuatro claves
(`subte_lineas`, `subte_estaciones`, `ffcc_lineas`, `ffcc_estaciones`) que ya
están en `SUBTECC_SOURCES` (67-72). Un solo diccionario con
`(archivo, url, builder, salida, descripción)` evita el desalineamiento.

### 5.6 Sin tests, sin CI y sin `.dockerignore` (Medio)

No hay `tests/`, `.github/workflows/`, `pytest.ini` ni `pyproject.toml`. La
verificación es manual (AppTest, `py_compile`). No hay `.dockerignore` (ver 6.2).

**Propuesta:** agregar un test smoke con AppTest para cada entrypoint y un
workflow que corra `py_compile` + AppTest. Es inversión de mantenimiento, no
funcionalidad.

---

## 6. Riesgos para datos o claves

Ordenados de menor a mayor riesgo.

### 6.1 Logs con IPs locales/públicas (Bajo)

**Evidencia:** `acceso_out.log`, `transporte_out.log`,
`opencode_streamlit_server.log`, etc. muestran `External URL:
http://181.46.138.21:8501`. No hay credenciales.

**Propuesta:** borrarlos y no compartir capturas de consola con esas URLs.

### 6.2 `COPY . .` sin `.dockerignore` puede hornear secretos y datos (Alto)

**Evidencia:** `Dockerfile:10` hace `COPY . .`; `Test-Path .dockerignore` es
`False` y `git ls-files` no lo incluye. El build context incluye, en una máquina
de desarrollo, `venv/` (cientos de MB), `data/` (~420 MB), `*.log`, `.git/`,
`__pycache__/` y —si existe— `.streamlit/secrets.toml` (ignorado por git en
`.gitignore:2`, pero **no** por Docker).

**Impacto:** imagen gigante y, si alguna vez se agrega una clave en
`secrets.toml` o un CSV con datos restringidos, queda dentro de la imagen
(distribuible/inspeccionable). Hoy no hay `secrets.toml` ni claves en el repo
(las APIs usadas son key-free), pero el riesgo latente es alto.

**Propuesta:** crear `.dockerignore` con al menos: `venv/`, `.venv/`, `data/`,
`*.log`, `__pycache__/`, `.git/`, `.streamlit/secrets.toml`, `backup/`. No
cambia el comportamiento de la app y reduce el contexto de build de cientos de
MB a ~7 MB.

### 6.3 Inyección de HTML desde datasets externos (Bajo)

**Evidencia:** valores de datasets se interpolan en HTML con
`unsafe_allow_html=True` o en popups/tooltips de Folium:

- `app_transporte.py:416-421` (dirección/barrio/comuna en popup);
- `app_subte.py:637-639` (nombre de estación en `DivIcon`);
- `app_acceso.py:362-368` (`barrio_sel` en caption HTML);
- `data_loaders.py:1597` (`name` OSM), `1612-1614` (subte), `1626-1630`
  (ferrocarril).

**Riesgo:** si una fuente abierta se corrompe o se reemplaza, un nombre con
HTML/JS podría ejecutarse en el navegador del usuario. Las fuentes actuales son
oficiales y de confianza, por eso el riesgo es bajo.

**Propuesta:** escapar con `html.escape()` los campos de texto antes de
interpolarlos (sin cambiar el diseño). No requiere tocar la lógica.

### 6.4 Estimaciones presentadas como datos (Bajo, documentado)

`app_acceso.py:178` y `217` usan `familias × 4` para personas;
`data_loaders.py:2022-2049` reparte la demanda SUBE por comuna en proporción al
número de paradas, y `app_transporte.py:641-643` lo aclara. No es un bug, pero
conviene mantener los disclaimers si se reutilizan los CSV exportados.

### 6.5 Descargas sin reintento/backoff (Medio)

**Evidencia:** `data_loaders.py:713` (`load_geojson`), `720`
(`_download_to_file`), `1081-1085` (`_download_molinete_zip`) y `1735-1740`
(Overpass) hacen un único `requests.get` con timeout. El OSM tiene fallback de
URL (28-31, 1733) pero no reintentos; los ZIP de molinetes son descargas de
~80 MB y un corte deja el proceso a medias (aunque usa `.part` y
`os.replace`, 1086-1090).

**Propuesta:** agregar 2-3 reintentos con backoff para errores 429/5xx, como ya
recomienda el `AGENTS.md` global. Es robustez, no funcionalidad nueva.

### 6.6 Escritura no atómica de fuentes descargadas (Medio)

**Evidencia:** `_download_to_file` (`data_loaders.py:718-727`) valida el
contenido en memoria pero escribe directo al path final (`open(path, "wb")`,
726-727). Si el proceso muere durante la escritura, queda un archivo parcial que
`os.path.exists` considerará válido en el próximo arranque. El flujo de
molinetes sí usa temporal + `os.replace` (1086-1090).

**Propuesta:** replicar el patrón `tmp` + `os.replace` en `_download_to_file`.

### 6.7 `except Exception: pass` y fallbacks silenciosos (Medio)

**Evidencia:**

- `data_loaders.py:146-147`: si falla la lectura de un parquet, devuelve `None`
  sin avisar y cae al flujo crudo.
- `data_loaders.py:1231-1233`: si falla la lectura del CSV agregado de molinetes,
  pasa a reconstruirlo (puede tardar minutos).
- `data_loaders.py:1396-1397`, `1410-1413`: ídem SUBE.
- `data_loaders.py:1791-1792`, `2016-2017`: si falla el `.gz` del bundle, cae al
  geojson crudo sin registrar la causa.
- `data_loaders.py:834-841` (`_load_amba_sources`): si falta un GeoJSON RMBA,
  simplemente no se agrega; `build_routes_table_amba` (845-874) devuelve solo
  CABA sin advertencia de que faltan líneas.

**Impacto:** un bundle corrupto o una fuente faltante puede producir un tablero
"válido" pero incompleto, sin que el usuario lo sepa.

**Propuesta:** registrar la excepción (`st.warning`/log) y, en
`_load_amba_sources`, devolver además cuántas fuentes se cargaron para que la
app muestre un caption de cobertura.

### 6.8 `bundle_available()` no verifica que los archivos existan (Medio)

**Evidencia:** `data_loaders.py:105-112` solo compara `schema_version` del
`bundle_meta.json`; no comprueba que estén los 11 archivos listados. Si falta
uno (por ejemplo, un `git lfs` mal clonado o un deploy parcial),
`_read_parquet_bundle` (135-147) devuelve `None` y el loader cae al flujo crudo:
en Cloud eso implica descargar desde cero (rutas ~12 MB; molinetes ~206 MB).

**Propuesta:** en `bundle_available()`, verificar también `os.path.exists` de
los archivos requeridos (o de los que use cada loader) y, si falta alguno,
reportarlo.

### 6.9 Colisión de etiquetas de barrio en `app_acceso.py` (Medio)

**Evidencia:** `app_acceso.py:144-149` arma `label = f"{barrio} · {partido}"` y
lo usa como clave de `barrio_labels`; `barrio_label_of_id` mapea el `id` a esa
etiqueta. Si dos barrios del mismo partido tienen el mismo `nombre_barrio`, la
segunda fila pisa la clave y `barrio_labels[label]` (253) puede devolver el `id`
equivocado. El clic (`159-161`) busca por etiqueta, así que también puede
seleccionar el barrio incorrecto.

**Propuesta:** incluir el `id_renabap` en la etiqueta visible o detectar
duplicados y desambiguar; es una corrección de datos, no una funcionalidad
nueva.

### 6.10 Caché OSM que nunca se refresca (Medio)

**Evidencia:** `load_osm_stops` (`data_loaders.py:1766-1779`) solo descarga si
`OSM_STOPS_FILE` no existe. Si se amplía `OSM_AMBA_BBOX` (`data_loaders.py:34`),
el archivo viejo se sigue usando indefinidamente y faltan paradas en la nueva
área; el propio `AGENTS.md` dice que hay que borrarlo a mano.

**Propuesta:** guardar junto al GeoJSON el bbox/`built_at` usado y re-descargar
si no coincide (mismo patrón que los sidecars de SUBE/molinetes).

### 6.11 Feriados estáticos (Medio)

**Evidencia:** `data_loaders.py:190-206` cubre 2024-2027. `_build_sube_aggregates`
(1364-1370) y `app_subte.py:98` clasifican feriados con ese set. En 2028 (o si se
corrige un feriado) los promedios de "día hábil" quedan mal sin aviso.

**Propuesta:** al construir agregados, verificar que el año de cada fecha esté
cubierto por `FERIADOS_ARG`; si no, advertir y/o generar el set desde la API
oficial en el build (no en runtime).

### 6.12 Bundle obsoleto no detectable (Medio)

**Evidencia:** `bundle_meta.json` tiene `schema_version` y `built_at`, pero no
los `mtime` de las fuentes. `_data_token` (`data_loaders.py:1873-1875`) devuelve
el token del bundle e ignora los `mtime` crudos, y `ensure_local_data` retorna
temprano (733-734). Si se actualizan los CSV/ZIP en `data/` sin regenerar el
bundle, las apps siguen mostrando el bundle viejo en silencio.

**Propuesta:** que `build_data_bundle.py` guarde en `bundle_meta.json` el
`mtime`/hash de cada fuente y que, en modo local, `bundle_available()` advierta
si alguna fuente es más nueva (sin cambiar el modo Cloud).

### 6.13 Años por defecto y orden de líneas (Medio/Bajo)

- `app_subte.py:324`: el año base por defecto es 2025; cuando 2026 esté
  completo, la app seguirá abriendo en 2025. Propuesta: elegir el año más
  reciente con datos completos.
- `app_transporte.py:114`: `key=int` puede lanzar `ValueError` si una línea no
  es numérica. Propuesta: orden tolerante.

### 6.14 Sin claves en el repo (correcto) pero con riesgo latente (Alto si se agregan)

**Evidencia:** no hay `.streamlit/secrets.toml` (verificado), no hay
`api_key`/`token`/`password` en el código. Las APIs usadas son key-free (Esri
canvas, OSM, BA Data). `.gitignore:2` ignora `secrets.toml`.

**Riesgo:** el único vector hoy es el `COPY . .` de Docker (6.2). Si en el
futuro se agrega una clave, el flujo correcto es
`st.secrets`/variable de entorno y `.dockerignore`; nunca un literal en el
código ni un archivo versionado.

---

## Verificación sugerida (sin cambiar funcionalidad)

```powershell
venv\Scripts\python -m py_compile data_loaders.py app_transporte.py app_acceso.py app_subte.py build_data_bundle.py
```

```python
from streamlit.testing.v1 import AppTest
for entry in ("app_transporte.py", "app_acceso.py", "app_subte.py"):
    at = AppTest.from_file(entry, default_timeout=300)
    at.run()
    print(entry, "exception:", at.exception)
```

Además, para reproducir el hallazgo 2.6 en un entorno tipo Cloud, alcanza con
mover temporalmente `data/` fuera del proyecto (dejando `data_bundle/`) y abrir
`app_transporte.py`: el selector "Vista de demanda" y el ranking no aparecen.
No se ejecutó esa prueba para no modificar el working tree.
