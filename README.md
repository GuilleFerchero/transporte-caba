# Transporte CABA · Tableros de transporte del AMBA

Tableros interactivos en **Streamlit + Folium** para explorar el transporte
público del Área Metropolitana de Buenos Aires con **datos abiertos** del
Gobierno de la Ciudad (BA Data) y de la Secretaría de Transporte de la Nación.

El repositorio reúne tres aplicaciones independientes que comparten un mismo
módulo de datos, tema visual y estilos:

| App | Entrypoint | Qué responde |
| --- | --- | --- |
| **Transporte público** | `app_transporte.py` | Recorridos y paradas de colectivo, demanda SUBE, subte y ferrocarril |
| **Acceso a la ciudad** | `app_acceso.py` | Cobertura de transporte y acceso al centro desde barrios populares (RE-NABAP) |
| **Subte por molinete** | `app_subte.py` | Entradas por estación, hora pico y evolución interanual (SBASE) |

## Capturas de funcionalidades

- **Recorridos AMBA**: 2.199 recorridos (1.104 de CABA + 1.095 del conurbano),
  coloreados por jurisdicción, con paradas, subte y ferrocarril como capas
  opcionales.
- **Demanda SUBE**: usos diarios y mensuales por línea, ranking de productividad
  (usos por km) y vistas por tipo de día y semana tipo.
- **Cobertura RE-NABAP**: barrios populares clasificados según su cercanía a la
  red y si alguna línea llega al centro (comunas 1 y 3).
- **Molinete SBASE**: entradas por estación, slider de franja horaria, hora pico
  automática y comparación interanual.

## Fuentes de datos

Todas las fuentes son abiertas. BA Data se publica bajo licencia
**CC-BY-2.5-AR**.

- **BA Data** — recorridos y paradas de colectivo, comunas y estaciones de
  ferrocarril.
- **Secretaría de Transporte (RMBA)** — recorridos nacionales, provinciales y
  municipales; líneas y estaciones de subte; líneas de ferrocarril.
- **SUBE** — cantidad de transacciones diarias por línea (`dat-ab-usos-*.csv`).
- **SBASE / BA Data** — viajes del subte por molinete en rangos de 15 minutos
  (`molinetes-<YYYY>.zip`).
- **RE-NABAP** — barrios populares filtrados al AMBA.
- **OpenStreetMap (Overpass)** — paradas del conurbano, descargadas de forma
  diferida (lazy).

> Las fuentes crudas viven en `data/` (no versionada). Los datos derivados se
> publican precomputados en `data_bundle/` (versionado, ~9 MB).

## Estructura del repositorio

```
app_transporte.py        # Tablero de transporte público (recorridos + SUBE)
app_acceso.py            # Tablero de acceso a la ciudad / cobertura RE-NABAP
app_subte.py             # Tablero de entradas por molinete (SBASE)
data_loaders.py          # Módulo compartido: URLs, carga, mapas, tema y formato
build_data_bundle.py     # Regenera data_bundle/ desde las fuentes crudas
check_bundle_parity.py   # Valida invariantes y paridad bundle ↔ datos crudos
data/                    # Fuentes crudas y agregados (local, no versionado)
data_bundle/             # Parquet zstd + geojson gzip precomputados (versionado)
docs/HISTORIAL_AGENTS.md # Contexto histórico, metodología y lecciones aprendidas
.streamlit/config.toml   # Tema oscuro
Dockerfile               # Imagen python:3.12-slim + Streamlit
docker-compose.yml       # Alternativa a Streamlit Cloud con volumen persistente
```

### Bundle precomputado

Streamlit Cloud clona el repositorio en cada arranque; descargar cientos de MB
de fuentes crudas por sesión era inviable. Por eso las apps son
**bundle-first**: leen `data_bundle/` y solo caen a las fuentes crudas si el
bundle no existe o su `schema_version` cambió.

Contenido principal del bundle:

