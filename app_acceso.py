import copy
import os
import pandas as pd
import numpy as np
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.features import GeoJsonTooltip, GeoJsonPopup

from data_loaders import (
    ensure_local_data,
    load_geojson,
    load_subte_lines,
    load_subte_stations,
    load_ffcc_lines,
    load_ffcc_stations,
    load_renabap_points,
    load_renabap_centroids,
    _load_amba_sources,
    _load_renabap_geojson,
    _subte_line_color,
    build_routes_table_amba,
    _haversine_np,
    draw_route,
    route_colors,
    THEME_CSS,
    STOPS_FILE,
    STOPS_URL,
    ROUTES_FILE,
    ROUTES_URL,
    AMBA_BUS_BOUNDS,
    RENABAP_RADIUS_M,
    JUR_COLOR,
    FFCC_COLOR,
    LINE_COLORS,
    BASE_COLORS,
    _fmt,
    _fmt_dec,
)

COBERTO_COLOR = "#2e9e4b"
NO_COBERTO_COLOR = "#d62728"
BARRIO_BUS_RADIUS_M = 500
BARRIO_RAIL_RADIUS_M = 1200

st.set_page_config(
    page_title="Acceso a la Ciudad AMBA",
    page_icon="🏘️",
    layout="wide",
)

st.markdown(THEME_CSS, unsafe_allow_html=True)

st.title("Acceso a la Ciudad desde Barrios Populares")
st.subheader("Cobertura de la red de transporte (colectivo, subte y ferrocarril) sobre los barrios RE-NABAP del AMBA")


@st.cache_data(show_spinner=False)
def _network_coords(routes_df, show_subte, show_ffcc):
    lats, lons = [], []
    for _, route_row in routes_df.iterrows():
        for segment in route_row["coords"]:
            lats.extend(float(c[1]) for c in segment)
            lons.extend(float(c[0]) for c in segment)
    if show_subte:
        for _, r in load_subte_lines().iterrows():
            for segment in r["coords"]:
                lats.extend(float(c[1]) for c in segment)
                lons.extend(float(c[0]) for c in segment)
    if show_ffcc:
        for _, r in load_ffcc_lines().iterrows():
            for segment in r["coords"]:
                lats.extend(float(c[1]) for c in segment)
                lons.extend(float(c[0]) for c in segment)
    return lats, lons


@st.cache_data(show_spinner=False)
def _covered_ids(routes_df, show_subte, show_ffcc) -> set:
    ren_points = load_renabap_points()
    lats, lons = _network_coords(routes_df, show_subte, show_ffcc)
    if not lats or ren_points.empty:
        return set()
    return _grid_near_ids(lats, lons, ren_points, RENABAP_RADIUS_M)


def _grid_near_ids(route_lats, route_lons, ren_df, radius_m) -> set:
    rp = np.column_stack([np.asarray(route_lats, dtype=float),
                          np.asarray(route_lons, dtype=float)])
    if rp.size == 0:
        return set()
    lat_m = 111_320.0
    lon_m = lat_m * np.cos(np.radians(float(np.mean(rp[:, 0]))))
    cell_m = radius_m / 2.0
    glat = np.floor(rp[:, 0] * lat_m / cell_m).astype(int)
    glon = np.floor(rp[:, 1] * lon_m / cell_m).astype(int)
    grid = {}
    for i in range(len(rp)):
        grid.setdefault((int(glat[i]), int(glon[i])), []).append(i)
    r_lat = ren_df["lat"].to_numpy(dtype=float)
    r_lon = ren_df["lon"].to_numpy(dtype=float)
    r_ids = ren_df["id"].to_numpy()
    steps = 3
    covered = set()
    for k in range(len(ren_df)):
        gk_lat = int(r_lat[k] * lat_m / cell_m)
        gk_lon = int(r_lon[k] * lon_m / cell_m)
        best = np.inf
        for di in range(-steps, steps + 1):
            for dj in range(-steps, steps + 1):
                bucket = grid.get((gk_lat + di, gk_lon + dj))
                if not bucket:
                    continue
                idx = np.asarray(bucket)
                d = _haversine_np(r_lat[k], r_lon[k], rp[idx, 0], rp[idx, 1])
                best = min(best, float(d.min()))
                if best <= radius_m:
                    break
            if best <= radius_m:
                break
        if best <= radius_m:
            covered.add(int(r_ids[k]))
    return covered


