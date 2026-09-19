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
    point_in_polygon,
    renabap_covered_ids,
    lines_near_barrio,
    _sube_source_token,
    load_sube_transactions,
    draw_route,
    draw_subte_stations,
    draw_ffcc_stations,
    routes_to_geojson,
    route_colors,
    _metric_box_html,
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
    SUBE_MONTHLY_FILE,
    SUBE_SOURCE_FILES,
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
def _barrio_bounds(bar_id):
    ren_points = load_renabap_points()
    bpts = ren_points[ren_points["id"] == bar_id]
    if bpts.empty:
        return None
    return [
        [float(bpts["lat"].min()), float(bpts["lon"].min())],
        [float(bpts["lat"].max()), float(bpts["lon"].max())],
    ]


def _find_barrio_at(lat, lon, fc) -> int | None:
    for feature in fc["features"]:
        if point_in_polygon(lat, lon, feature["geometry"]):
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


def _bus_color(r):
    jur = r.get("jurisdiccion")
    if jur in (None, "CABA"):
        color, _ = route_colors(LINE_COLORS.get(r["linea"]))
        return color
    return JUR_COLOR.get(jur, "#7f7f7f")


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
    covered = renabap_covered_ids(show_subte, show_ffcc)
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
        _metric_box_html(
            "Barrios con cobertura",
            f"{_fmt(con_cobertura)}<small>/ {_fmt(total_barrios)}</small>",
            f'<span>a ≤ {RENABAP_RADIUS_M} m de alguna red</span>',
        ),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        _metric_box_html(
            "Barrios sin cobertura",
            f'<span style="color:{NO_COBERTO_COLOR};">{_fmt(sin_cobertura)}</span>',
            '<span>lejos de toda la red considerada</span>',
        ),
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        _metric_box_html(
            "Familias con cobertura",
            f"{_fmt(familias_cubiertas)}<small>fam.</small>",
            f'<span>~ {_fmt(familias_cubiertas * 4)} personas (×4)</span>',
        ),
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        _metric_box_html(
            "% del AMBA conectado",
            f"{_fmt_dec(pct)}<small>%</small>",
            '<span>de los barrios populares analizados</span>',
        ),
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
    bus_routes = routes_df.iloc[np.asarray(lines_near_barrio(bar_id, BARRIO_BUS_RADIUS_M, "bus"))]
    near_subte_idx = set(lines_near_barrio(bar_id, BARRIO_RAIL_RADIUS_M, "subte"))
    near_ffcc_idx = set(lines_near_barrio(bar_id, BARRIO_RAIL_RADIUS_M, "ffcc"))
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

if not bus_routes.empty:
    folium.GeoJson(
        routes_to_geojson(bus_routes, color_func=_bus_color),
        style_function=lambda f: {
            "color": f["properties"].get("color", "#7f7f7f"),
            "weight": bus_weight,
            "opacity": bus_opacity,
        },
        tooltip=GeoJsonTooltip(
            fields=["linea", "ramal", "sentido"],
            aliases=["Línea", "Ramal", "Sentido"],
            localize=True,
        ),
        popup=GeoJsonPopup(
            fields=["linea", "ramal", "sentido", "desde", "hasta"],
            aliases=["Línea", "Ramal", "Sentido", "Desde", "Hasta"],
            localize=True,
            style="font-size:12px;",
        ),
        name="Recorridos de colectivo",
    ).add_to(m)

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
    draw_subte_stations(m, subte_stations)

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
    draw_ffcc_stations(m, ffcc_stations)

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

if bar_id is not None:
    sube_ok = os.path.exists(SUBE_MONTHLY_FILE) or any(os.path.exists(p) for p in SUBE_SOURCE_FILES)
    if sube_ok:
        with st.spinner("Cruzando demanda SUBE de las líneas cercanas..."):
            sube = load_sube_transactions(_sube_source_token())
            near_lineas = list(dict.fromkeys(bus_routes["linea"]))
            sube_near = sube[sube["linea"].isin(near_lineas)] if not sube.empty else pd.DataFrame(columns=["linea", "fecha", "transacciones"])
        if not sube_near.empty:
            last12 = sube_near[sube_near["fecha"] >= sube_near["fecha"].max() - pd.DateOffset(months=11)]
            total_usos = int(last12["transacciones"].sum())
            usos_dia = total_usos / 365.0
            st.markdown(
                _metric_box_html(
                    "Demanda de las líneas a ≤ 500 m",
                    f"{_fmt(total_usos)}<small>usos/12m</small>",
                    f'<span>≈ {_fmt(usos_dia)} usos/día · {len(near_lineas)} línea(s)</span>',
                ),
                unsafe_allow_html=True,
            )
            top = (
                last12.groupby("linea", as_index=False)["transacciones"].sum()
                .sort_values("transacciones", ascending=False).head(10)
                .rename(columns={"linea": "Línea", "transacciones": "Usos (12m)"})
            )
            with st.expander(f"Usos SUBE por línea cerca de {barrio_sel}"):
                st.dataframe(top, width="stretch", hide_index=True)
                csv_top = top.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "Descargar usos por línea (CSV)",
                    data=csv_top,
                    file_name=f"usos_lineas_{bar_id}.csv",
                    mime="text/csv",
                )
            st.caption(
                "La demanda corresponde a las líneas que bordean el barrio (proxy de accesibilidad efectiva), "
                "no a viajes originados en el barrio: es el total AMBA de cada línea."
            )
        else:
            st.info("No hay datos SUBE para las líneas que pasan cerca del barrio seleccionado.")

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
        "[estaciones de ferrocarril de BA Data](https://data.buenosaires.gob.ar/dataset/juqdkmgo-102). "
        "Demanda: transacciones SUBE por línea (Secretaría de Transporte)."
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
        "La *demanda de las líneas a ≤ 500 m* es la suma de los usos SUBE (AMBA) de esas líneas, "
        "un proxy de cuánto transporte circula al borde del barrio. "
        "En una próxima etapa se podrán agregar corredores hacia destinos clave (microcentro, intercambiadores) "
        "y tiempos de viaje."
    )