import gzip
import os
import re
import io
import json
import zipfile
import unicodedata
from collections import defaultdict
from datetime import datetime
import numpy as np
import requests
import pandas as pd
import streamlit as st
import folium
from folium.features import GeoJsonTooltip, GeoJsonPopup

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
STOPS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos-paradas/paradas-de-colectivo.geojson"
ROUTES_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos-recorridos/recorrido-colectivos.geojson"
COMUNAS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/innovacion-transformacion-digital/comunas/comunas.geojson"
SUBE_USOS_2024_URL = "https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2024.csv"
SUBE_USOS_2025_URL = "https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2025.csv"
SUBE_USOS_2026_URL = "https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2026.csv"
RENABAP_AMBA_URL = "https://www.argentina.gob.ar/sites/default/files/renabap-2023-12-06.geojson"
OSM_STOPS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
OSM_STOPS_URL = OSM_STOPS_URLS[0]
OSM_STOPS_USER_AGENT = "panel-transporte-caba/1.0 (dashboard Streamlit de colectivos AMBA)"
OSM_AMBA_BBOX = "(-35.20,-59.45,-34.00,-57.85)"

RMBA_BASE_URL = "https://datos.transporte.gob.ar/dataset/f87b93d4-ade2-44fc-a409-d3736ba9f3ba/resource"
RMBA_NACIONAL_URL = f"{RMBA_BASE_URL}/84947471-9c1e-4a23-8a2e-03a8c87c056f/download/lineasbusrmbajurisdiccionnacional.geojson"
RMBA_PROVINCIAL_URL = f"{RMBA_BASE_URL}/f95e25bc-a6b2-4a78-a04b-35fa437be96b/download/lineasbusrmbajurisdiccionprovincial.geojson"
RMBA_MUNICIPAL_URL = f"{RMBA_BASE_URL}/f0f3791a-addc-4143-bb95-ef0e8bca5bd8/download/lineasbusrmbajurisdiccionmunicipal.geojson"
SUBTE_LINEAS_URL = f"{RMBA_BASE_URL}/9341189e-6f06-43d7-a5ed-a34f3435fbcc/download/reddesubterraneo1.geojson"
SUBTE_ESTACIONES_URL = f"{RMBA_BASE_URL}/79f1bdc7-857e-4295-b19a-bfdd074384e0/download/estacionesdesubte.geojson"
FFCC_LINEAS_URL = f"{RMBA_BASE_URL}/367a26af-c5b4-4361-b614-abd6ad743383/download/ambalineas.geojson"
FFCC_ESTACIONES_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/estaciones-ferrocarril/estaciones-de-ferrocarril.geojson"

# ---------------------------------------------------------------------------
# Rutas de archivos locales
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STOPS_FILE = os.path.join(DATA_DIR, "paradas-de-colectivo.geojson")
ROUTES_FILE = os.path.join(DATA_DIR, "recorrido-colectivos.geojson")
COMUNAS_FILE = os.path.join(DATA_DIR, "comunas.geojson")
RENABAP_AMBA_FILE = os.path.join(DATA_DIR, "renabap_amba.geojson")
OSM_STOPS_FILE = os.path.join(DATA_DIR, "paradas_amba_osm.geojson")
SUBE_USOS_2024_FILE = os.path.join(DATA_DIR, "dat-ab-usos-2024.csv")
SUBE_USOS_2025_FILE = os.path.join(DATA_DIR, "dat-ab-usos-2025.csv")
SUBE_USOS_2026_FILE = os.path.join(DATA_DIR, "dat-ab-usos-2026.csv")
RMBA_NACIONAL_FILE = os.path.join(DATA_DIR, "rmba_nacional.geojson")
RMBA_PROVINCIAL_FILE = os.path.join(DATA_DIR, "rmba_provincial.geojson")
RMBA_MUNICIPAL_FILE = os.path.join(DATA_DIR, "rmba_municipal.geojson")
SUBTE_LINEAS_FILE = os.path.join(DATA_DIR, "subte_lineas.geojson")
SUBTE_ESTACIONES_FILE = os.path.join(DATA_DIR, "subte_estaciones.geojson")
FFCC_LINEAS_FILE = os.path.join(DATA_DIR, "ffcc_lineas.geojson")
FFCC_ESTACIONES_FILE = os.path.join(DATA_DIR, "ffcc_estaciones.geojson")

MOLINETES_CDN = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/sbase/subte-viajes-molinetes"
MOLINETES_FILES = {
    2024: "molinetes-2024.zip",
    2025: "molinetes-2025.zip",
    2026: "molinetes-2026.zip",
}
MOLINETES_DIR = os.path.join(DATA_DIR, "molinetes")
MOLINETES_AGG_FILE = os.path.join(DATA_DIR, "molinetes_subte.csv")
MOLINETES_AGG_META_FILE = os.path.join(DATA_DIR, "molinetes_agg_meta.json")
MOLINETES_AGG_SCHEMA_VERSION = 2

SUBE_MONTHLY_FILE = os.path.join(DATA_DIR, "sube_usos_mensuales.csv")
SUBE_DAILY_FILE = os.path.join(DATA_DIR, "sube_usos_diarios.csv")
SUBE_AGG_META_FILE = os.path.join(DATA_DIR, "sube_agregados_meta.json")

ROUTES_SOURCE_FILES = [ROUTES_FILE, RMBA_NACIONAL_FILE, RMBA_PROVINCIAL_FILE, RMBA_MUNICIPAL_FILE]

# ---------------------------------------------------------------------------
# Bundle precomputado (data_bundle/) - datos derivados para deploy liviano
# ---------------------------------------------------------------------------
# Generado con build_data_bundle.py y commiteado al repo: Streamlit Cloud clona
# el repo, asi las apps arrancan SIN descargar las ~420 MB de fuentes crudas.
# Si data_bundle/ no existe o el schema no coincide, se usa el flujo clasico.
BUNDLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_bundle")
BUNDLE_META_FILE = os.path.join(BUNDLE_DIR, "bundle_meta.json")
BUNDLE_SCHEMA_VERSION = 1

BUNDLE_ROUTES_FILE = os.path.join(BUNDLE_DIR, "routes.parquet")
BUNDLE_STOPS_FILE = os.path.join(BUNDLE_DIR, "stops.parquet")
BUNDLE_SUBE_MENSUAL_FILE = os.path.join(BUNDLE_DIR, "sube_mensual.parquet")
BUNDLE_SUBE_DIARIO_FILE = os.path.join(BUNDLE_DIR, "sube_diario.parquet")
BUNDLE_MOLINETES_FILE = os.path.join(BUNDLE_DIR, "molinetes.parquet")
BUNDLE_SUBTE_LINES_FILE = os.path.join(BUNDLE_DIR, "subte_lines.parquet")
BUNDLE_SUBTE_STATIONS_FILE = os.path.join(BUNDLE_DIR, "subte_stations.parquet")
BUNDLE_FFCC_LINES_FILE = os.path.join(BUNDLE_DIR, "ffcc_lines.parquet")
BUNDLE_FFCC_STATIONS_FILE = os.path.join(BUNDLE_DIR, "ffcc_stations.parquet")
BUNDLE_COMUNAS_FILE = os.path.join(BUNDLE_DIR, "comunas.geojson.gz")
BUNDLE_RENABAP_FILE = os.path.join(BUNDLE_DIR, "renabap_amba.geojson.gz")