@st.cache_data(show_spinner=False)
def _lines_near_barrio(lines_df, bar_id, radius_m) -> tuple:
    if "coords" not in lines_df.columns:
        return ()
    ren_points = load_renabap_points()
    bpts = ren_points[ren_points["id"] == bar_id]
    if bpts.empty:
        return ()
    b_lat = bpts["lat"].to_numpy(dtype=float)
    b_lon = bpts["lon"].to_numpy(dtype=float)
    lat_m = 111_320.0
    lon_m = lat_m * np.cos(np.radians(float(b_lat.mean())))
    cell_m = radius_m / 2.0
    rl, rln, ridx = [], [], []
    for i, row in lines_df.iterrows():
        for seg in row["coords"]:
            for c in seg:
                rl.append(float(c[1]))
                rln.append(float(c[0]))
                ridx.append(i)
    if not rl:
        return ()
    rl = np.asarray(rl, dtype=float)
    rln = np.asarray(rln, dtype=float)
    ridx = np.asarray(ridx, dtype=int)
    glat = np.floor(rl * lat_m / cell_m).astype(int)
    glon = np.floor(rln * lon_m / cell_m).astype(int)
    grid = {}
    for i in range(len(rl)):
        grid.setdefault((int(glat[i]), int(glon[i])), []).append(i)
    steps = 3
    found = set()
    for k in range(len(bpts)):
        gk_lat = int(b_lat[k] * lat_m / cell_m)
        gk_lon = int(b_lon[k] * lon_m / cell_m)
        for di in range(-steps, steps + 1):
            for dj in range(-steps, steps + 1):
                bucket = grid.get((gk_lat + di, gk_lon + dj))
                if not bucket:
                    continue
                idx = np.asarray(bucket)
                d = _haversine_np(b_lat[k], b_lon[k], rl[idx], rln[idx])
                m = d <= radius_m
                if m.any():
                    found.update(ridx[idx[m]].astype(int).tolist())
    return tuple(sorted(found))


@st.cache_data(show_spinner=False)
def _barrio_bounds(bar_id):
    ren_points = load_renabap_points()
    bpts = ren_points[ren_points["id"] == bar_id]
    if bpts.empty:
        return None
    return [
        [float(bpts["lat"].min()), float(bpts["lon"].min())],
        [float(bpts["lat"].max()), float(bpts["lon"].max())],
    ]


def _point_in_multi_polygon(lat, lon, geom) -> bool:
    if geom.get("type") != "MultiPolygon":
        return False
    x, y = float(lon), float(lat)
    inside = False
    for polygon in geom["coordinates"]:
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


def _find_barrio_at(lat, lon, fc) -> int | None:
    for feature in fc["features"]:
        if _point_in_multi_polygon(lat, lon, feature["geometry"]):
            id_renabap = feature["properties"].get("id_renabap")
            if id_renabap is not None:
                return int(id_renabap)
    return None


@st.cache_data(show_spinner=False)
def _renabap_fc_with_estado(covered: frozenset):
    fc = _load_renabap_geojson()
    if fc is None:
        return None
    out = copy.deepcopy(fc)
    for feature in out["features"]:
        eid = feature["properties"].get("id_renabap")
        feature["properties"]["estado"] = "con cobertura" if eid in covered else "sin cobertura"
    return out


data_messages = ensure_local_data()
for message in data_messages:
    st.caption(message)

with st.spinner("Cargando datos..."):
    stops_fc = load_geojson(STOPS_FILE, STOPS_URL)
    routes_fc = load_geojson(ROUTES_FILE, ROUTES_URL)
    routes_df = build_routes_table_amba(routes_fc, _load_amba_sources())