- `routes.parquet` — 2.199 recorridos con geometrías, `longitud_m` y jurisdicción.
- `stops.parquet` — 11.461 paradas.
- `sube_mensual.parquet` / `sube_diario.parquet` — agregados de demanda.
- `molinetes.parquet` — entradas por hora y estación (~1,46 M filas).
- `subte_*.parquet`, `ffcc_*.parquet` — redes de subte y ferrocarril.
- `comunas.geojson.gz`, `renabap_amba.geojson.gz`.
- `bundle_meta.json` — `schema_version` y fecha de corte.

## Requisitos

- Python 3.12
- Entorno virtual en `venv/` (excepción a la convención global `.venv`)
- Dependencias fijadas en `requirements.txt`

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Cómo correr

```powershell
streamlit run app_transporte.py   # transporte público
streamlit run app_acceso.py       # acceso a la ciudad
streamlit run app_subte.py        # subte por molinete
```

No hace falta descargar datos para levantar las apps: el bundle ya está
commiteado. Si se quiere trabajar con las fuentes crudas, la app las descarga
sola en `data/` cuando faltan.

## Verificación

```powershell
# Sintaxis
python -m py_compile data_loaders.py app_transporte.py app_acceso.py app_subte.py build_data_bundle.py check_bundle_parity.py

# Paridad e invariantes del bundle (sale con código 1 si falla)
.\venv\Scripts\python check_bundle_parity.py
```

`check_bundle_parity.py` valida, entre otras cosas, la regla de identificación
de líneas SUBE, que `longitud_m` siga siendo `float`, que las geometrías se
lean como listas Python y que la cobertura RE-NABAP sea consistente. Sirve como
paso de CI.

También se puede probar una app sin navegador con `AppTest`:

```python
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("app_acceso.py", default_timeout=300)
at.run()
print(at.exception)  # debe estar vacío
```

## Regenerar el bundle

Cuando cambien las fuentes (por ejemplo, un año nuevo de SUBE o molinetes) o los
builders:

```powershell
.\venv\Scripts\python build_data_bundle.py
git add data_bundle/
```

Si cambian los builders hay que subir `BUNDLE_SCHEMA_VERSION` en
`data_loaders.py` y volver a correr `check_bundle_parity.py`.

## Docker

```powershell
docker compose up -d --build
```

La app queda disponible en `http://localhost:8501`. El volumen nombrado
`transporte-data` persiste `data/`, y con el bundle commiteado el arranque es
inmediato aunque el volumen esté vacío.

## Deploy

Las tres apps se publican como aplicaciones separadas en **Streamlit Community
Cloud** desde la rama `main` del repositorio
[`GuilleFerchero/transporte-caba`](https://github.com/GuilleFerchero/transporte-caba).
El free tier suspende las apps por inactividad; la alternativa Docker evita esa
suspensión.

## Notas metodológicas

- La **demanda SUBE** es siempre del AMBA completo; los filtros de jurisdicción
  aplican a recorridos y paradas, no a la demanda.
- El **choropleth por comuna** es una estimación: reparte los usos de cada línea
  entre sus paradas de CABA de forma proporcional, no es demanda medida por
  parada.
- La **cobertura RE-NABAP** mide la frontera de cada barrio contra el trazado de
  la red (no el centroide) y usa una grilla espacial de 100 m para hacerlo
  viable sobre todo el AMBA.
- Los recorridos del conurbano **no se deduplican por línea**: cada feature es
  una variante (línea × ramal × sentido) y deduplicar perdería la mayor parte de
  los kilómetros.
- La comparación interanual de molinetes **2025 vs 2024** no es estrictamente
  comparable por un cambio metodológico (desde dic-2024 se incluyen otros modos
  de pago).

## Créditos

Datos: Gobierno de la Ciudad de Buenos Aires (BA Data, CC-BY-2.5-AR), Secretaría
de Transporte de la Nación, SBASE y RE-NABAP. Mapas base: Esri y OpenStreetMap.
