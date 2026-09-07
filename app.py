import os
import re
import json
import unicodedata
import numpy as np
import streamlit as st
import folium
import requests
import pandas as pd
from folium.features import GeoJsonTooltip, GeoJsonPopup
from streamlit_folium import st_folium

STOPS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos-paradas/paradas-de-colectivo.geojson"
ROUTES_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos-recorridos/recorrido-colectivos.geojson"
SUBE_USOS_2025_URL = "https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2025.csv"
SUBE_USOS_2026_URL = "https://archivos-datos.transporte.gob.ar/upload/Dat_Ab_Usos/dat-ab-usos-2026.csv"
RENABAP_AMBA_URL = "https://www.argentina.gob.ar/sites/default/files/renabap-2023-12-06.geojson"
OSM_STOPS_URL = "https://overpass.kumi.systems/api/interpreter"
OSM_STOPS_USER_AGENT = "panel-transporte-caba/1.0 (dashboard Streamlit de colectivos AMBA)"
OSM_AMBA_BBOX = "(-35.02,-58.80,-34.40,-58.05)"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STOPS_FILE = os.path.join(DATA_DIR, "paradas-de-colectivo.geojson")
ROUTES_FILE = os.path.join(DATA_DIR, "recorrido-colectivos.geojson")
RENABAP_AMBA_FILE = os.path.join(DATA_DIR, "renabap_amba.geojson")
OSM_STOPS_FILE = os.path.join(DATA_DIR, "paradas_amba_osm.geojson")
SUBE_USOS_2025_FILE = os.path.join(DATA_DIR, "dat-ab-usos-2025.csv")
SUBE_USOS_2026_FILE = os.path.join(DATA_DIR, "dat-ab-usos-2026.csv")

DATA_SOURCES = [
    (STOPS_FILE, STOPS_URL),
    (ROUTES_FILE, ROUTES_URL),
]

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

CABA_BOX = {
    "lat_min": -34.705, "lat_max": -34.520,
    "lon_min": -58.533, "lon_max": -58.340,
}

OSM_STOP_RADIUS_M = 150

SEL_LINEA = "— Seleccioná una línea —"

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