with st.sidebar:
    st.markdown("### Redes consideradas")
    st.caption(
        "La cobertura siempre considera todas las líneas de colectivo del AMBA. "
        "En el mapa, el colectivo está oculto por defecto para no saturarlo; "
        "se muestra solo para el barrio seleccionado o tildando esta opción:"
    )
    show_subte = st.checkbox("Subte (CABA)", value=True)
    show_ffcc = st.checkbox("Ferrocarril (AMBA)", value=True)
    show_bus = st.checkbox("Mostrar todas las líneas de colectivo", value=False)

    st.markdown("### Filtro territorial")
    ren_centroids_full = load_renabap_centroids()
    partidos = ["Todos"] + sorted(
        ren_centroids_full["partido"].dropna().unique(),
        key=lambda p: (len(str(p)), str(p)),
    )
    partido_filter = st.selectbox("Partido / Comuna", partidos)

    barrio_labels = {}
    barrio_label_of_id = {}
    for _, r in ren_centroids_full.iterrows():
        label = f"{r['barrio']} · {r['partido']}"
        barrio_labels[label] = int(r["id"])
        barrio_label_of_id[int(r["id"])] = label

    map_state = st.session_state.get("acceso_map")
    click = (map_state or {}).get("last_object_clicked") or (map_state or {}).get("last_clicked")
    if click and click.get("lat") is not None and click.get("lng") is not None:
        click_key = (round(float(click["lat"]), 5), round(float(click["lng"]), 5))
        if st.session_state.get("_processed_click") != click_key:
            st.session_state["_processed_click"] = click_key
            renabap_fc = _load_renabap_geojson()
            if renabap_fc is not None:
                clicked_id = _find_barrio_at(float(click["lat"]), float(click["lng"]), renabap_fc)
                if clicked_id is not None and clicked_id in barrio_label_of_id:
                    st.session_state["barrio_sel"] = barrio_label_of_id[clicked_id]

    barrio_opts = ["Todos"] + sorted(
        barrio_labels.keys(), key=lambda s: (len(s), s.lower())
    )
    barrio_sel = st.selectbox(
        "Barrio popular (colectivo cerca)",
        barrio_opts,
        key="barrio_sel",
        help="Elegí un barrio de la lista o hacé clic sobre un polígono en el mapa: se muestran las líneas de transporte que pasan cerca.",
    )

with st.spinner("Midiendo cobertura de la red..."):
    covered = _covered_ids(routes_df, show_subte, show_ffcc)
    ren_centroids = load_renabap_centroids().copy()

ren_centroids["cobertura"] = ren_centroids["id"].astype(int).isin(covered)
ren_centroids["personas"] = ren_centroids["familias"] * 4

if partido_filter != "Todos":
    ren_centroids = ren_centroids[ren_centroids["partido"] == partido_filter].reset_index(drop=True)

if ren_centroids.empty:
    st.warning("No hay barrios populares para el filtro seleccionado.")
    st.stop()

total_barrios = len(ren_centroids)
con_cobertura = int(ren_centroids["cobertura"].sum())
sin_cobertura = total_barrios - con_cobertura
familias_cubiertas = int(ren_centroids.loc[ren_centroids["cobertura"], "familias"].sum())
pct = 100.0 * con_cobertura / total_barrios if total_barrios else 0.0

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        f'<div class="metric-box"><div class="mb-label">Barrios con cobertura</div>'
        f'<div class="mb-value">{_fmt(con_cobertura)}<small>/ {_fmt(total_barrios)}</small></div>'
        f'<div class="mb-sub"><span>a ≤ {RENABAP_RADIUS_M} m de alguna red</span></div></div>',
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        f'<div class="metric-box"><div class="mb-label">Barrios sin cobertura</div>'
        f'<div class="mb-value" style="color:{NO_COBERTO_COLOR};">{_fmt(sin_cobertura)}</div>'
        f'<div class="mb-sub"><span>lejos de toda la red considerada</span></div></div>',
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        f'<div class="metric-box"><div class="mb-label">Familias con cobertura</div>'
        f'<div class="mb-value">{_fmt(familias_cubiertas)}<small>fam.</small></div>'
        f'<div class="mb-sub"><span>~ {_fmt(familias_cubiertas * 4)} personas (×4)</span></div></div>',
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        f'<div class="metric-box"><div class="mb-label">% del AMBA conectado</div>'
        f'<div class="mb-value">{_fmt_dec(pct)}<small>%</small></div>'
        f'<div class="mb-sub"><span>de los barrios populares analizados</span></div></div>',
        unsafe_allow_html=True,
    )

