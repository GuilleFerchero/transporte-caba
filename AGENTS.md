# Panel de Transporte CABA

Dashboard Streamlit + Folium con datos abiertos de BA Data y de la Secretaría de
Transporte para colectivos, subte y ferrocarril del AMBA, y acceso desde barrios
populares RE-NABAP.

## Correr y verificar
```powershell
streamlit run app_transporte.py   # recorridos, paradas, SUBE y overlays subte/ferro
streamlit run app_acceso.py       # cobertura RE-NABAP y líneas cercanas
streamlit run app_subte.py        # viajes por molinete (SBASE)
```
- Sintaxis: `python -m py_compile data_loaders.py app_*.py build_data_bundle.py check_bundle_parity.py`
- Verificación real: `venv\Scripts\python check_bundle_parity.py` (sale 1 si falla; sirve de CI).
- Sin navegador: `AppTest.from_file("app_acceso.py", default_timeout=300).run()`.
- Windows/PowerShell. El entorno virtual de este proyecto se llama `venv/` (excepción a la regla global de `.venv`), con Python 3.12; dependencias fijadas en `requirements.txt` (incluye `pyarrow`).

## Estructura
- `app_transporte.py`, `app_acceso.py`, `app_subte.py`: tres entrypoints independientes.
- `data_loaders.py`: módulo compartido (URLs, carga/transformación cacheada, mapas, tema, formato).
- `build_data_bundle.py`: regenera `data_bundle/`; `check_bundle_parity.py`: lo valida.
- `data/`: fuentes crudas y agregados, **no versionado** (`.gitignore`, uso local).
- `data_bundle/`: parquet zstd + geojson gzip, **versionado** (~9 MB).
- `docs/HISTORIAL_AGENTS.md`: contexto histórico, detalles y lecciones.
- `.streamlit/config.toml`: tema oscuro; `Dockerfile` + `docker-compose.yml`: alternativa a Cloud.

## Fuentes de datos
- BA Data (CC-BY-2.5-AR): `recorrido-colectivos.geojson` (1.104), `paradas-de-colectivo.geojson`, `comunas.geojson` (trae BOM: leer `utf-8-sig`).
- RMBA/Secretaría de Transporte: `rmba_{nacional,provincial,municipal}.geojson`, subte (`reddesubterraneo1`, `estacionesdesubte`) y FFCC (`ambalineas`); estaciones FFCC de BA Data.
- SUBE: `dat-ab-usos-{2024,2025,2026}.csv` (diario por línea; `AMBA=SI` + `COLECTIVO` + grafía AMBA).
- SBASE molinetes: `molinetes-<YYYY>.zip` de la CDN (2024-2026; 2026 parcial hasta junio).
- RE-NABAP (barrios populares filtrados a AMBA) y OSM (paradas del conurbano vía Overpass, lazy).

## Bundle (clave)
- Loaders **bundle-first**: si `data_bundle/bundle_meta.json` tiene `schema_version == BUNDLE_SCHEMA_VERSION` (hoy 2) y existen los 11 archivos, no se descargan fuentes crudas.
- Contiene `routes.parquet` (2.199 recorridos: 1.104 CABA + 1.095 RMBA), `stops.parquet` (11.461), `sube_mensual/diario.parquet`, `molinetes.parquet` (1.457.749 filas), subte/ffcc, `comunas.geojson.gz` y `renabap_amba.geojson.gz`.
- Regenerar cuando cambien fuentes o builders: `venv\Scripts\python build_data_bundle.py` (requiere `data/` crudo) → `git add data_bundle/` → commit.
- Si cambia un builder, subir `BUNDLE_SCHEMA_VERSION` en `data_loaders.py` y correr `check_bundle_parity.py`; los parquet con schema viejo se ignoran.

## Decisiones técnicas vigentes
- Dedupe RMBA **solo por número de línea y contra BA Data**; nunca entre features RMBA (cada uno es una variante; deduplicar pierde ~95% de km).
- SUBE se identifica **solo por grafía** (`SUBE_LINEA_RE` / `_is_amba_sube_code`), no por jurisdicción/provincia: acepta CABA/BSAS/BS_AS/LINEA..., rechaza `RZ` y códigos pelados.
- Caché `@st.cache_data` con tokens de mtime (`_data_token`, `_sube_source_token`, `_molinetes_source_token`); nunca pasar DataFrames con listas.
- Cobertura RE-NABAP con grilla de 100 m (`build_point_grid`/`_grid_matches`) contra vértices de frontera, no centroides; `stops_near_route` solo para OSM.
- `longitud_m` debe seguir `float`; `_read_parquet_bundle` convierte geometrías a listas Python (`_deep_python`).
- Feriados: `FERIADOS_ARG` estático 2024-2027; actualizarlo al publicarse un año nuevo.
- Mapas: Esri dark/light + OSM.de (CARTO/OSM.org se cuelgan); `st_folium(..., returned_objects=[])` salvo en `app_acceso` (clic de barrio).
- Las apps deciden si hay SUBE con `sube_available()` (contempla `data_bundle/`), nunca con `os.path.exists` sobre `data/`. `bundle_available()` exige `schema_version` y que existan todos los archivos del bundle.

## Trampas conocidas
- No modificar `data/` ni inventar datos; validar columnas, tipos, nulos y duplicados.
- Se descartan `COMUNA=76` y valores `L*` no numéricos.
- No cortar el barrido de `_grid_matches` al primer hit (perdía 65% de líneas cercanas a 500 m).
- Estaciones de molinetes: normalizar con `MOLINETES_STATION_ALIAS` + `_canon_molinete_station`; cruzar por (estación, línea).
- Los iconos Material de Streamlit se ven como texto; workaround CSS en `THEME_CSS`.
- OSM/SUBE/RE-NABAP degradan con warning; paradas/recorridos/comunas son core.
- No hacer commit ni push sin que el usuario lo pida. Cada push a `main` reinicia las tres apps en Cloud.
- `check_bundle_parity.py` (sección A2 y paridad de SUBE) compara contra `data/`, no contra el bundle: si `data/` es más vieja que `built_at` de `bundle_meta.json`, da falsos fallos. No regenerar el bundle desde un `data/` desactualizado; borrar antes los agregados SUBE locales.

## Deploy en Streamlit Cloud
- Repo `GuilleFerchero/transporte-caba`, rama `main`, tres apps separadas en `share.streamlit.io`.
- `data_bundle/` commiteado: el primer render no descarga crudos; el free tier duerme por inactividad.
- `requirements.txt` debe incluir `pyarrow`; Docker (`docker compose up -d --build`) evita suspensión y persiste `data/` en el volumen `transporte-data`.
- Python 3.12 (Advanced settings). En Cloud no existe `data/`: todo sale de `data_bundle/`.
