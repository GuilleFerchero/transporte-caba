import os
import re
import json
import unicodedata
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

SUBE_MONTHLY_FILE = os.path.join(DATA_DIR, "sube_usos_mensuales.csv")
SUBE_DAILY_FILE = os.path.join(DATA_DIR, "sube_usos_diarios.csv")
SUBE_AGG_META_FILE = os.path.join(DATA_DIR, "sube_agregados_meta.json")

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


@st.cache_data(show_spinner=False)
def ensure_local_data() -> list:
    messages = []
    os.makedirs(DATA_DIR, exist_ok=True)
    for path, url in DATA_SOURCES:
        if not os.path.exists(path):
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            with open(path, "wb") as f:
                f.write(resp.content)
            messages.append(f"Descargado {os.path.basename(path)}")

    for path, url in (
        (SUBE_USOS_2024_FILE, SUBE_USOS_2024_URL),
        (SUBE_USOS_2025_FILE, SUBE_USOS_2025_URL),
        (SUBE_USOS_2026_FILE, SUBE_USOS_2026_URL),
    ):
        if not os.path.exists(path):
            messages.append(f"Descargando {os.path.basename(path)}...")
            try:
                resp = requests.get(url, timeout=600)
                resp.raise_for_status()
                with open(path, "wb") as f:
                    f.write(resp.content)
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
                resp = requests.get(url, timeout=600)
                resp.raise_for_status()
                with open(path, "wb") as f:
                    f.write(resp.content)
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
    fc = _load_geojson_safe(SUBTE_LINEAS_FILE, SUBTE_LINEAS_URL, "líneas de subte")
    return build_subte_lines_df(fc) if fc else _empty_lines_df()


@st.cache_data(show_spinner=False)
def load_subte_stations() -> pd.DataFrame:
    fc = _load_geojson_safe(SUBTE_ESTACIONES_FILE, SUBTE_ESTACIONES_URL, "estaciones de subte")
    return build_subte_stations_df(fc) if fc else pd.DataFrame(columns=["estacion", "linea", "lat", "lon"])


@st.cache_data(show_spinner=False)
def load_ffcc_lines() -> pd.DataFrame:
    fc = _load_geojson_safe(FFCC_LINEAS_FILE, FFCC_LINEAS_URL, "líneas de ferrocarril")
    return build_ffcc_lines_df(fc) if fc else pd.DataFrame(columns=["linea", "descrip", "coords"])


@st.cache_data(show_spinner=False)
def load_ffcc_stations() -> pd.DataFrame:
    fc = _load_geojson_safe(FFCC_ESTACIONES_FILE, FFCC_ESTACIONES_URL, "estaciones de ferrocarril")
    return build_ffcc_stations_df(fc) if fc else pd.DataFrame(columns=["nombre", "linea", "ramal", "lat", "lon"])


# ---------------------------------------------------------------------------
# SUBE - normalizacion y lectura
# ---------------------------------------------------------------------------
def _normalize_sube_linea(code) -> str | None:
    if code is None or pd.isna(code):
        return None
    m = re.search(r"(\d+)", str(code))
    if not m:
        return None
    n = int(m.group(1))
    return f"{n:03d}" if n > 0 else None


def _is_caba_sube_row(code, jurisdiccion) -> bool:
    cu = "" if code is None else str(code).strip().upper()
    if cu.startswith(("CABA", "BSAS_LINEA", "BS_ASLINEA")):
        return True
    if "RZ" in cu or not cu:
        return False
    jur = "" if jurisdiccion is None else str(jurisdiccion).strip()
    return jur.upper() in ("NACIONAL", "C.A.B.A")


SUBE_SOURCE_FILES = [SUBE_USOS_2024_FILE, SUBE_USOS_2025_FILE, SUBE_USOS_2026_FILE]


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


def _sube_source_token() -> str:
    parts = []
    for path in SUBE_SOURCE_FILES:
        parts.append("1" if os.path.exists(path) else "0")
        if os.path.exists(path):
            parts.append(f"{os.path.getmtime(path):.0f}")
    return "|".join(parts)


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
    daily["tipo_dia"] = daily["fecha"].dt.dayofweek.map(
        {0: "Día hábil", 1: "Día hábil", 2: "Día hábil", 3: "Día hábil", 4: "Día hábil",
         5: "Sábado", 6: "Domingo"}
    )
    daily = daily.rename(columns={"CANTIDAD": "transacciones"})[["linea", "fecha", "transacciones", "tipo_dia"]]

    mensual.to_csv(SUBE_MONTHLY_FILE, index=False)
    daily.to_csv(SUBE_DAILY_FILE, index=False)
    meta = {
        "fuentes": [os.path.basename(p) for p in SUBE_SOURCE_FILES],
        "built_after": max(os.path.getmtime(p) for p in SUBE_SOURCE_FILES if os.path.exists(p)),
    }
    with open(SUBE_AGG_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return mensual


@st.cache_data(show_spinner=False)
def load_sube_transactions(token: str) -> pd.DataFrame:
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


@st.cache_data(show_spinner=False)
def load_comunas() -> dict:
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