red_label = "red de colectivo AMBA"
suffix = []
if show_subte:
    suffix.append("subte")
if show_ffcc:
    suffix.append("ferrocarril")
if suffix:
    red_label += " + " + " y ".join(suffix)
st.caption(
    f"Se considera con cobertura un barrio popular cuando la <b>frontera</b> de su polígono cae a "
    f"≤ {RENABAP_RADIUS_M} m de al menos una línea de {red_label}. "
    f"El conteo usa los vértices del polígono (barrios alargados bordean la red aunque su centroide quede lejos).",
    unsafe_allow_html=True,
)

m = folium.Map(location=[-34.6037, -58.3816], zoom_start=10)

bar_id = None
bus_routes = routes_df.iloc[0:0]
near_subte_idx = None
near_ffcc_idx = None
if barrio_sel != "Todos":
    bar_id = barrio_labels[barrio_sel]
    bus_routes = routes_df.iloc[np.asarray(_lines_near_barrio(routes_df, bar_id, BARRIO_BUS_RADIUS_M))]
    near_subte_idx = set(_lines_near_barrio(load_subte_lines(), bar_id, BARRIO_RAIL_RADIUS_M))
    near_ffcc_idx = set(_lines_near_barrio(load_ffcc_lines(), bar_id, BARRIO_RAIL_RADIUS_M))
elif show_bus:
    bus_routes = routes_df

renabap_fc = _renabap_fc_with_estado(frozenset(covered))
if renabap_fc is not None:
    def style_fn(feature):
        is_covered = feature["properties"].get("estado") == "con cobertura"
        color = COBERTO_COLOR if is_covered else NO_COBERTO_COLOR
        selected = bar_id is not None and feature["properties"].get("id_renabap") == bar_id
        return {
            "fillColor": color,
            "color": "#ffffff" if selected else color,
            "weight": 3.5 if selected else 1.5,
            "fillOpacity": 0.45,
        }

    folium.GeoJson(
        renabap_fc,
        style_function=style_fn,
        tooltip=GeoJsonTooltip(
            fields=["nombre_barrio", "departamento", "estado"],
            aliases=["Barrio", "Partido", ""],
            localize=True,
        ),
        popup=GeoJsonPopup(
            fields=[
                "nombre_barrio", "departamento", "localidad",
                "familias_aproximadas", "estado", "id_renabap",
            ],
            aliases=[
                "Barrio", "Partido", "Localidad",
                "Familias aprox.", "", "ID RE-NABAP",
            ],
            localize=True,
            style="font-size:12px;",
        ),
        name="Barrios populares RE-NABAP (AMBA)",
    ).add_to(m)

bus_weight = 2.5 if bar_id is not None else 1.5
bus_opacity = 0.85 if bar_id is not None else 0.4

for _, route_row in bus_routes.iterrows():
    color = JUR_COLOR.get(route_row.get("jurisdiccion"), "#7f7f7f")
    if route_row.get("jurisdiccion") in (None, "CABA"):
        color, _ = route_colors(LINE_COLORS.get(route_row["linea"]))
    ramal = route_row.get("recorrido")
    ramal = ramal if ramal not in (None, "", "s/d") else "s/d"
    sentido = route_row.get("sentido") or "s/d"
    popup_html = f"<b>Línea {route_row['linea']}</b> · Ramal {ramal}<br>Sentido: {sentido}"
    if route_row.get("desde") and route_row.get("hasta"):
        popup_html += f"<br>{route_row['desde']} → {route_row['hasta']}"
    draw_route(
        m,
        route_row["coords_simple"],
        color,
        None,
        weight=bus_weight,
        opacity=bus_opacity,
        tooltip=f"Línea {route_row['linea']} · Ramal {ramal} · {sentido}",
        popup=popup_html,
    )