@st.cache_data(show_spinner=False)
def load_geojson(path: str, url: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
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
        else:
            messages.append(f"Usando datos locales: {os.path.basename(path)}")

    for path, url in (
        (SUBE_USOS_2025_FILE, SUBE_USOS_2025_URL),
        (SUBE_USOS_2026_FILE, SUBE_USOS_2026_URL),
    ):
        if not os.path.exists(path):
            resp = requests.get(url, timeout=600)
            resp.raise_for_status()
            with open(path, "wb") as f:
                f.write(resp.content)
            messages.append(f"Descargado {os.path.basename(path)}")
        else:
            messages.append(f"Usos SUBE diarios (local): {os.path.basename(path)}")

    if not os.path.exists(RENABAP_AMBA_FILE):
        messages.append("Descargando RE-NABAP nacional y filtrando AMBA...")
        resp = requests.get(RENABAP_AMBA_URL, timeout=300)
        resp.raise_for_status()
        national = resp.json()
        amba = _filter_renabap_amba(national)
        with open(RENABAP_AMBA_FILE, "w", encoding="utf-8") as f:
            json.dump(amba, f, ensure_ascii=False)
        messages.append(f"Guardado RE-NABAP AMBA: {len(amba['features'])} barrios")
    else:
        messages.append("Usando datos locales: renabap_amba.geojson")

    if not os.path.exists(OSM_STOPS_FILE):
        messages.append("Descargando paradas AMBA desde OpenStreetMap (Overpass)...")
        resp = requests.get(
            OSM_STOPS_URL,
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
        messages.append(f"Guardadas paradas AMBA desde OSM: {len(features)}")
    else:
        messages.append("Usando datos locales: paradas_amba_osm.geojson")

    return messages


def _osm_stops_query() -> str:
    return (
        "[out:json][timeout:300];"
        "(node[\"highway\"=\"bus_stop\"]{b};"
        "node[\"public_transport\"=\"platform\"][\"bus\"=\"yes\"]{b};);"
        "out body;"
    ).format(b=OSM_AMBA_BBOX)


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
        rows.append(
            {
                "linea": str(props["linea"]).zfill(3),
                "recorrido": props.get("recorrido"),
                "sentido": props.get("sentido"),
                "modalidad": props.get("modalidad"),
                "desde": props.get("desde"),
                "hasta": props.get("hasta"),
                "coords": feature["geometry"]["coordinates"],
            }
        )
    return pd.DataFrame(rows)


def _route_distance_m(route_row) -> float:
    total = 0.0
    for segment in route_row["coords"]:
        for i in range(1, len(segment)):
            lon1, lat1 = segment[i - 1]
            lon2, lat2 = segment[i]
            total += _haversine_np(lat1, lon1, lat2, lon2)
    return float(total)


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


@st.cache_data(show_spinner=False)
def load_sube_transactions() -> pd.DataFrame:
    monthly = []
    daymap = []
    for path in (SUBE_USOS_2025_FILE, SUBE_USOS_2026_FILE):
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
        df["fecha"] = pd.to_datetime(df["DIA_TRANSPORTE"]).dt.to_period("M").dt.to_timestamp()
        monthly.append(df.groupby(["linea", "fecha"], as_index=False)["CANTIDAD"].sum())
        daymap.append(df[["fecha", "DIA_TRANSPORTE"]])
    if not monthly:
        return pd.DataFrame(columns=["linea", "fecha", "transacciones"])
    result = pd.concat(monthly).rename(columns={"CANTIDAD": "transacciones"})
    ultimo_dia = (
        pd.concat(daymap).groupby("fecha")["DIA_TRANSPORTE"].max().sort_index()
    )
    last = ultimo_dia.index.max()
    if pd.to_datetime(ultimo_dia[last]).day < last.days_in_month:
        result = result[result["fecha"] < last]
    result = result.sort_values(["linea", "fecha"])
    cutoff = result["fecha"].max() - pd.DateOffset(months=11)
    return result[result["fecha"] >= cutoff].reset_index(drop=True)


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


def draw_route(m, route_row, color, band=None):
    for segment in route_row["coords"]:
        locations = [(lat, lon) for lon, lat in segment]
        if band:
            folium.PolyLine(
                locations=locations,
                color=band,
                weight=6,
                opacity=0.9,
            ).add_to(m)
        folium.PolyLine(
            locations=locations,
            color=color,
            weight=4,
            opacity=0.8,
            tooltip=(
                f"Línea {route_row['linea']} - "
                f"Recorrido {route_row['recorrido']} - {route_row['sentido']}"
            ),
        ).add_to(m)


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
def load_osm_stops() -> pd.DataFrame:
    with open(OSM_STOPS_FILE, encoding="utf-8") as f:
        fc = json.load(f)
    return build_osm_stops_table(fc)


def _haversine_np(lat1, lon1, lat2, lon2):
    r_earth = 6_371_000.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return r_earth * 2 * np.arcsin(np.sqrt(a))


def osm_stops_for_line(osm_df: pd.DataFrame, lats, lons, radius_m=OSM_STOP_RADIUS_M) -> pd.DataFrame:
    if osm_df.empty or not lats:
        return osm_df.iloc[0:0]
    lat_arr = np.asarray(lats, dtype=float)
    lon_arr = np.asarray(lons, dtype=float)
    pad = 0.012
    cand = osm_df[
        (osm_df["lat"] >= lat_arr.min() - pad)
        & (osm_df["lat"] <= lat_arr.max() + pad)
        & (osm_df["lon"] >= lon_arr.min() - pad)
        & (osm_df["lon"] <= lon_arr.max() + pad)
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


def _fmt(n, suffix="", default="s/d"):
    if n is None or (isinstance(n, float) and n != n):
        return default
    try:
        return f"{int(n):,}".replace(",", ".") + suffix
    except (TypeError, ValueError):
        return default


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


st.set_page_config(
    page_title="Panel de Transporte CABA",
    page_icon="🚌",
    layout="wide",
)

st.title("Panel de Visualización de Transporte")
st.subheader("Ciudad Autónoma de Buenos Aires - Líneas de colectivo y paradas")

data_messages = ensure_local_data()
for message in data_messages:
    st.caption(message)

with st.spinner("Cargando datos de colectivos..."):
    stops_fc = load_geojson(STOPS_FILE, STOPS_URL)
    routes_fc = load_geojson(ROUTES_FILE, ROUTES_URL)

stops_df = build_stops_table(stops_fc)
routes_df = build_routes_table(routes_fc)

route_lineas = set(routes_df["linea"])
stop_lineas = set(stops_df["linea"])
lineas = sorted(route_lineas | stop_lineas, key=int)

col_sel, col_info = st.columns([1, 3])

with col_sel:
    linea = st.selectbox(
        "Línea de colectivo",
        [SEL_LINEA, "Todas las líneas"] + lineas,
        index=0,
    )
    real_linea = linea not in (SEL_LINEA, "Todas las líneas")

    recorrido = "Todos"
    sentido = "Ambos"
    show_osm_stops = False
    if real_linea:
        line_recorridos = sorted(
            routes_df[routes_df["linea"] == linea]["recorrido"].dropna().unique(),
            key=lambda r: (len(str(r)), str(r)),
        )
        if len(line_recorridos) > 1:
            recorrido = st.selectbox(
                "Recorrido",
                ["Todos"] + list(line_recorridos),
                key="recorrido_sel",
            )
        sentido = st.selectbox(
            "Sentido",
            ["Ambos", "IDA", "VUELTA"],
            key="sentido_sel",
        )
        show_osm_stops = st.checkbox("Paradas de colectivo AMBA (OpenStreetMap)", value=False)
    show_renabap = st.checkbox("Barrios populares RE-NABAP (AMBA)", value=False)

if "last_linea" in st.session_state and st.session_state["last_linea"] != linea:
    for key in ("recorrido_sel", "sentido_sel"):
        st.session_state.pop(key, None)
if real_linea:
    st.session_state["last_linea"] = linea

if real_linea:
    line_routes = routes_df[routes_df["linea"] == linea]
    if recorrido != "Todos":
        line_routes = line_routes[line_routes["recorrido"] == recorrido]
    if sentido != "Ambos":
        line_routes = line_routes[line_routes["sentido"] == sentido]

osm_match = pd.DataFrame()
if real_linea and show_osm_stops:
    with st.spinner("Filtrando paradas AMBA (OSM)..."):
        osm_stops_all = load_osm_stops()
        lats, lons = [], []
        for _, route_row in line_routes.iterrows():
            for segment in route_row["coords"]:
                lats.extend(float(c[1]) for c in segment)
                lons.extend(float(c[0]) for c in segment)
        osm_match = osm_stops_for_line(osm_stops_all, lats, lons)

with col_info:
    if real_linea:
        total_km = sum(_route_distance_m(row) for _, row in line_routes.iterrows()) / 1000.0
        caption = (
            f"{len(stops_df[stops_df['linea'] == linea])} paradas, "
            f"{len(line_routes)} recorridos "
            f"(recorrido {recorrido}, {sentido}) y {total_km:,.1f} km de recorrido."
        )
        if show_osm_stops:
            caption += f" Paradas AMBA (OSM): {len(osm_match)}."
        st.caption(caption)
    elif linea == "Todas las líneas":
        total_km = sum(_route_distance_m(row) for _, row in routes_df.iterrows()) / 1000.0
        st.caption(
            f"{len(stops_df)} paradas y {len(routes_df)} recorridos "
            f"para {len(lineas)} líneas ({total_km:,.0f} km totales de recorrido)."
        )
    else:
        st.caption("Seleccioná una línea para ver sus recorridos y paradas, o mostrá todas las líneas.")

m = folium.Map(location=[-34.6037, -58.3816], zoom_start=12)

if linea == "Todas las líneas":
    for _, route_row in routes_df.iterrows():
        color, band = route_colors(LINE_COLORS.get(route_row["linea"]))
        draw_route(m, route_row, color, band)
elif real_linea:
    for _, route_row in line_routes.iterrows():
        color, band = route_colors(LINE_COLORS.get(linea))
        draw_route(m, route_row, color, band)

    for _, stop_row in stops_df[stops_df["linea"] == linea].iterrows():
        folium.CircleMarker(
            location=[stop_row["lat"], stop_row["lon"]],
            radius=4,
            color="white",
            weight=1,
            fill=True,
            fill_color="#111111",
            fill_opacity=0.9,
            tooltip=f"Línea {linea}: {stop_row['direccion']}",
            popup=folium.Popup(
                f"<b>{stop_row['direccion']}</b><br>"
                f"Barrio: {stop_row['barrio']}<br>"
                f"Comuna: {stop_row['comuna']}",
                max_width=250,
            ),
        ).add_to(m)

    if show_osm_stops and not osm_match.empty:
        draw_osm_stops(m, osm_match)

    lats, lons = [], []
    for _, route_row in line_routes.iterrows():
        for segment in route_row["coords"]:
            lats.extend(float(c[1]) for c in segment)
            lons.extend(float(c[0]) for c in segment)
    if lats:
        m.fit_bounds(
            [[min(lats), min(lons)], [max(lats), max(lons)]],
            padding=(20, 20),
        )

if show_renabap:
    with st.spinner("Cargando barrios populares RE-NABAP (AMBA)..."):
        renabap_fc = load_geojson(RENABAP_AMBA_FILE, RENABAP_AMBA_URL)
    draw_renabap(m, renabap_fc)

st_folium(m, width="100%", height=650, returned_objects=[])

if real_linea:
    sube = load_sube_transactions()
    line_sube = sube[sube["linea"] == linea]
    if line_sube.empty:
        st.info(f"No hay indicadores de transacciones SUBE para la línea {linea}.")
    else:
        st.subheader(f"Transacciones SUBE - Línea {linea}")
        chart_df = line_sube[["fecha", "transacciones"]].set_index("fecha")
        st.line_chart(chart_df)
        st.caption(
            f"Fuente: Secretaría de Transporte (datos.transporte.gob.ar) - "
            f"transacciones SUBE (usos) por fecha. Usos diarios agregados por mes "
            f"(AMBA), de {line_sube['fecha'].min():%m/%Y} a {line_sube['fecha'].max():%m/%Y}."
        )

with st.expander("Sobre los datos"):
    st.markdown(
        "Fuente: [BA Data](https://data.buenosaires.gob.ar) - "
        "[Colectivos: recorridos](https://data.buenosaires.gob.ar/dataset/colectivos-recorridos), "
        "[Colectivos: paradas](https://data.buenosaires.gob.ar/dataset/colectivos-paradas). "
        "Licencia CC-BY-2.5-AR. "
        "Barrios populares: [RE-NABAP](https://www.argentina.gob.ar/obras-publicas/sisu/renabap) "
        "(Registro Nacional de Barrios Populares, dataset 2023 filtrado a AMBA). "
        "Paradas del conurbano: [OpenStreetMap](https://www.openstreetmap.org) "
        "(paradas de colectivo descargadas vía Overpass, filtradas por proximidad al recorrido). "
        "Transacciones SUBE: [Secretaría de Transporte](https://datos.transporte.gob.ar) - "
        "[Cantidad de transacciones SUBE (usos) por fecha](https://datos.transporte.gob.ar/dataset/sube-cantidad-de-transacciones-usos-por-fecha) "
        "(usos diarios por línea en AMBA, agregados mensualmente). "
        "Los recorridos se colorean según la librea definida por línea (colores cargados "
        "manualmente en lineas_colores.xlsx); el sentido se indica en el tooltip de "
        "cada trazo."
    )