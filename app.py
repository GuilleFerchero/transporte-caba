import streamlit as st
import folium
import requests
import pandas as pd
from streamlit_folium import st_folium

STOPS_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos-paradas/paradas-de-colectivo.geojson"
ROUTES_URL = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/transporte-y-obras-publicas/colectivos-recorridos/recorrido-colectivos.geojson"

COLOR_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


@st.cache_data(show_spinner=False)
def load_geojson(url: str) -> dict:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


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


def color_for_line(linea: str):
    idx = (int(linea) - 1) % len(COLOR_PALETTE)
    return COLOR_PALETTE[idx]


def draw_route(m, route_row, color):
    for segment in route_row["coords"]:
        folium.PolyLine(
            locations=[(lat, lon) for lon, lat in segment],
            color=color,
            weight=4,
            opacity=0.8,
            tooltip=(
                f"Línea {route_row['linea']} - "
                f"Recorrido {route_row['recorrido']} - {route_row['sentido']}"
            ),
        ).add_to(m)


st.set_page_config(
    page_title="Panel de Transporte CABA",
    page_icon="🚌",
    layout="wide",
)

st.title("Panel de Visualización de Transporte")
st.subheader("Ciudad Autónoma de Buenos Aires - Líneas de colectivo y paradas")

with st.spinner("Descargando datos abiertos de BA Data..."):
    stops_fc = load_geojson(STOPS_URL)
    routes_fc = load_geojson(ROUTES_URL)

stops_df = build_stops_table(stops_fc)
routes_df = build_routes_table(routes_fc)

route_lineas = set(routes_df["linea"])
stop_lineas = set(stops_df["linea"])
lineas = sorted(route_lineas | stop_lineas, key=int)

col_sel, col_info = st.columns([1, 3])

with col_sel:
    linea = st.selectbox(
        "Línea de colectivo",
        ["Todas las líneas"] + lineas,
        index=0,
    )

with col_info:
    if linea != "Todas las líneas":
        st.caption(
            f"{len(stops_df[stops_df['linea'] == linea])} paradas "
            f"y {len(routes_df[routes_df['linea'] == linea])} recorridos disponibles."
        )
    else:
        st.caption(
            f"{len(stops_df)} paradas y {len(routes_df)} recorridos "
            f"para {len(lineas)} líneas."
        )

m = folium.Map(location=[-34.6037, -58.3816], zoom_start=12)

if linea == "Todas las líneas":
    for _, route_row in routes_df.iterrows():
        draw_route(m, route_row, color_for_line(route_row["linea"]))
else:
    for _, route_row in routes_df[routes_df["linea"] == linea].iterrows():
        if route_row["sentido"] == "IDA":
            color = "#1a73e8"
        else:
            color = "#e8710a"
        draw_route(m, route_row, color)

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

    lat_min, lat_max = stops_df[stops_df["linea"] == linea]["lat"].min(), stops_df[stops_df["linea"] == linea]["lat"].max()
    lon_min, lon_max = stops_df[stops_df["linea"] == linea]["lon"].min(), stops_df[stops_df["linea"] == linea]["lon"].max()
    m.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]], padding=(20, 20))

st_folium(m, width="100%", height=650)

with st.expander("Sobre los datos"):
    st.markdown(
        "Fuente: [BA Data](https://data.buenosaires.gob.ar) - "
        "[Colectivos: recorridos](https://data.buenosaires.gob.ar/dataset/colectivos-recorridos) "
        "y [Colectivos: paradas](https://data.buenosaires.gob.ar/dataset/colectivos-paradas). "
        "Licencia CC-BY-2.5-AR. "
        "Los recorridos se colorean según el sentido (ida/vuelta) para una línea seleccionada "
        "y según la línea cuando se muestran todas."
    )