if show_subte:
    subte_lines = load_subte_lines()
    subte_stations = load_subte_stations()
    if near_subte_idx is not None:
        subte_lines = subte_lines.iloc[np.asarray(sorted(near_subte_idx))]
        visible = set(subte_lines["label"].dropna())
        subte_stations = subte_stations[subte_stations["linea"].isin(visible)]
    for _, r in subte_lines.iterrows():
        draw_route(
            m, r["coords"], _subte_line_color(r["label"]), None,
            weight=3, opacity=0.85, tooltip=f"Subte - Línea {r['label']}",
            popup=f"<b>Subte - Línea {r['label']}</b>",
        )
    for _, r in subte_stations.iterrows():
        folium.CircleMarker(
            location=[r["lat"], r["lon"]],
            radius=4,
            color="white",
            weight=1,
            fill=True,
            fill_color=_subte_line_color(r["linea"]),
            fill_opacity=0.9,
            tooltip=f"{r['estacion']} · Línea {r['linea']}" if r["estacion"] else f"Subte Línea {r['linea']}",
            popup=folium.Popup(
                f"<b>Estación {r['estacion']}</b><br>Subte - Línea {r['linea']}",
                max_width=260,
            ),
        ).add_to(m)

if show_ffcc:
    ffcc_lines = load_ffcc_lines()
    ffcc_stations = load_ffcc_stations()
    if near_ffcc_idx is not None:
        ffcc_lines = ffcc_lines.iloc[np.asarray(sorted(near_ffcc_idx))]
        visible = set(ffcc_lines["linea"].dropna())
        ffcc_stations = ffcc_stations[ffcc_stations["linea"].isin(visible)]
    for _, r in ffcc_lines.iterrows():
        label = f"Ferrocarril {r['linea']}"
        if r.get("descrip"):
            label += f" - {r['descrip']}"
        draw_route(
            m, r["coords"], FFCC_COLOR, None,
            weight=3, opacity=0.85, tooltip=label,
            popup=f"<b>{label}</b>",
        )
    for _, r in ffcc_stations.iterrows():
        folium.CircleMarker(
            location=[r["lat"], r["lon"]],
            radius=4,
            color="white",
            weight=1,
            fill=True,
            fill_color=FFCC_COLOR,
            fill_opacity=0.9,
            tooltip=f"{r['nombre']} · {r['linea']}" if r["nombre"] else f"Ferrocarril {r['linea']}",
            popup=folium.Popup(
                f"<b>Estación {r['nombre']}</b><br>Ferrocarril {r['linea']}"
                f"{' · ' + r['ramal'] if r['ramal'] else ''}",
                max_width=260,
            ),
        ).add_to(m)

if bar_id is not None:
    bb = _barrio_bounds(bar_id)
    if bb:
        m.fit_bounds(bb, padding=(60, 60))
else:
    m.fit_bounds(AMBA_BUS_BOUNDS, padding=(0, 0))

if bar_id is not None:
    st.caption(
        f"Mostrando <b>{len(bus_routes)}</b> línea(s) de colectivo a ≤ {BARRIO_BUS_RADIUS_M} m y "
        f"los trazos de <b>subte</b> y <b>ferrocarril</b> a ≤ {BARRIO_RAIL_RADIUS_M} m de <b>{barrio_sel}</b>. "
        f"Para ver el contexto completo, tildá <i>Mostrar todas las líneas de colectivo</i> "
        f"en la barra lateral.",
        unsafe_allow_html=True,
    )