def bundle_available() -> bool:
    """True si hay un bundle precomputado valido (evita descargar fuentes crudas)."""
    try:
        with open(BUNDLE_META_FILE, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return False
    return meta.get("schema_version") == BUNDLE_SCHEMA_VERSION


def _bundle_token() -> str:
    if not bundle_available():
        return ""
    try:
        return f"bundle:{os.path.getmtime(BUNDLE_META_FILE):.0f}"
    except OSError:
        return ""


def _deep_python(v):
    """Convierte recursivamente ndarrays/valores numpy a tipos Python planos."""
    if isinstance(v, list):
        return [_deep_python(x) for x in v]
    if isinstance(v, np.ndarray):
        return _deep_python(v.tolist())
    if isinstance(v, np.generic):
        return v.item()
    return v


def _read_parquet_bundle(path) -> pd.DataFrame | None:
    """Lee un parquet del bundle si esta disponible; las columnas de geometria
    vuelven a listas planas de Python (pyarrow las devuelve como ndarray)."""
    if not bundle_available():
        return None
    try:
        df = pd.read_parquet(path)
        for col in ("coords", "coords_simple"):
            if col in df.columns:
                df[col] = df[col].map(_deep_python)
        return df
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Fuentes de datos
# ---------------------------------------------------------------------------
AMBA_BUS_SOURCES = [
    (RMBA_NACIONAL_FILE, RMBA_NACIONAL_URL, "recorridos RMBA nacionales", "NACIONAL"),
    (RMBA_PROVINCIAL_FILE, RMBA_PROVINCIAL_URL, "recorridos RMBA provinciales", "PROVINCIAL"),
    (RMBA_MUNICIPAL_FILE, RMBA_MUNICIPAL_URL, "recorridos RMBA municipales", "MUNICIPAL"),
]
AMBA_OVERLAY_SOURCES = [
    (SUBTE_LINEAS_FILE, SUBTE_LINEAS_URL, "líneas de subte"),
    (SUBTE_ESTACIONES_FILE, SUBTE_ESTACIONES_URL, "estaciones de subte"),
    (FFCC_LINEAS_FILE, FFCC_LINEAS_URL, "líneas de ferrocarril"),
    (FFCC_ESTACIONES_FILE, FFCC_ESTACIONES_URL, "estaciones de ferrocarril"),
]
AMBA_BUS_BOUNDS = [[-35.1876, -59.4382], [-34.0418, -57.9211]]

DATA_SOURCES = [
    (STOPS_FILE, STOPS_URL),
    (ROUTES_FILE, ROUTES_URL),
    (COMUNAS_FILE, COMUNAS_URL),
]

# ---------------------------------------------------------------------------
# Constantes RE-NABAP
# ---------------------------------------------------------------------------
RENABAP_AMBA_DEPTS = {
    "almirante brown", "avellaneda", "berazategui", "berisso",
    "esteban echeverria", "ezeiza", "florencio varela",
    "general san martin", "hurlingham", "ituzaingo", "jose c. paz",
    "la matanza", "lanus", "lomas de zamora", "malvinas argentinas",
    "merlo", "moreno", "moron", "quilmes", "san fernando",
    "san isidro", "tres de febrero", "vicente lopez",
    "la plata", "ensenada", "jose m. ezeiza",
}

RENABAP_COLOR = "#d62728"
RENABAP_RADIUS_M = 300

# Feriados nacionales argentinos (inamovibles, trasladables y puentes), fuente
# oficial DDJJ (https://api.argentinadatos.com/v1/feriados/). Se actualizan a mano
# cuando el calendario del año siguiente se publica.
FERIADOS_ARG = {
    "2024-01-01", "2024-02-12", "2024-02-13", "2024-03-24", "2024-03-29", "2024-04-01",
    "2024-04-02", "2024-05-01", "2024-05-25", "2024-06-17", "2024-06-20", "2024-06-21",
    "2024-07-09", "2024-08-17", "2024-10-11", "2024-10-12", "2024-11-18", "2024-12-08",
    "2024-12-25",
    "2025-01-01", "2025-03-03", "2025-03-04", "2025-03-24", "2025-04-02", "2025-04-18",
    "2025-05-01", "2025-05-02", "2025-05-25", "2025-06-16", "2025-06-20", "2025-07-09",
    "2025-08-15", "2025-08-17", "2025-10-10", "2025-10-12", "2025-11-21", "2025-11-24",
    "2025-12-08", "2025-12-25",
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-03-23", "2026-03-24", "2026-04-02",
    "2026-04-03", "2026-05-01", "2026-05-25", "2026-06-15", "2026-06-20", "2026-07-09",
    "2026-07-10", "2026-08-17", "2026-10-12", "2026-11-23", "2026-12-07", "2026-12-08",
    "2026-12-25",
    "2027-01-01", "2027-02-08", "2027-02-09", "2027-03-24", "2027-03-26", "2027-04-02",
    "2027-05-01", "2027-05-25", "2027-06-17", "2027-06-20", "2027-07-09", "2027-08-17",
    "2027-10-12", "2027-11-20", "2027-12-08", "2027-12-25",
}

# ---------------------------------------------------------------------------
# Constantes de mapa / estilos
# ---------------------------------------------------------------------------
SUBTE_COLOR = "#7b2fbf"
FFCC_COLOR = "#1f77b4"
JUR_COLOR = {"PROVINCIAL": "#2e9e4b", "MUNICIPAL": "#f2a30f", "NACIONAL": "#1f77b4"}

SUBTE_LINE_COLORS = {
    "A": "#00b3e6",
    "B": "#e2001a",
    "C": "#004b97",
    "D": "#009a44",
    "E": "#60247e",
    "H": "#ffd100",
}

CABA_BOX = {
    "lat_min": -34.705, "lat_max": -34.520,
    "lon_min": -58.533, "lon_max": -58.340,
}

OSM_STOP_RADIUS_M = 150
ALL_LINES_SIMPLE_STEP_M = 30.0
CHOROPLETH_BINS = 5

SEL_LINEA = "— Seleccioná una línea —"
VISTA_MENSUAL = "Mensual"
VISTA_DIA = "Tipo de día (hábiles vs. finde)"
VISTA_SEMANA = "Semana tipo (Lunes a Domingo)"
BENCH_NINGUNO = "Sin comparación"
BENCH_AMBA = "Total AMBA"

BASE_COLORS = {
    "azul": "#1a73e8",
    "rojo": "#d62728",
    "verde": "#2e9e4b",
    "amarillo": "#f2c200",
    "blanco": "#f5f5f5",
    "marron": "#8b5a2b",
    "violeta": "#7b2fbf",
    "gris": "#9e9e9e",
    "negro": "#212121",
}

LINE_COLORS = {
    "001": "azul y amarillo",
    "002": "rojo",
    "004": "blanco",
    "006": "blanco y verde",
    "007": "azul",
    "008": "azul",
    "009": "blanco y azul",
    "010": "verde",
    "012": "rojo y negro",
    "015": "verde",
    "017": "verde",
    "019": "rojo",
    "020": "blanco y rojo",
    "021": "azul",
    "022": "verde",
    "023": "blanco y verde",
    "024": "verde y rojo",
    "025": "azul",
    "026": "blanco y rojo",
    "028": "verde y blanco",
    "029": "azul",
    "031": "rojo",
    "032": "rojo",
    "033": "verde",
    "034": "azul",
    "037": "verde",
    "039": "marrón",
    "041": "amarillo",
    "042": "blanco y rojo",
    "044": "azul",
    "045": "verde",
    "046": "azul",
    "047": "rojo",
    "049": "rojo",
    "050": "blanco",
    "051": "azul",
    "053": "azul",
    "055": "rojo",
    "056": "verde",
    "057": "blanco",
    "059": "verde",
    "060": "amarillo",
    "061": "rojo",
    "062": "rojo",
    "063": "azul",
    "064": "azul",
    "065": "blanco y verde",
    "067": "rojo",
    "068": "azul",
    "070": "verde",
    "071": "blanco y azul",
    "074": "azul",
    "075": "rojo",
    "076": "verde",
    "078": "amarillo",
    "079": "azul",
    "080": "rojo",
    "084": "azul",
    "085": "verde",
    "086": "azul",
    "087": "amarillo",
    "088": "rojo",
    "090": "amarillo",
    "091": "verde",
    "092": "verde",
    "093": "amarillo",
    "095": "verde",
    "096": "blanco y rojo",
    "097": "azul",
    "098": "amarillo",
    "099": "blanco",
    "100": "rojo",
    "101": "verde",
    "102": "rojo y azul",
    "103": "rojo",
    "105": "blanco y azul",
    "106": "blanco",
    "107": "blanco",
    "108": "blanco",
    "109": "rojo",
    "110": "rojo y azul",
    "111": "amarillo",
    "113": "azul",
    "114": "rojo",
    "115": "rojo",
    "117": "blanco y rojo",
    "118": "azul",
    "119": "verde",
    "123": "azul y amarillo",
    "124": "rojo",
    "126": "rojo",
    "127": "amarillo",
    "128": "rojo",
    "129": "blanco",
    "130": "amarillo",
    "132": "blanco y azul",
    "133": "rojo",
    "134": "rojo",
    "135": "verde",
    "136": "blanco",
    "140": "rojo",
    "143": "rojo",
    "145": "violeta",
    "146": "blanco y azul",
    "148": "amarillo",
    "150": "rojo",
    "151": "azul",
    "152": "azul",
    "153": "rojo",
    "154": "verde",
    "158": "rojo",
    "159": "verde",
    "160": "rojo",
    "161": "rojo",
    "163": "blanco",
    "164": "azul",
    "166": "rojo",
    "168": "rojo",
    "169": "azul",
    "172": "amarillo",
    "174": "azul",
    "176": "blanco",
    "177": "azul",
    "178": "rojo",
    "179": "verde",
    "180": "rojo",
    "181": "rojo",
    "182": "blanco",
    "184": "gris",
    "185": "blanco",
    "188": "rojo",
    "193": "azul",
    "194": "azul",
    "195": "blanco",
}

# ---------------------------------------------------------------------------
# Utilitarias de colores / subte
# ---------------------------------------------------------------------------
def _subte_line_letter(linea) -> str:
    s = str(linea or "")
    letters = [w for w in s.split() if w.isalpha()]
    return letters[-1].upper() if letters else s.strip().upper()


def _subte_line_color(linea) -> str:
    return SUBTE_LINE_COLORS.get(_subte_line_letter(linea), SUBTE_COLOR)


# ---------------------------------------------------------------------------
# Utilitarias generales
# ---------------------------------------------------------------------------
def _normalize(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower().strip()


def _filter_renabap_amba(national_fc: dict) -> dict:
    features = []
    for feat in national_fc["features"]:
        prov = feat["properties"]["provincia"]
        if "Ciudad" in prov:
            features.append(feat)
        elif prov == "Buenos Aires":
            dept = _normalize(feat["properties"]["departamento"])
            if dept in RENABAP_AMBA_DEPTS:
                features.append(feat)
    return {"type": "FeatureCollection", "features": features}


def _osm_stops_query() -> str:
    return (
        "[out:json][timeout:300];"
        "(node[\"highway\"=\"bus_stop\"]{b};"
        "node[\"public_transport\"=\"platform\"][\"bus\"=\"yes\"]{b};);"
        "out body;"
    ).format(b=OSM_AMBA_BBOX)


# ---------------------------------------------------------------------------
# Funciones de geometria / matematica
# ---------------------------------------------------------------------------
def _haversine_np(lat1, lon1, lat2, lon2):
    r_earth = 6_371_000.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return r_earth * 2 * np.arcsin(np.sqrt(a))


def _route_length_m(coords) -> float:
    total = 0.0
    for segment in coords:
        for i in range(1, len(segment)):
            lon1, lat1 = segment[i - 1]
            lon2, lat2 = segment[i]
            total += _haversine_np(lat1, lon1, lat2, lon2)
    return float(total)


def _dx_dy_m(lat1, lon1, lat2, lon2):
    lat_m = 111_320.0
    lon_m = lat_m * np.cos(np.radians((float(lat1) + float(lat2)) / 2.0))
    dx = (float(lon2) - float(lon1)) * lon_m
    dy = (float(lat2) - float(lat1)) * lat_m
    return dx, dy


def _simplify_route_coords(coords, min_step_m=ALL_LINES_SIMPLE_STEP_M):
    simplified = []
    for segment in coords:
        if not segment:
            continue
        pts = [(float(c[1]), float(c[0])) for c in segment]
        out = [pts[0]]
        last = pts[0]
        for p in pts[1:]:
            dx, dy = _dx_dy_m(last[0], last[1], p[0], p[1])
            if np.hypot(dx, dy) >= min_step_m:
                out.append(p)
                last = p
        if out[-1] != pts[-1]:
            out.append(pts[-1])
        simplified.append([(lon, lat) for lat, lon in out])
    return simplified


def _clean_route_coords(geom) -> list:
    if not geom or not geom.get("coordinates"):
        return []
    coords = geom["coordinates"]
    segments = coords if geom["type"] == "MultiLineString" else [coords]
    out = []
    for seg in segments:
        pts = [(float(c[0]), float(c[1])) for c in seg if len(c) >= 2]
        if pts:
            out.append(pts)
    return out


def _norm_sentido(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "IDA"
    s = str(v).strip().lower()
    if s in ("0", "ida"):
        return "IDA"
    if s in ("1", "vuelta"):
        return "VUELTA"
    return "IDA"


def _norm_rmba_linea(v) -> str | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    m = re.search(r"(\d+)", str(v))
    if not m:
        return None
    n = int(m.group(1))
    return f"{n:03d}" if n > 0 else None


def _clean_label(v) -> str | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def point_in_polygon(lat: float, lon: float, geom) -> bool:
    """Test de punto en polígono (ray casting) para geometrías Polygon y MultiPolygon."""
    if not geom:
        return False
    gtype = geom.get("type")
    if gtype == "Polygon":
        polygons = [geom["coordinates"]]
    elif gtype == "MultiPolygon":
        polygons = geom["coordinates"]
    else:
        return False
    x, y = float(lon), float(lat)
    inside = False
    for polygon in polygons:
        for ring in polygon:
            n = len(ring)
            if n < 3:
                continue
            j = n - 1
            for i in range(n):
                xi, yi = float(ring[i][0]), float(ring[i][1])
                xj, yj = float(ring[j][0]), float(ring[j][1])
                if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                    inside = not inside
                j = i
    return inside


def stops_near_route(stops_df: pd.DataFrame, lats, lons, radius_m=OSM_STOP_RADIUS_M) -> pd.DataFrame:
    if stops_df.empty or not lats:
        return stops_df.iloc[0:0]
    lat_arr = np.asarray(lats, dtype=float)
    lon_arr = np.asarray(lons, dtype=float)
    pad = 0.012
    cand = stops_df[
        (stops_df["lat"] >= lat_arr.min() - pad)
        & (stops_df["lat"] <= lat_arr.max() + pad)
        & (stops_df["lon"] >= lon_arr.min() - pad)
        & (stops_df["lon"] <= lon_arr.max() + pad)
    ]
    if cand.empty:
        return cand
    stop_lat = cand["lat"].to_numpy()
    stop_lon = cand["lon"].to_numpy()
    keep = np.zeros(len(cand), dtype=bool)
    for i in range(0, len(cand), 250):
        s_lat = stop_lat[i : i + 250, None]
        s_lon = stop_lon[i : i + 250, None]
        best = np.full(s_lat.shape[0], np.inf)
        for a in range(0, len(lat_arr), 5000):
            d = _haversine_np(
                s_lat, s_lon,
                lat_arr[None, a : a + 5000],
                lon_arr[None, a : a + 5000],
            )
            best = np.minimum(best, d.min(axis=1))
        keep[i : i + 250] = best <= radius_m
    return cand[keep].reset_index(drop=True)


def _index_series(serie: pd.DataFrame) -> pd.DataFrame:
    out = serie.copy()
    base = out["transacciones"].iloc[0]
    out["idx"] = 100.0 * out["transacciones"] / base if base else 0.0
    return out


# ---------------------------------------------------------------------------
# Carga de archivos GeoJSON
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_geojson(path: str, url: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _download_to_file(path: str, url: str, timeout: int, kind: str = "bin") -> None:
    """Descarga a disco solo después de validar el contenido (evita archivos parciales)."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    if kind == "json":
        json.loads(resp.content.decode("utf-8-sig"))
    elif kind == "csv" and not resp.content.strip():
        raise ValueError("archivo CSV vacío")
    with open(path, "wb") as f:
        f.write(resp.content)


@st.cache_data(show_spinner=False)
def ensure_local_data() -> list:
    messages = []
    if bundle_available():
        return ["Datos precomputados de data_bundle/ (sin descargas de fuentes crudas)."]
    os.makedirs(DATA_DIR, exist_ok=True)
    for path, url in DATA_SOURCES:
        if not os.path.exists(path):
            try:
                _download_to_file(path, url, 60, "json")
                messages.append(f"Descargado {os.path.basename(path)}")
            except Exception as e:
                messages.append(f"No se pudo descargar {os.path.basename(path)}: {e}")

    for path, url in (
        (SUBE_USOS_2024_FILE, SUBE_USOS_2024_URL),
        (SUBE_USOS_2025_FILE, SUBE_USOS_2025_URL),
        (SUBE_USOS_2026_FILE, SUBE_USOS_2026_URL),
    ):
        if not os.path.exists(path):
            messages.append(f"Descargando {os.path.basename(path)}...")
            try:
                _download_to_file(path, url, 600, "csv")
                messages.append(f"Descargado {os.path.basename(path)}")
            except Exception as e:
                messages.append(f"No se pudo descargar {os.path.basename(path)}: {e}")

    if not os.path.exists(RENABAP_AMBA_FILE):
        messages.append("Descargando RE-NABAP nacional y filtrando AMBA...")
        try:
            resp = requests.get(RENABAP_AMBA_URL, timeout=300)
            resp.raise_for_status()
            national = resp.json()
            amba = _filter_renabap_amba(national)
            with open(RENABAP_AMBA_FILE, "w", encoding="utf-8") as f:
                json.dump(amba, f, ensure_ascii=False)
            messages.append(f"Guardado RE-NABAP AMBA: {len(amba['features'])} barrios")
        except Exception as e:
            messages.append(f"No se pudo descargar RE-NABAP: {e}")

    bus_downloads = [(p, u, l) for p, u, l, _j in AMBA_BUS_SOURCES]
    for path, url, label in bus_downloads + AMBA_OVERLAY_SOURCES:
        if not os.path.exists(path):
            messages.append(f"Descargando {label}...")
            try:
                _download_to_file(path, url, 600, "json")
                messages.append(f"Descargado {os.path.basename(path)}")
            except Exception as e:
                messages.append(f"No se pudo descargar {label}: {e}")

    return messages


# ---------------------------------------------------------------------------
# Construccion de tablas
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def build_stops_table(fc: dict) -> pd.DataFrame:
    rows = []
    for feature in fc["features"]:
        props = feature["properties"]
        lon, lat = feature["geometry"]["coordinates"]
        lineas = [props[k] for k in ("L1", "L2", "L3", "L4", "L5", "L6")]
        for linea in lineas:
            if linea is None or str(linea).strip() == "":
                continue
            if not str(linea).isdigit():
                continue
            rows.append(
                {
                    "linea": str(linea).zfill(3),
                    "lat": lat,
                    "lon": lon,
                    "direccion": props.get("DIRECCION"),
                    "barrio": props.get("BARRIO"),
                    "comuna": props.get("COMUNA"),
                }
            )
    df = pd.DataFrame(rows)
    return df.drop_duplicates(subset=["linea", "lat", "lon"])


@st.cache_data(show_spinner=False)
def build_routes_table(fc: dict) -> pd.DataFrame:
    rows = []
    for feature in fc["features"]:
        props = feature["properties"]
        coords = feature["geometry"]["coordinates"]
        rows.append(
            {
                "linea": str(props["linea"]).zfill(3),
                "recorrido": props.get("recorrido"),
                "sentido": props.get("sentido"),
                "modalidad": props.get("modalidad"),
                "desde": props.get("desde"),
                "hasta": props.get("hasta"),
                "coords": coords,
                "coords_simple": _simplify_route_coords(coords),
                "longitud_m": _route_length_m(coords),
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def _load_amba_sources() -> list[tuple[dict, str]]:
    sources = []
    for path, _url, _label, jur in AMBA_BUS_SOURCES:
        if os.path.exists(path):
            with open(path, encoding="utf-8-sig") as f:
                sources.append((json.load(f), jur))
    return sources


@st.cache_data(show_spinner=False)
def build_routes_table_amba(routes_fc: dict, rmba_sources) -> pd.DataFrame:
    base = build_routes_table(routes_fc)
    base["jurisdiccion"] = "CABA"
    rows = []
    seen = set(base["linea"])
    for fc, jur in rmba_sources:
        for feature in fc["features"]:
            linea = _norm_rmba_linea(feature["properties"].get("LINEA"))
            if linea is None or linea in seen:
                continue
            seen.add(linea)
            coords = _clean_route_coords(feature["geometry"])
            if not coords:
                continue
            rows.append(
                {
                    "linea": linea,
                    "recorrido": _clean_label(feature["properties"].get("RAMAL")),
                    "sentido": _norm_sentido(feature["properties"].get("SENTIDO")),
                    "modalidad": jur,
                    "desde": None,
                    "hasta": None,
                    "coords": coords,
                    "coords_simple": _simplify_route_coords(coords),
                    "longitud_m": _route_length_m(coords),
                    "jurisdiccion": jur,
                }
            )
    extra = pd.DataFrame(rows, columns=list(base.columns))
    return pd.concat([base, extra], ignore_index=True)


@st.cache_data(show_spinner=False)
def load_stops_df() -> pd.DataFrame:
    """Tabla de paradas (formato largo por linea). Bundle-first, fallback raw."""
    df = _read_parquet_bundle(BUNDLE_STOPS_FILE)
    if df is not None:
        return df
    return build_stops_table(load_geojson(STOPS_FILE, STOPS_URL))


@st.cache_data(show_spinner=False)
def load_routes_df() -> pd.DataFrame:
    """Tabla de recorridos AMBA completos (BA Data + RMBA). Bundle-first."""
    df = _read_parquet_bundle(BUNDLE_ROUTES_FILE)
    if df is not None:
        return df
    routes_fc = load_geojson(ROUTES_FILE, ROUTES_URL)
    return build_routes_table_amba(routes_fc, _load_amba_sources())


# ---------------------------------------------------------------------------
# Subte / ferrocarril
# ---------------------------------------------------------------------------
def _fc_lines_df(fc: dict, label_field: str, extra=None) -> pd.DataFrame:
    rows = []
    for feature in fc["features"]:
        props = feature["properties"]
        row = {"coords": _clean_route_coords(feature["geometry"]),
               "label": _clean_label(props.get(label_field))}
        if extra:
            for k, fld in extra.items():
                row[k] = _clean_label(props.get(fld))
        rows.append(row)
    return pd.DataFrame(rows)


def build_subte_lines_df(fc: dict) -> pd.DataFrame:
    return _fc_lines_df(fc, "LINEASUB")


def build_subte_stations_df(fc: dict) -> pd.DataFrame:
    rows = []
    for feature in fc["features"]:
        c = feature["geometry"]["coordinates"]
        props = feature["properties"]
        rows.append({
            "estacion": _clean_label(props.get("ESTACION")),
            "linea": _clean_label(props.get("LINEA")),
            "lat": float(c[1]), "lon": float(c[0]),
        })
    return pd.DataFrame(rows)


def build_ffcc_lines_df(fc: dict) -> pd.DataFrame:
    rows = []
    for feature in fc["features"]:
        props = feature["properties"]
        rows.append({
            "linea": _clean_label(props.get("Linea")),
            "descrip": _clean_label(props.get("Descrip")),
            "coords": _clean_route_coords(feature["geometry"]),
        })
    return pd.DataFrame(rows)


def build_ffcc_stations_df(fc: dict) -> pd.DataFrame:
    rows = []
    for feature in fc["features"]:
        props = feature["properties"]
        lon = props.get("long")
        lat = props.get("lat")
        if lon is None or lat is None:
            continue
        rows.append({
            "nombre": _clean_label(props.get("nombre")),
            "linea": _clean_label(props.get("linea")),
            "ramal": _clean_label(props.get("ramal")),
            "lat": float(lat), "lon": float(lon),
        })
    return pd.DataFrame(rows)


def _load_geojson_safe(path: str, url: str, label: str) -> dict | None:
    try:
        return load_geojson(path, url)
    except Exception:
        st.warning(f"No se pudieron cargar los datos de {label}; se omite la capa.")
        return None


def _empty_lines_df():
    return pd.DataFrame(columns=["coords", "label"])


@st.cache_data(show_spinner=False)
def load_subte_lines() -> pd.DataFrame:
    df = _read_parquet_bundle(BUNDLE_SUBTE_LINES_FILE)
    if df is not None:
        return df
    fc = _load_geojson_safe(SUBTE_LINEAS_FILE, SUBTE_LINEAS_URL, "líneas de subte")
    return build_subte_lines_df(fc) if fc else _empty_lines_df()


@st.cache_data(show_spinner=False)
def load_subte_stations() -> pd.DataFrame:
    df = _read_parquet_bundle(BUNDLE_SUBTE_STATIONS_FILE)
    if df is not None:
        return df
    fc = _load_geojson_safe(SUBTE_ESTACIONES_FILE, SUBTE_ESTACIONES_URL, "estaciones de subte")
    return build_subte_stations_df(fc) if fc else pd.DataFrame(columns=["estacion", "linea", "lat", "lon"])


@st.cache_data(show_spinner=False)
def load_ffcc_lines() -> pd.DataFrame:
    df = _read_parquet_bundle(BUNDLE_FFCC_LINES_FILE)
    if df is not None:
        return df
    fc = _load_geojson_safe(FFCC_LINEAS_FILE, FFCC_LINEAS_URL, "líneas de ferrocarril")
    return build_ffcc_lines_df(fc) if fc else pd.DataFrame(columns=["linea", "descrip", "coords"])


@st.cache_data(show_spinner=False)
def load_ffcc_stations() -> pd.DataFrame:
    df = _read_parquet_bundle(BUNDLE_FFCC_STATIONS_FILE)
    if df is not None:
        return df
    fc = _load_geojson_safe(FFCC_ESTACIONES_FILE, FFCC_ESTACIONES_URL, "estaciones de ferrocarril")
    return build_ffcc_stations_df(fc) if fc else pd.DataFrame(columns=["nombre", "linea", "ramal", "lat", "lon"])


# ---------------------------------------------------------------------------
# Subte - viajes por molinete (SBASE / BA Data)
# ---------------------------------------------------------------------------
MOLINETES_STATION_ALIAS = {
    "carlos pellegrini": "c. pellegrini",
    "pellegrini": "c. pellegrini",
    "avenida de mayo": "av. de mayo",
    "av de mayo": "av. de mayo",
    "mariano moreno": "moreno",
    "scalabrini ortiz": "r.scalabrini ortiz",
    "pasteur": "pasteur - amia",
    "malabia": "malabia - osvaldo pugliese",
    "tronador": "tronador - villa ortuzar",
    "los incas": "de los incas -pque. chas",
    "de los incas": "de los incas -pque. chas",
    "incas": "de los incas -pque. chas",
    "once": "once - 30 de diciembre",
    "once 30 de diciembre": "once - 30 de diciembre",
    "30 de diciembre": "once - 30 de diciembre",
    "rosas": "juan manuel de rosas",
    "juan m de rosas": "juan manuel de rosas",
    "juan manuel de rosas": "juan manuel de rosas",
    "plaza de los virreyes": "plaza de los virreyes - eva peron",
    "pza. de los virreyes": "plaza de los virreyes - eva peron",
    "entre rios": "entre rios - rodolfo walsh",
    "patricios": "parque patricios",
    "humberto i": "humberto 1",
    "flores": "san jose de flores",
    "plaza miserere": "plaza de miserere",
    "pza. miserere": "plaza de miserere",
    "avenida la plata": "av. la plata",
    "retiro e": "retiro",
    "retiro c": "retiro",
    "retiro h": "retiro",
}
MOLINETES_IGNORED = {"", "#n/d", "null", "prueba"}
_MOLINETE_SMALL_WORDS = {"de", "del", "la", "las", "los", "y", "e", "a"}


def _molinete_line_letter(linea) -> str:
    s = str(linea or "").strip()
    return s[5:] if s.lower().startswith("linea") else s


def _decode_molinete(raw: bytes) -> str:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _title_station(norm_name: str) -> str:
    parts = norm_name.split()
    return " ".join(
        w.capitalize() if (i == 0 or w not in _MOLINETE_SMALL_WORDS) else w
        for i, w in enumerate(parts)
    )


def _norm_molinete_station(s: str) -> str:
    return _normalize(s)


def _molinete_zip_path(year: int) -> str:
    return os.path.join(MOLINETES_DIR, f"molinete_{year}.zip")


def _download_molinete_zip(year: int) -> str:
    path = _molinete_zip_path(year)
    if os.path.exists(path) and os.path.getsize(path) > 100_000:
        return path
    url = f"{MOLINETES_CDN}/{MOLINETES_FILES[year]}"
    os.makedirs(MOLINETES_DIR, exist_ok=True)
    resp = requests.get(
        url, timeout=1800, stream=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; panel-transporte-caba/1.0)"},
    )
    resp.raise_for_status()
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            fh.write(chunk)
    os.replace(tmp, path)
    return path


@st.cache_data(show_spinner=False)
def _molinetes_geo_names() -> dict:
    stations = load_subte_stations()
    mapa = {}
    for _, r in stations.iterrows():
        nombre = _clean_label(r["estacion"])
        if nombre:
            mapa.setdefault(_normalize(nombre), nombre)
    return mapa


def _canon_molinete_station(s: str, geo_names: dict) -> str:
    n = _norm_molinete_station(s)
    if n in MOLINETES_IGNORED:
        return ""
    n = MOLINETES_STATION_ALIAS.get(n, n)
    if n in geo_names:
        return geo_names[n]
    m = re.search(r"\.[a-z]$|\s[a-z]$", n)
    if m:
        alt = MOLINETES_STATION_ALIAS.get(n[: m.start()], n[: m.start()])
        if alt in geo_names:
            return geo_names[alt]
    return _title_station(n)


def _ingest_molinete_zip(year: int, geo_names: dict) -> dict:
    path = _download_molinete_zip(year)
    agg = defaultdict(int)
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.lower().endswith(".csv"):
                continue
            try:
                lines = _decode_molinete(z.read(name)).splitlines()
            except Exception:
                continue
            if not lines:
                continue
            hdr = lines[0].strip().lstrip('"').rstrip('"')
            if "pax_TOTAL" not in hdr:
                continue
            for line in lines[1:]:
                s = line.strip()
                if not s:
                    continue
                if s.endswith(";"):
                    s = s.rstrip(";")
                if s.startswith('"') and s.endswith('"'):
                    s = s[1:-1]
                fields = s.split(";")
                if len(fields) < 10:
                    continue
                estacion = _canon_molinete_station(fields[5], geo_names)
                if not estacion:
                    continue
                try:
                    fecha = datetime.strptime(fields[0].strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
                    hora = int(fields[1][:2])
                    viajes = int(fields[9])
                except (ValueError, TypeError):
                    continue
                agg[(fecha, hora, _molinete_line_letter(fields[3]), estacion)] += viajes
    return agg


def _molinetes_source_token() -> str:
    return _data_token([_molinete_zip_path(y) for y in sorted(MOLINETES_FILES)])


def _molinetes_aggregates_fresh() -> bool:
    if not (os.path.exists(MOLINETES_AGG_FILE) and os.path.exists(MOLINETES_AGG_META_FILE)):
        return False
    try:
        with open(MOLINETES_AGG_META_FILE, encoding="utf-8") as f:
            meta = json.load(f)
    except (ValueError, OSError):
        return False
    if meta.get("schema_version", 0) != MOLINETES_AGG_SCHEMA_VERSION:
        return False
    src_files = [_molinete_zip_path(y) for y in sorted(MOLINETES_FILES)]
    if [os.path.basename(p) for p in src_files] != meta.get("fuentes", []):
        return False
    if any(not os.path.exists(p) for p in src_files):
        return False
    return max(os.path.getmtime(p) for p in src_files) <= meta.get("built_after", 0)


def _build_molinetes_aggregates() -> pd.DataFrame:
    try:
        geo_names = _molinetes_geo_names()
    except Exception:
        geo_names = {}
    frames = []
    for year in sorted(MOLINETES_FILES):
        try:
            agg = _ingest_molinete_zip(year, geo_names)
        except Exception as e:
            st.warning(f"No se pudieron leer los molinetes {year}: {e}")
            continue
        if not agg:
            continue
        df = pd.DataFrame(agg.items(), columns=["key", "viajes"])
        df[["fecha", "hora", "linea", "estacion"]] = pd.DataFrame(list(df["key"]), index=df.index)
        frames.append(df.drop(columns=["key"]))
    if not frames:
        return pd.DataFrame(columns=["fecha", "hora", "linea", "estacion", "viajes"])
    df = pd.concat(frames, ignore_index=True)
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = (
        df.groupby(["fecha", "hora", "linea", "estacion"], as_index=False)["viajes"].sum()
        .sort_values(["fecha", "hora", "estacion", "linea"])
        .reset_index(drop=True)
    )
    df.to_csv(MOLINETES_AGG_FILE, index=False)
    src_files = [_molinete_zip_path(y) for y in sorted(MOLINETES_FILES)]
    meta = {
        "fuentes": [os.path.basename(p) for p in src_files],
        "built_after": max(os.path.getmtime(p) for p in src_files if os.path.exists(p)),
        "schema_version": MOLINETES_AGG_SCHEMA_VERSION,
        "años": sorted(MOLINETES_FILES),
    }
    with open(MOLINETES_AGG_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return df


@st.cache_data(show_spinner=False)
def load_molinetes(token: str) -> pd.DataFrame:
    df = _read_parquet_bundle(BUNDLE_MOLINETES_FILE)
    if df is not None:
        df["fecha"] = pd.to_datetime(df["fecha"])
        return df
    if _molinetes_aggregates_fresh():
        try:
            df = pd.read_csv(MOLINETES_AGG_FILE, dtype={"linea": str, "estacion": str})
            df["fecha"] = pd.to_datetime(df["fecha"])
            return df
        except Exception:
            pass
    return _build_molinetes_aggregates()


@st.cache_data(show_spinner=False)
def load_subte_stations_geo() -> pd.DataFrame:
    """Una fila por estación y línea con coordenadas, para el mapa de molinetes.

    El geojson trae estaciones homónimas en líneas distintas (p.ej. Callao y
    Pueyrredón en B y D, Independencia en C y E) con coordenadas propias; hay que
    conservarlas separadas o se pisan y el mapa las rotula con la línea equivocada.
    """
    stations = load_subte_stations()
    if stations.empty:
        return pd.DataFrame(columns=["nombre", "linea", "lat", "lon"])
    rows = {}
    for _, r in stations.iterrows():
        nombre = _clean_label(r["estacion"])
        if not nombre:
            continue
        linea = _clean_label(r["linea"])
        rows.setdefault((_normalize(nombre), linea), [nombre, linea, r["lat"], r["lon"]])
    return pd.DataFrame(rows.values(), columns=["nombre", "linea", "lat", "lon"])


# ---------------------------------------------------------------------------
# SUBE - normalizacion y lectura
# ---------------------------------------------------------------------------
def _normalize_sube_linea(code) -> str | None:
    # Mismo criterio de `_norm_rmba_linea`: primer grupo de dígitos + zfill(3).
    return _norm_rmba_linea(code)


def _is_caba_sube_row(code, jurisdiccion) -> bool:
    cu = "" if code is None else str(code).strip().upper()
    if cu.startswith(("CABA", "BSAS_LINEA", "BS_ASLINEA")):
        return True
    if "RZ" in cu or not cu:
        return False
    jur = "" if jurisdiccion is None else str(jurisdiccion).strip()
    return jur.upper() in ("NACIONAL", "C.A.B.A")


SUBE_SOURCE_FILES = [SUBE_USOS_2024_FILE, SUBE_USOS_2025_FILE, SUBE_USOS_2026_FILE]
SUBE_AGG_SCHEMA_VERSION = 2


def _sube_source_token() -> str:
    return _data_token(SUBE_SOURCE_FILES)


@st.cache_data(show_spinner=False)
def _read_sube_daily_all() -> pd.DataFrame:
    frames = []
    for path in SUBE_SOURCE_FILES:
        if not os.path.exists(path):
            continue
        df = pd.read_csv(
            path,
            usecols=[
                "DIA_TRANSPORTE", "LINEA", "AMBA", "TIPO_TRANSPORTE",
                "JURISDICCION", "CANTIDAD",
            ],
            dtype={"LINEA": str},
        )
        df["AMBA"] = df["AMBA"].str.strip().str.upper()
        df["TIP"] = df["TIPO_TRANSPORTE"].str.strip().str.upper()
        pref = df["LINEA"].astype(str).str.strip().str.upper()
        ok = pref.str.startswith(("CABA", "BSAS_LINEA", "BS_ASLINEA")) | (
            (~pref.str.contains("RZ"))
            & df["JURISDICCION"].fillna("").str.strip().str.upper().isin(["NACIONAL", "C.A.B.A"])
        )
        df = df[ok & (df["AMBA"] == "SI") & (df["TIP"] == "COLECTIVO")].copy()
        df["linea"] = df["LINEA"].apply(_normalize_sube_linea)
        df = df.dropna(subset=["linea"])
        df["fecha"] = pd.to_datetime(df["DIA_TRANSPORTE"])
        frames.append(df[["linea", "fecha", "CANTIDAD"]])
    if not frames:
        return pd.DataFrame(columns=["linea", "fecha", "CANTIDAD"])
    return pd.concat(frames, ignore_index=True)


def _sube_aggregates_fresh() -> bool:
    if not (
        os.path.exists(SUBE_MONTHLY_FILE)
        and os.path.exists(SUBE_DAILY_FILE)
        and os.path.exists(SUBE_AGG_META_FILE)
    ):
        return False
    try:
        with open(SUBE_AGG_META_FILE, encoding="utf-8") as f:
            meta = json.load(f)
    except (ValueError, OSError):
        return False
    if meta.get("schema_version", 1) != SUBE_AGG_SCHEMA_VERSION:
        return False
    src = list(meta.get("fuentes", []))
    src_files = [os.path.join(DATA_DIR, s) for s in src]
    if any(not os.path.exists(p) for p in src_files):
        return False
    src_max = max(os.path.getmtime(p) for p in src_files)
    return src_max <= meta.get("built_after", 0)


def _build_sube_aggregates() -> pd.DataFrame:
    try:
        df = _read_sube_daily_all()
    except Exception as e:
        st.warning(f"No se pudieron leer los datos fuente de SUBE: {e}")
        return pd.DataFrame(columns=["linea", "fecha", "transacciones"])
    if df.empty:
        return pd.DataFrame(columns=["linea", "fecha", "transacciones"])

    df["fecha_m"] = df["fecha"].dt.to_period("M").dt.to_timestamp()

    ultimo_dia = df.groupby("fecha_m")["fecha"].max().sort_index()
    last = ultimo_dia.index.max()
    if pd.to_datetime(ultimo_dia[last]).day < last.days_in_month:
        df = df[df["fecha_m"] < last]

    mensual = (
        df.groupby(["linea", "fecha_m"], as_index=False)["CANTIDAD"].sum()
        .rename(columns={"fecha_m": "fecha", "CANTIDAD": "transacciones"})
    )
    mensual = mensual.sort_values(["linea", "fecha"])
    cutoff = mensual["fecha"].max() - pd.DateOffset(months=23)
    mensual = mensual[mensual["fecha"] >= cutoff].reset_index(drop=True)

    daily = df[["linea", "fecha", "CANTIDAD"]].copy()
    daily_cut = mensual["fecha"].max() - pd.DateOffset(months=11)
    daily = daily[daily["fecha"] >= daily_cut].copy()
    weekday = daily["fecha"].dt.dayofweek
    is_feriado = daily["fecha"].dt.strftime("%Y-%m-%d").isin(FERIADOS_ARG)
    daily["tipo_dia"] = np.where(
        is_feriado,
        "Feriado",
        np.where(weekday < 5, "Día hábil", np.where(weekday == 5, "Sábado", "Domingo")),
    )
    daily = daily.rename(columns={"CANTIDAD": "transacciones"})[["linea", "fecha", "transacciones", "tipo_dia"]]

    mensual.to_csv(SUBE_MONTHLY_FILE, index=False)
    daily.to_csv(SUBE_DAILY_FILE, index=False)
    meta = {
        "fuentes": [os.path.basename(p) for p in SUBE_SOURCE_FILES],
        "built_after": max(os.path.getmtime(p) for p in SUBE_SOURCE_FILES if os.path.exists(p)),
        "schema_version": SUBE_AGG_SCHEMA_VERSION,
    }
    with open(SUBE_AGG_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return mensual


@st.cache_data(show_spinner=False)
def load_sube_transactions(token: str) -> pd.DataFrame:
    df = _read_parquet_bundle(BUNDLE_SUBE_MENSUAL_FILE)
    if df is not None:
        df["fecha"] = pd.to_datetime(df["fecha"]).dt.to_period("M").dt.to_timestamp()
        return df[["linea", "fecha", "transacciones"]].sort_values(["linea", "fecha"]).reset_index(drop=True)
    if _sube_aggregates_fresh():
        try:
            df = pd.read_csv(SUBE_MONTHLY_FILE, dtype={"linea": str})
            df["fecha"] = pd.to_datetime(df["fecha"]).dt.to_period("M").dt.to_timestamp()
            return df[["linea", "fecha", "transacciones"]].sort_values(["linea", "fecha"]).reset_index(drop=True)
        except Exception:
            pass
    return _build_sube_aggregates()


@st.cache_data(show_spinner=False)
def load_sube_daily(token: str) -> pd.DataFrame:
    df = _read_parquet_bundle(BUNDLE_SUBE_DIARIO_FILE)
    if df is not None:
        return df.sort_values(["linea", "fecha"]).reset_index(drop=True)
    if not _sube_aggregates_fresh():
        _build_sube_aggregates()
    if not os.path.exists(SUBE_DAILY_FILE):
        return pd.DataFrame(columns=["linea", "fecha", "transacciones", "tipo_dia"])
    try:
        df = pd.read_csv(SUBE_DAILY_FILE, dtype={"linea": str})
    except Exception:
        return pd.DataFrame(columns=["linea", "fecha", "transacciones", "tipo_dia"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df.sort_values(["linea", "fecha"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Colores de librea
# ---------------------------------------------------------------------------
def _livery_colors(description: str) -> list:
    norm = _normalize(description).replace(" y ", " ").replace(" con ", " ")
    return [BASE_COLORS[t] for t in norm.split() if t in BASE_COLORS]


def route_colors(description: str | None):
    cols = _livery_colors(description) if description else []
    if not cols:
        return "#7f7f7f", None
    white = BASE_COLORS["blanco"]
    if len(cols) == 1:
        color = cols[0]
        band = "#3a3a3a" if color == white else None
        return color, band
    non_white = [c for c in cols if c != white]
    color = non_white[0] if non_white else cols[0]
    band = cols[0]
    if band == color:
        band = next((c for c in cols[1:] if c != color), None)
    return color, band


# ---------------------------------------------------------------------------
# Dibujo en Folium
# ---------------------------------------------------------------------------
def draw_route(m, coords, color, band=None, weight=4, opacity=0.8, tooltip=None, popup=None):
    if isinstance(popup, str) and popup:
        popup = folium.Popup(popup, max_width=280)
    for segment in coords:
        locations = [(lat, lon) for lon, lat in segment]
        if band:
            folium.PolyLine(
                locations=locations,
                color=band,
                weight=weight + 2,
                opacity=0.9,
            ).add_to(m)
        kw = {"color": color, "weight": weight, "opacity": opacity}
        if tooltip:
            kw["tooltip"] = tooltip
        if popup is not None:
            kw["popup"] = popup
        folium.PolyLine(locations, **kw).add_to(m)


def draw_osm_stops(m, stops_df):
    for _, stop_row in stops_df.iterrows():
        folium.CircleMarker(
            location=[stop_row["lat"], stop_row["lon"]],
            radius=3,
            color="#0f766e",
            weight=1,
            fill=True,
            fill_color="#14b8a6",
            fill_opacity=0.9,
            tooltip=f"Parada AMBA: {stop_row['name'] or 's/d'}",
        ).add_to(m)


def draw_subte_stations(m, df):
    for _, r in df.iterrows():
        nombre = r["estacion"]
        folium.CircleMarker(
            location=[r["lat"], r["lon"]],
            radius=4,
            color="white",
            weight=1,
            fill=True,
            fill_color=_subte_line_color(r["linea"]),
            fill_opacity=0.9,
            tooltip=f"{nombre} · Línea {r['linea']}" if nombre else f"Subte Línea {r['linea']}",
            popup=(
                folium.Popup(f"<b>Estación {nombre}</b><br>Línea {r['linea']}", max_width=260)
                if nombre
                else ""
            ),
        ).add_to(m)


def draw_ffcc_stations(m, df):
    for _, r in df.iterrows():
        nombre = r["nombre"]
        ramal = f" · {r['ramal']}" if r["ramal"] else ""
        if nombre:
            tooltip = f"{nombre} · {r['linea']}"
            popup_txt = f"<b>Estación {nombre}</b><br>Ferrocarril {r['linea']}{ramal}"
        else:
            tooltip = f"Ferrocarril {r['linea']}"
            popup_txt = f"<b>Ferrocarril {r['linea']}</b>"
        folium.CircleMarker(
            location=[r["lat"], r["lon"]],
            radius=4,
            color="white",
            weight=1,
            fill=True,
            fill_color=FFCC_COLOR,
            fill_opacity=0.9,
            tooltip=tooltip,
            popup=folium.Popup(popup_txt, max_width=260),
        ).add_to(m)


def routes_to_geojson(routes_df, color_func=None, use_simple=True) -> dict:
    """Convierte una tabla de rutas en un único FeatureCollection para dibujar
    miles de recorridos en una sola capa de Folium (mucho más liviano)."""
    features = []
    for _, r in routes_df.iterrows():
        coords = r["coords_simple"] if use_simple else r["coords"]
        if not coords:
            continue
        color = color_func(r) if color_func else "#7f7f7f"
        properties = {
            "linea": r["linea"],
            "ramal": _clean_label(r["recorrido"]),
            "sentido": r["sentido"],
            "desde": _clean_label(r["desde"]),
            "hasta": _clean_label(r["hasta"]),
            "jurisdiccion": r.get("jurisdiccion"),
            "color": color,
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "MultiLineString", "coordinates": coords},
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def geo_route_style(feature):
    return {"color": feature["properties"].get("color", "#7f7f7f")}


def draw_renabap(m, fc, color=RENABAP_COLOR):
    def style_fn(feature):
        return {
            "fillColor": color,
            "color": color,
            "weight": 2,
            "fillOpacity": 0.35,
        }

    layer = folium.GeoJson(
        fc,
        style_function=style_fn,
        tooltip=GeoJsonTooltip(
            fields=["nombre_barrio", "departamento"],
            aliases=["", ""],
            localize=True,
        ),
        popup=GeoJsonPopup(
            fields=[
                "nombre_barrio", "provincia", "departamento",
                "localidad", "familias_aproximadas", "id_renabap",
            ],
            aliases=[
                "Barrio", "Provincia", "Partido",
                "Localidad", "Familias aprox.", "ID RE-NABAP",
            ],
            localize=True,
            style="font-size:12px;",
        ),
        name="Barrios populares RE-NABAP (AMBA)",
    )
    layer.add_to(m)


# ---------------------------------------------------------------------------
# Paradas OSM
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def build_osm_stops_table(fc: dict) -> pd.DataFrame:
    rows = []
    for feature in fc["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        if (
            CABA_BOX["lon_min"] <= lon <= CABA_BOX["lon_max"]
            and CABA_BOX["lat_min"] <= lat <= CABA_BOX["lat_max"]
        ):
            continue
        rows.append(
            {"lat": lat, "lon": lon, "name": feature["properties"].get("name")}
        )
    df = pd.DataFrame(rows)
    return df.drop_duplicates(subset=["lat", "lon"])


@st.cache_data(show_spinner=False)
def _download_osm_stops() -> None:
    errors = []
    for url in OSM_STOPS_URLS:
        try:
            resp = requests.get(
                url,
                params={"data": _osm_stops_query()},
                headers={"User-Agent": OSM_STOPS_USER_AGENT},
                timeout=600,
            )
            resp.raise_for_status()
            osm_raw = resp.json()
            features = []
            for el in osm_raw["elements"]:
                tags = el.get("tags", {})
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [el["lon"], el["lat"]]},
                        "properties": {
                            "osm_id": el["id"],
                            "name": tags.get("name"),
                            "network": tags.get("network"),
                        },
                    }
                )
            fc = {"type": "FeatureCollection", "features": features}
            with open(OSM_STOPS_FILE, "w", encoding="utf-8") as f:
                json.dump(fc, f, ensure_ascii=False)
            return
        except Exception as e:
            errors.append(f"{url}: {e}")
    raise RuntimeError("; ".join(errors))


@st.cache_data(show_spinner=False)
def load_osm_stops() -> pd.DataFrame:
    if not os.path.exists(OSM_STOPS_FILE):
        try:
            _download_osm_stops()
        except Exception:
            st.warning(
                "No se pudieron descargar las paradas AMBA de OpenStreetMap (Overpass). "
                "Se omite la capa."
            )
            return pd.DataFrame(columns=["lat", "lon", "name"])
    with open(OSM_STOPS_FILE, encoding="utf-8") as f:
        fc = json.load(f)
    return build_osm_stops_table(fc)


# ---------------------------------------------------------------------------
# RE-NABAP
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_renabap_geojson():
    if bundle_available() and os.path.exists(BUNDLE_RENABAP_FILE):
        try:
            with gzip.open(BUNDLE_RENABAP_FILE, "rt", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        return load_geojson(RENABAP_AMBA_FILE, RENABAP_AMBA_URL)
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def load_renabap_centroids() -> pd.DataFrame:
    fc = _load_renabap_geojson()
    if fc is None:
        return pd.DataFrame(columns=["id", "barrio", "partido", "lat", "lon", "familias"])
    rows = []
    for feature in fc["features"]:
        props = feature["properties"]
        geom = feature["geometry"]
        if geom["type"] == "Polygon":
            polys = [geom["coordinates"]]
        else:
            polys = geom["coordinates"]
        xs, ys = [], []
        for poly in polys:
            for ring in poly:
                for lon, lat in ring:
                    xs.append(lon)
                    ys.append(lat)
        if not xs:
            continue
        rows.append(
            {
                "id": props.get("id_renabap"),
                "barrio": props.get("nombre_barrio"),
                "partido": props.get("departamento"),
                "lat": sum(ys) / len(ys),
                "lon": sum(xs) / len(xs),
                "familias": props.get("familias_aproximadas"),
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def load_renabap_points() -> pd.DataFrame:
    fc = _load_renabap_geojson()
    if fc is None:
        return pd.DataFrame(columns=["id", "lat", "lon"])
    rows = []
    for feature in fc["features"]:
        props = feature["properties"]
        geom = feature["geometry"]
        if geom["type"] == "Polygon":
            polys = [geom["coordinates"]]
        else:
            polys = geom["coordinates"]
        b_id = props.get("id_renabap")
        for poly in polys:
            for ring in poly:
                for lon, lat in ring:
                    rows.append({"id": b_id, "lat": float(lat), "lon": float(lon)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Redes espaciales: aplanado de coordenadas + grilla de proximidad
# ---------------------------------------------------------------------------
# La grilla se construye una sola vez por contenido de datos (token de mtime de
# archivos fuente) y las consultas reciben argumentos hasheables (str/int), no
# DataFrames con columnas de listas: evita que st.cache_data haga pickle de las
# ~440k coordenadas en cada rerun ("unhashable type: 'list'").
NET_CELL_M = 100.0


def _source_token(files) -> str:
    parts = []
    for p in files:
        parts.append("1" if os.path.exists(p) else "0")
        if os.path.exists(p):
            parts.append(f"{os.path.getmtime(p):.0f}")
    return "|".join(parts)


def _data_token(files) -> str:
    """Token de cache: bundle si esta disponible, si no mtimes de los fuentes."""
    return _bundle_token() or _source_token(files)


def _flatten_network(df) -> tuple:
    lat, lon, owner = [], [], []
    for i, row in enumerate(df.itertuples()):
        for seg in row.coords:
            if not seg:
                continue
            for c in seg:
                lat.append(float(c[1]))
                lon.append(float(c[0]))
                owner.append(i)
    return (
        np.asarray(lat, dtype=float),
        np.asarray(lon, dtype=float),
        np.asarray(owner, dtype=int),
    )


def route_points_latlon(routes_df) -> tuple:
    """Aplana las coordenadas de una tabla de rutas en (lats, lons)."""
    lat, lon, _ = _flatten_network(routes_df)
    return lat.tolist(), lon.tolist()


@st.cache_data(show_spinner=False)
def bus_network(token: str) -> tuple:
    routes_df = load_routes_df()
    return _flatten_network(routes_df)


@st.cache_data(show_spinner=False)
def subte_network(token: str) -> tuple:
    return _flatten_network(load_subte_lines())


@st.cache_data(show_spinner=False)
def ffcc_network(token: str) -> tuple:
    return _flatten_network(load_ffcc_lines())


def build_point_grid(lat, lon, cell_m=NET_CELL_M):
    """Grilla espacial sobre una nube de puntos; devuelve (dict de buckets, meta)."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    lat_m = 111_320.0
    if lat.size == 0:
        return {}, (lat_m, 0.0, cell_m)
    lon_m = lat_m * np.cos(np.radians(float(lat.mean())))
    gi = np.floor(lat * lat_m / cell_m).astype(int)
    gj = np.floor(lon * lon_m / cell_m).astype(int)
    grid = {}
    for i in range(lat.size):
        grid.setdefault((int(gi[i]), int(gj[i])), []).append(i)
    return grid, (lat_m, lon_m, cell_m)


def _grid_matches(grid, meta, net_lat, net_lon, qlat, qlon, radius_m):
    """Devuelve (índices de red a <=radius, máscara de puntos query alcanzados)."""
    lat_m, lon_m, cell_m = meta
    qlat = np.atleast_1d(np.asarray(qlat, dtype=float))
    qlon = np.atleast_1d(np.asarray(qlon, dtype=float))
    nq = qlat.size
    query_hit = np.zeros(nq, dtype=bool)
    net_hit = set()
    if nq == 0 or not grid:
        return net_hit, query_hit
    steps = int(np.ceil(radius_m / cell_m)) + 1
    for k in range(nq):
        gk_lat = int(qlat[k] * lat_m / cell_m)
        gk_lon = int(qlon[k] * lon_m / cell_m)
        hit = False
        for di in range(-steps, steps + 1):
            for dj in range(-steps, steps + 1):
                bucket = grid.get((gk_lat + di, gk_lon + dj))
                if not bucket:
                    continue
                idx = np.asarray(bucket)
                d = _haversine_np(qlat[k], qlon[k], net_lat[idx], net_lon[idx])
                m = d <= radius_m
                if m.any():
                    net_hit.update(idx[m].tolist())
                    hit = True
            if hit:
                break
        query_hit[k] = hit
    return net_hit, query_hit


@st.cache_data(show_spinner=False)
def renabap_covered_ids(show_subte: bool, show_ffcc: bool) -> frozenset:
    """IDs RE-NABAP con al menos un vértice de frontera a <= RENABAP_RADIUS_M de la red."""
    ren = load_renabap_points()
    if ren.empty:
        return frozenset()
    lat, lon, _ = bus_network(_data_token(ROUTES_SOURCE_FILES))
    if show_subte:
        slat, slon, _ = subte_network(_data_token([SUBTE_LINEAS_FILE]))
        lat = np.concatenate([lat, slat])
        lon = np.concatenate([lon, slon])
    if show_ffcc:
        flat, flon, _ = ffcc_network(_data_token([FFCC_LINEAS_FILE]))
        lat = np.concatenate([lat, flat])
        lon = np.concatenate([lon, flon])
    if lat.size == 0:
        return frozenset()
    grid, meta = build_point_grid(lat, lon)
    _, query_hit = _grid_matches(grid, meta, lat, lon, ren["lat"], ren["lon"], RENABAP_RADIUS_M)
    return frozenset(int(v) for v in np.asarray(ren["id"])[query_hit])


@st.cache_data(show_spinner=False)
def lines_near_barrio(bar_id: int, radius_m: int, network: str) -> tuple:
    """Índices de línea (row en la df del modo) a <= radius_m de la frontera del barrio."""
    ren = load_renabap_points()
    bpts = ren[ren["id"] == bar_id]
    if bpts.empty:
        return ()
    if network == "bus":
        lat, lon, owner = bus_network(_data_token(ROUTES_SOURCE_FILES))
    elif network == "subte":
        lat, lon, owner = subte_network(_data_token([SUBTE_LINEAS_FILE]))
    elif network == "ffcc":
        lat, lon, owner = ffcc_network(_data_token([FFCC_LINEAS_FILE]))
    else:
        return ()
    if lat.size == 0:
        return ()
    grid, meta = build_point_grid(lat, lon)
    hits, _ = _grid_matches(grid, meta, lat, lon, bpts["lat"], bpts["lon"], radius_m)
    owners = {int(o) for o in owner[np.asarray(sorted(hits), dtype=int)]}
    return tuple(sorted(owners))


@st.cache_data(show_spinner=False)
def load_comunas() -> dict:
    if bundle_available() and os.path.exists(BUNDLE_COMUNAS_FILE):
        try:
            with gzip.open(BUNDLE_COMUNAS_FILE, "rt", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            pass
    return load_geojson(COMUNAS_FILE, COMUNAS_URL)


@st.cache_data(show_spinner=False)
def comuna_demand_table(stops_df: pd.DataFrame, sube: pd.DataFrame) -> pd.DataFrame:
    stops_caba = stops_df.copy()
    stops_caba["comuna"] = pd.to_numeric(stops_caba["comuna"], errors="coerce")
    stops_caba = stops_caba[stops_caba["comuna"].between(1, 15)].dropna(subset=["comuna"])
    stops_caba["comuna"] = stops_caba["comuna"].astype(int)
    if stops_caba.empty or sube.empty:
        return pd.DataFrame(columns=["comuna", "usos", "paradas"])

    counts = stops_caba.groupby(["linea", "comuna"], as_index=False).size()
    counts = counts.rename(columns={"size": "paradas"})
    per_line_total = counts.groupby("linea", as_index=False)["paradas"].sum().rename(
        columns={"paradas": "total_paradas_caba"}
    )
    counts = counts.merge(per_line_total, on="linea")
    counts["weight"] = counts["paradas"] / counts["total_paradas_caba"]

    sube12 = sube[sube["fecha"] >= sube["fecha"].max() - pd.DateOffset(months=11)]
    line_tot = sube12.groupby("linea", as_index=False)["transacciones"].sum().rename(
        columns={"transacciones": "usos_12m"}
    )
    counts = counts.merge(line_tot, on="linea", how="inner")
    counts["usos"] = counts["weight"] * counts["usos_12m"]

    return (
        counts.groupby("comuna", as_index=False)["usos"].sum()
        .sort_values("comuna")
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Formateo
# ---------------------------------------------------------------------------
def _fmt(n, suffix="", default="s/d"):
    if n is None or (isinstance(n, float) and n != n):
        return default
    try:
        return f"{int(n):,}".replace(",", ".") + suffix
    except (TypeError, ValueError):
        return default


def _fmt_dec(n, decimals=1, suffix=""):
    if n is None or (isinstance(n, float) and n != n):
        return "s/d"
    try:
        return f"{float(n):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".") + suffix
    except (TypeError, ValueError):
        return "s/d"


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------
def _metric_box_html(label: str, value_html: str, sub_html: str = "", badges_html: str = "") -> str:
    sub = f'<div class="mb-sub">{sub_html}</div>' if sub_html else ""
    badges = f'<div class="mb-delta">{badges_html}</div>' if badges_html else ""
    return (
        f'<div class="metric-box"><div class="mb-label">{label}</div>'
        f'<div class="mb-value">{value_html}</div>{sub}{badges}</div>'
    )


def _delta_pill_html(pct) -> str:
    if pct is None:
        return '<span class="delta-pill flat">—</span>'
    if pct > 0:
        cls, arrow = "up", "▲"
    elif pct < 0:
        cls, arrow = "down", "▼"
    else:
        cls, arrow = "flat", "▬"
    return f'<span class="delta-pill {cls}">{arrow} {_fmt_dec(abs(pct))}%</span>'


# ---------------------------------------------------------------------------
# CSS compartido
# ---------------------------------------------------------------------------
THEME_CSS = """
<style>
html, body, .stApp, .stApp * {
    font-family: "Calibri", "Segoe UI", Tahoma, Arial, sans-serif !important;
}
.app-header {
    border-bottom: 1px solid #2a3142;
    padding-bottom: 10px;
    margin-bottom: 6px;
}
div.metric-box {
    background: linear-gradient(160deg, #1b2232 0%, #131824 100%);
    border: 1px solid #2d3548;
    border-radius: 16px;
    padding: 16px 20px 18px 20px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, .38);
}
div.metric-box .mb-label {
    color: #8b95ab;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .7px;
    text-transform: uppercase;
}
div.metric-box .mb-value {
    color: #ffffff;
    font-size: 52px;
    font-weight: 700;
    line-height: 1.05;
    margin-top: 4px;
    font-variant-numeric: tabular-nums;
}
div.metric-box .mb-value small {
    font-size: 22px;
    font-weight: 600;
    color: #aeb8cc;
    margin-left: 6px;
}
div.metric-box .mb-sub {
    margin-top: 12px;
    border-top: 1px solid #2d3548;
    padding-top: 10px;
    font-size: 15px;
    color: #aeb8cc;
    display: flex;
    justify-content: space-between;
    gap: 14px;
}
div.metric-box .mb-sub .num {
    color: #ffffff;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}
div.tx-detached {
    margin-top: 92px;
}
div.mb-delta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
}
span.delta-pill {
    border-radius: 20px;
    padding: 4px 11px;
    font-size: 13px;
    font-weight: 700;
    white-space: nowrap;
}
span.delta-pill.up {
    color: #3ddc84;
    background: rgba(61, 220, 132, .14);
}
span.delta-pill.down {
    color: #ff7b7b;
    background: rgba(255, 123, 123, .14);
}
span.delta-pill.flat {
    color: #aeb8cc;
    background: rgba(174, 184, 204, .14);
}
</style>
"""