st.caption(
    "💡 Hacé <b>clic sobre un barrio</b> en el mapa para ver las líneas de transporte que pasan cerca "
    "(o elegilo en la lista de la barra lateral).",
    unsafe_allow_html=True,
)

st.markdown(
    f'<div style="display:flex;gap:24px;margin:8px 0;color:#aeb8cc;font-size:14px;">'
    f'<span><span style="display:inline-block;width:14px;height:14px;background:{COBERTO_COLOR};'
    f'border-radius:2px;margin-right:6px;"></span>Con cobertura</span>'
    f'<span><span style="display:inline-block;width:14px;height:14px;background:{NO_COBERTO_COLOR};'
    f'border-radius:2px;margin-right:6px;"></span>Sin cobertura</span></div>',
    unsafe_allow_html=True,
)

st_folium(m, width="100%", height=650, returned_objects=["last_object_clicked", "last_clicked"], key="acceso_map")

st.subheader("Resumen por partido / comuna")
resumen = (
    ren_centroids.groupby("partido", as_index=False)
    .agg(
        barrios=("id", "count"),
        con_cobertura=("cobertura", "sum"),
        familias=("familias", "sum"),
        familias_cubiertas=("familias", lambda s: s[ren_centroids.loc[s.index, "cobertura"]].sum()),
    )
    .sort_values("con_cobertura", ascending=True)
    .reset_index(drop=True)
)
resumen["sin_cobertura"] = resumen["barrios"] - resumen["con_cobertura"]
resumen["personas_cubiertas"] = resumen["familias_cubiertas"] * 4
resumen.columns = ["Partido / Comuna", "Barrios", "Con cobertura", "Familias", "Fam. cubiertas", "Sin cobertura", "Personas cubiertas"]
resumen = resumen[["Partido / Comuna", "Barrios", "Con cobertura", "Sin cobertura", "Familias", "Fam. cubiertas", "Personas cubiertas"]]

st.dataframe(resumen, width="stretch", hide_index=True)

csv = resumen.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "Descargar resumen (CSV)",
    data=csv,
    file_name="cobertura_renabap_amba.csv",
    mime="text/csv",
)

with st.expander("Sobre los datos y la metodología"):
    st.markdown(
        "**Fuentes:** Barrios populares: [RE-NABAP](https://www.argentina.gob.ar/obras-publicas/sisu/renabap) "
        "(Registro Nacional de Barrios Populares, dataset 2023 filtrado a AMBA: 1.356 barrios, 516.303 familias "
        "aproximadas). Colectivos: [BA Data](https://data.buenosaires.gob.ar) (recorridos y paradas, CC-BY-2.5-AR) + "
        "[Recorridos RMBA](https://datos.transporte.gob.ar/dataset/recorridos-de-lineas-de-transporte-rmba-jn) "
        "(Secretaría de Transporte: nacionales, provinciales y municipales). Subte y ferrocarril: datasets RMBA + "
        "[estaciones de ferrocarril de BA Data](https://data.buenosaires.gob.ar/dataset/juqdkmgo-102)."
    )
    st.markdown(
        "**Metodología:** se considera que un barrio popular tiene *cobertura* cuando algún **vértice de la "
        "frontera** de su polígono queda a ≤ 300 m de al menos una línea activa (colectivo del AMBA completo, "
        "y opcionalmente subte y/o ferrocarril). Se usan los vértices y no el centroide para no perder barrios "
        "alargados (p.ej. Villa Itatí) que bordean una ruta aunque su centroide quede lejos. Las *personas* son una "
        "estimación gruesa: familias × 4 (excluye otras tipologías). El conteo de las líneas de colectivo usa la "
        "geometría completa de los ~1.274 recorridos AMBA."
    )
    st.markdown(
        "**Nota:** esta app mide *proximidad espacial a la red*, no tiempo de viaje ni frecuencia de servicio. "
        "Un barrio puede quedar cerca de una línea y aun así tener mala conexión al centro de la ciudad. "
        "En una próxima etapa se podrán agregar corredores hacia destinos clave (microcentro, intercambiadores) "
        "y tiempos de viaje."
    )