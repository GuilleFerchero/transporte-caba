import copy
import json
import os
from collections import Counter

import pandas as pd
import numpy as np
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.features import GeoJsonTooltip, GeoJsonPopup

from data_loaders import (
    ensure_local_data,
    BUNDLE_META_FILE,
    load_routes_df,
    load_subte_lines,
    load_subte_stations,
    load_ffcc_lines,
    load_ffcc_stations,
    load_renabap_points,
    load_renabap_centroids,
    _load_renabap_geojson,
    _subte_line_color,
    point_in_polygon,
    barrio_access_profile,
    barrio_line_distances,
    barrio_nearest_center_line,
    route_center_flags,
    access_profile_token,
    _route_length_m,
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
    AMBA_BUS_BOUNDS,
    RENABAP_RADIUS_M,
    CENTER_COMUNA_IDS,
    CENTER_LABEL,
    FAMILIAS_A_PERSONAS,
    JUR_COLOR,
    FFCC_COLOR,
    LINE_COLORS,
    sube_available,
    app_header_html,
    make_map,
    tema_mapa_selector,
    _fmt,
    _fmt_dec,
)

CENTER_COLOR = "#2e9e4b"
PERIF_COLOR = "#e0a400"
NO_COBERTO_COLOR = "#d62728"
BARRIO_BUS_RADIUS_M = 500
BARRIO_RAIL_RADIUS_M = 1200
CENTER_STATE_LABEL = "Línea que toca el centro (sin transbordos)"
RADIUS_OPTIONS = (100, 200, 300, 400, 500, 750, 1000)
DEFAULT_RADIUS_M = RENABAP_RADIUS_M
CENTER_LOOKUP_RADIUS_M = 700
CONTACT_NAME = "Guille Ferchero"
CONTACT_EMAIL = "guilleferchero@gmail.com"
CONTACT_GITHUB = "GuilleFerchero"
CONTACT_GITHUB_URL = f"https://github.com/{CONTACT_GITHUB}"


def _bundle_cut_label() -> str:
    try:
        with open(BUNDLE_META_FILE, encoding="utf-8") as f:
            fecha = json.load(f).get("built_at", "")[:10]
    except (OSError, ValueError):
        fecha = ""
    return f"corte bundle {fecha}" if fecha else "sin fecha de bundle"


st.set_page_config(
    page_title="Acceso a la Ciudad AMBA",
    page_icon="🏘️",
    layout="wide",
)

st.markdown(THEME_CSS, unsafe_allow_html=True)

with st.spinner("Cargando datos..."):
    routes_df = load_routes_df()
    ren_centroids_full = load_renabap_centroids()

with st.sidebar:
    st.markdown("### Escenario de cercanía")
    radius_m = st.select_slider(
        "Radio de cercanía al trazado (escenario)",
        options=RADIUS_OPTIONS,
        value=DEFAULT_RADIUS_M,
        key="acceso_radius_m",
        help=(
            "Cambia la clasificación del mapa y los KPIs. "
            "300 m es la medición de referencia; otros valores son escenarios what-if. "
            "No cambia frecuencias, tiempos de viaje ni transbordos."
        ),
    )
    st.caption(
        f"Escenario activo: ≤ {radius_m} m al trazado. "
        f"Referencia fija: {DEFAULT_RADIUS_M} m."
    )

st.markdown(
    app_header_html(
        "",
        "Acceso a la Ciudad desde Barrios Populares",
        "Cobertura de colectivo, subte y ferrocarril y línea que toca el centro en los barrios RE-NABAP del AMBA",
        chips=[
            f"AMBA total · {_fmt(len(ren_centroids_full))} barrios RE-NABAP",
            f"Red de colectivo <b>{_fmt(len(routes_df))} recorridos</b>",
            f"Escenario activo · <b>≤ {_fmt_dec(radius_m)} m</b>",
            f"Centro: línea que toca <b>{CENTER_LABEL}</b>",
            f"RE-NABAP 2023 · {_bundle_cut_label()}",
        ],
    ),
    unsafe_allow_html=True,
)

for message in ensure_local_data():
    st.caption(message)

with st.sidebar:
    tema_mapa = tema_mapa_selector()


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
def _renabap_fc_with_estado(centro_ids: frozenset, perif_ids: frozenset, centro_info=()):
    fc = _load_renabap_geojson()
    if fc is None:
        return None
    out = copy.deepcopy(fc)
    info = {int(bid): (float(dist), str(linea)) for bid, dist, linea in centro_info}
    for feature in out["features"]:
        eid = feature["properties"].get("id_renabap")
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            eid = None
        if eid in centro_ids:
            estado = f"{CENTER_STATE_LABEL} (comunas {', '.join(str(c) for c in CENTER_COMUNA_IDS)})"
        elif eid in perif_ids:
            estado = "Solo periférico"
        else:
            estado = "Sin cobertura"
        feature["properties"]["estado"] = estado
        dist_linea = info.get(eid)
        feature["properties"]["dist_centro_m"] = (
            int(round(dist_linea[0])) if dist_linea is not None else None
        )
        feature["properties"]["linea_centro"] = dist_linea[1] if dist_linea is not None else None
    return out


def _bus_color(r):
    jur = r.get("jurisdiccion")
    if jur in (None, "CABA"):
        color, _ = route_colors(LINE_COLORS.get(r["linea"]))
        return color
    return JUR_COLOR.get(jur, "#7f7f7f")


with st.sidebar:
    st.markdown("### Redes consideradas")
    st.caption(
        "La cobertura siempre considera todas las líneas de colectivo del AMBA. "
        "La línea que toca el centro se evalúa con las redes tildadas. "
        "En el mapa, el colectivo está oculto por defecto para no saturarlo; "
        "se muestra solo para el barrio seleccionado o tildando esta opción:"
    )
    show_subte = st.checkbox("Subte (CABA)", value=True)
    show_ffcc = st.checkbox("Ferrocarril (AMBA)", value=True)
    show_bus = st.checkbox("Mostrar todas las líneas de colectivo", value=False)

    st.markdown("### Filtro territorial")
    partidos = ["Todos"] + sorted(
        ren_centroids_full["partido"].dropna().unique(),
        key=lambda p: (len(str(p)), str(p)),
    )
    partido_filter = st.selectbox("Partido / Comuna", partidos)

    estado_filter = st.selectbox(
        "Estado de acceso",
        ["Todos", CENTER_STATE_LABEL, "Solo periférico", "Sin cobertura"],
        help=(
            f"{CENTER_STATE_LABEL}: un vértice del barrio está a ≤ {radius_m} m del trazado "
            f"y alguna línea entra en {CENTER_LABEL}. Solo periférico: cerca de la red, pero sin línea al centro."
        ),
    )

    barrio_labels = {}
    barrio_label_of_id = {}
    base_labels = [
        f"{r['barrio']} · {r['partido']}" for _, r in ren_centroids_full.iterrows()
    ]
    label_counts = Counter(base_labels)
    for (_, r), base in zip(ren_centroids_full.iterrows(), base_labels):
        label = base if label_counts[base] == 1 else f"{base} (id {int(r['id'])})"
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

profile_token = access_profile_token()
centro_lookup_radius_m = max(radius_m, CENTER_LOOKUP_RADIUS_M)
with st.spinner("Midiendo cobertura y línea al centro..."):
    profile = barrio_access_profile(radius_m, CENTER_COMUNA_IDS, profile_token)
    centro_lineas = barrio_nearest_center_line(centro_lookup_radius_m, profile_token)
    bus_center_flags, subte_center_flags, ffcc_center_flags = route_center_flags(
        profile_token, CENTER_COMUNA_IDS
    )
    ren_full = load_renabap_centroids().copy()

ren_full["id"] = pd.to_numeric(ren_full["id"], errors="coerce")
ren_full = ren_full.dropna(subset=["id"])
ren_full["id"] = ren_full["id"].astype(int)
ren_full = ren_full.merge(profile, on="id", how="left")
for col in ("bus_near", "bus_center", "subte_near", "subte_center", "ffcc_near", "ffcc_center"):
    ren_full[col] = ren_full[col].fillna(False).astype(bool)
for col in (
    "km_total", "km_center", "share_center", "max_km",
    "km_bus_total", "km_bus_center", "km_subte_total", "km_subte_center",
    "km_ffcc_total", "km_ffcc_center", "max_km_bus", "max_km_subte", "max_km_ffcc",
):
    ren_full[col] = ren_full[col].fillna(0.0)

ren_full["cobertura"] = (
    ren_full["bus_near"]
    | (show_subte & ren_full["subte_near"])
    | (show_ffcc & ren_full["ffcc_near"])
)
ren_full["acceso_centro"] = (
    ren_full["bus_center"]
    | (show_subte & ren_full["subte_center"])
    | (show_ffcc & ren_full["ffcc_center"])
)
ren_full["periferico"] = ren_full["cobertura"] & ~ren_full["acceso_centro"]
ren_full["sin_cobertura"] = ~ren_full["cobertura"]

ren_centroids = ren_full.copy()
if partido_filter != "Todos":
    ren_centroids = ren_centroids[ren_centroids["partido"] == partido_filter].reset_index(drop=True)
if estado_filter != "Todos":
    estado_col = {
        CENTER_STATE_LABEL: "acceso_centro",
        "Solo periférico": "periferico",
        "Sin cobertura": "sin_cobertura",
    }[estado_filter]
    ren_centroids = ren_centroids[ren_centroids[estado_col]].reset_index(drop=True)

if ren_centroids.empty:
    st.warning("No hay barrios populares para el filtro seleccionado.")
    st.stop()

total_barrios = len(ren_centroids)
con_centro = int(ren_centroids["acceso_centro"].sum())
solo_perif = int(ren_centroids["periferico"].sum())
sin_cob = int(ren_centroids["sin_cobertura"].sum())
fam_centro = int(ren_centroids.loc[ren_centroids["acceso_centro"], "familias"].sum())
fam_perif = int(ren_centroids.loc[ren_centroids["periferico"], "familias"].sum())
total_familias = int(ren_centroids["familias"].sum())
pct_centro = 100.0 * con_centro / total_barrios if total_barrios else 0.0
pct_fam_centro = 100.0 * fam_centro / total_familias if total_familias else 0.0

st.caption(
    f"Escenario activo: **≤ {radius_m} m** al trazado. "
    "Cambia la clasificación, no la frecuencia ni el tiempo de viaje."
)

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        _metric_box_html(
            "Barrios con línea al centro",
            f'<span style="color:{CENTER_COLOR};">{_fmt(con_centro)}<small>/ {_fmt(total_barrios)}</small></span>',
            f'<span>vértice a ≤ {radius_m} m del trazado y línea que toca {CENTER_LABEL}</span>',
        ),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        _metric_box_html(
            "Solo cobertura periférica",
            f'<span style="color:{PERIF_COLOR};">{_fmt(solo_perif)}</span>',
            f'<span>{_fmt(fam_perif)} fam. · cerca del trazado, sin línea al centro</span>',
        ),
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        _metric_box_html(
            "Barrios sin cobertura",
            f'<span style="color:{NO_COBERTO_COLOR};">{_fmt(sin_cob)}</span>',
            f'<span>sin red considerada a ≤ {radius_m} m del trazado</span>',
        ),
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        _metric_box_html(
            "Familias con línea al centro",
            f"{_fmt(fam_centro)}<small>fam.</small>",
            f'<span>~ {_fmt(fam_centro * FAMILIAS_A_PERSONAS)} personas '
            f'(×{FAMILIAS_A_PERSONAS}) · {_fmt_dec(pct_centro)}% barrios · '
            f'{_fmt_dec(pct_fam_centro)}% familias</span>',
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
    f"<b>{CENTER_STATE_LABEL}</b>: algún vértice de la frontera cae a ≤ {radius_m} m del <b>trazado</b> "
    f"de una línea de {red_label} que entra en {CENTER_LABEL}. Si está cerca pero ninguna línea toca el centro, es "
    "<b>solo periférico</b>; si no hay red cerca, <b>sin cobertura</b>. "
    "Sin transbordos; km y share son intensidad, no frecuencia.",
    unsafe_allow_html=True,
)

m = make_map([-34.6037, -58.3816], zoom_start=10, theme=tema_mapa)

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

bus_center_series = pd.Series(bus_center_flags, index=routes_df.index, name="acceso_centro")
bus_routes = bus_routes.join(bus_center_series)

dist_bus = {}
dist_subte = {}
dist_ffcc = {}
if bar_id is not None:
    dist_bus = barrio_line_distances(bar_id, BARRIO_BUS_RADIUS_M, "bus", profile_token)
    if show_subte:
        dist_subte = barrio_line_distances(bar_id, BARRIO_RAIL_RADIUS_M, "subte", profile_token)
    if show_ffcc:
        dist_ffcc = barrio_line_distances(bar_id, BARRIO_RAIL_RADIUS_M, "ffcc", profile_token)

centro_ids = frozenset(ren_full.loc[ren_full["acceso_centro"], "id"].astype(int))
perif_ids = frozenset(ren_full.loc[ren_full["periferico"], "id"].astype(int))
centro_info = tuple(
    (int(getattr(r, "id")), float(getattr(r, "dist_m")), str(getattr(r, "linea")))
    for r in centro_lineas.itertuples()
    if pd.notna(getattr(r, "dist_m"))
)
renabap_fc = _renabap_fc_with_estado(centro_ids, perif_ids, centro_info)
if renabap_fc is not None:
    def style_fn(feature):
        estado = feature["properties"].get("estado")
        if estado.startswith(CENTER_STATE_LABEL):
            color = CENTER_COLOR
        elif estado.startswith("Solo periférico"):
            color = PERIF_COLOR
        else:
            color = NO_COBERTO_COLOR
        selected = (
            bar_id is not None
            and str(feature["properties"].get("id_renabap")) == str(bar_id)
        )
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
            fields=["nombre_barrio", "departamento", "estado", "dist_centro_m", "linea_centro"],
            aliases=["Barrio", "Partido", "Estado", "Dist. línea centro (m)", "Línea con centro"],
            localize=True,
        ),
        popup=GeoJsonPopup(
            fields=[
                "nombre_barrio", "departamento", "localidad",
                "familias_aproximadas", "estado", "dist_centro_m",
                "linea_centro", "id_renabap",
            ],
            aliases=[
                "Barrio", "Partido", "Localidad",
                "Familias aprox.", "Estado", "Dist. línea centro (m)",
                "Línea con centro", "ID RE-NABAP",
            ],
            localize=True,
            style="font-size:12.5px; line-height:1.45;",
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
            style="font-size:12.5px; line-height:1.45;",
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
        f"El color del barrio usa ≤ {radius_m} m desde los vértices: lo dibujado es sólo referencia visual. "
        f"Para ver el contexto completo, tildá <i>Mostrar todas las líneas de colectivo</i> "
        f"en la barra lateral.",
        unsafe_allow_html=True,
    )

st.caption(
    "💡 Hacé <b>clic sobre un barrio</b> en el mapa para ver las líneas de transporte que pasan cerca "
    "(o elegilo en la lista de la barra lateral).",
    unsafe_allow_html=True,
)

if show_bus and bar_id is None:
    st.caption(
        "Aviso: se están dibujando todas las líneas de colectivo del AMBA; el mapa puede demorar. "
        "Elegí un barrio o desactivá la opción para aligerarlo."
    )

st.markdown(
    f'<div style="display:flex;gap:24px;margin:8px 0;color:#aeb8cc;font-size:13px;line-height:1.4;">'
    f'<span><span style="display:inline-block;width:14px;height:14px;background:{CENTER_COLOR};'
    f'border-radius:2px;margin-right:6px;"></span>{CENTER_STATE_LABEL}</span>'
    f'<span><span style="display:inline-block;width:14px;height:14px;background:{PERIF_COLOR};'
    f'border-radius:2px;margin-right:6px;"></span>Solo periférico</span>'
    f'<span><span style="display:inline-block;width:14px;height:14px;background:{NO_COBERTO_COLOR};'
    f'border-radius:2px;margin-right:6px;"></span>Sin cobertura</span></div>',
    unsafe_allow_html=True,
)
if radius_m < BARRIO_BUS_RADIUS_M:
    transition_txt = (
        f"la franja {radius_m}–{BARRIO_BUS_RADIUS_M} m es límite/transición y no cambia el estado."
    )
else:
    transition_txt = (
        f"el radio del escenario alcanza o supera los {BARRIO_BUS_RADIUS_M} m de dibujo de colectivo; "
        "el mapa puede no mostrar todas las líneas que justifican el color."
    )
st.caption(
    f"El color es un corte a ≤ {radius_m} m entre los vértices del barrio y el trazado de la red; "
    f"{transition_txt}"
)

st_folium(m, width="100%", height=650, returned_objects=["last_object_clicked", "last_clicked"], key="acceso_map")

if bar_id is not None:
    sube_ok = sube_available()
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
                    f"Demanda SUBE AMBA de las líneas a ≤ {BARRIO_BUS_RADIUS_M} m",
                    f"{_fmt(total_usos)}<small>usos/12m</small>",
                    f'<span>≈ {_fmt(usos_dia)} usos/día · {len(near_lineas)} línea(s) · no del barrio</span>',
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

if bar_id is not None:
    prof = ren_full.loc[ren_full["id"] == bar_id].iloc[0]
    km_centro_visible = float(prof["km_bus_center"])
    km_total_visible = float(prof["km_bus_total"])
    if show_subte:
        km_centro_visible += float(prof["km_subte_center"])
        km_total_visible += float(prof["km_subte_total"])
    if show_ffcc:
        km_centro_visible += float(prof["km_ffcc_center"])
        km_total_visible += float(prof["km_ffcc_total"])
    share_visible = 100.0 * km_centro_visible / km_total_visible if km_total_visible else 0.0
    st.markdown(
        _metric_box_html(
            f"Km de líneas cercanas que llegan a {CENTER_LABEL}",
            f"{_fmt_dec(km_centro_visible)}<small>km</small>",
            f"<span>{_fmt_dec(share_visible)}% del km cercano (≤{radius_m} m) · no pondera frecuencia</span>",
        ),
        unsafe_allow_html=True,
    )

    det_rows = []
    for idx, r in bus_routes.iterrows():
        dist = dist_bus.get(int(idx))
        det_rows.append(
            {
                "Modo": "Colectivo",
                "Línea": r["linea"],
                "Ramal": r.get("recorrido"),
                "Sentido": r.get("sentido"),
                "Distancia (m)": int(round(dist)) if dist is not None else None,
                "Km de variante": float(r.get("longitud_m") or 0.0) / 1000.0,
                "Llega al centro": "Sí" if bool(r.get("acceso_centro")) else "No",
            }
        )
    if show_subte and near_subte_idx:
        subte_df = load_subte_lines()
        for pos in sorted(near_subte_idx):
            r = subte_df.iloc[pos]
            dist = dist_subte.get(pos)
            det_rows.append(
                {
                    "Modo": "Subte",
                    "Línea": r.get("label"),
                    "Ramal": None,
                    "Sentido": None,
                    "Distancia (m)": int(round(dist)) if dist is not None else None,
                    "Km de variante": _route_length_m(r["coords"]) / 1000.0,
                    "Llega al centro": "Sí" if subte_center_flags[pos] else "No",
                }
            )
    if show_ffcc and near_ffcc_idx:
        ffcc_df = load_ffcc_lines()
        for pos in sorted(near_ffcc_idx):
            r = ffcc_df.iloc[pos]
            dist = dist_ffcc.get(pos)
            det_rows.append(
                {
                    "Modo": "Ferrocarril",
                    "Línea": r.get("linea"),
                    "Ramal": r.get("descrip"),
                    "Sentido": None,
                    "Distancia (m)": int(round(dist)) if dist is not None else None,
                    "Km de variante": _route_length_m(r["coords"]) / 1000.0,
                    "Llega al centro": "Sí" if ffcc_center_flags[pos] else "No",
                }
            )
    if det_rows:
        det = pd.DataFrame(det_rows).sort_values(
            ["Llega al centro", "Distancia (m)", "Km de variante"],
            ascending=[False, True, False],
            na_position="last",
        )
        with st.expander(f"Líneas cercanas a {barrio_sel} y línea al centro"):
            dist_min = det["Distancia (m)"].min()
            dist_txt = f"{int(round(dist_min))} m" if pd.notna(dist_min) else "s/d"
            centro_row = centro_lineas[centro_lineas["id"] == bar_id]
            if not centro_row.empty and pd.notna(centro_row.iloc[0]["dist_m"]):
                centro_txt = (
                    f"Colectivo con centro más cercano: {centro_row.iloc[0]['linea']} a "
                    f"{int(round(centro_row.iloc[0]['dist_m']))} m."
                )
            else:
                centro_txt = f"Sin colectivo con centro a ≤ {centro_lookup_radius_m} m."
            st.caption(f"Distancia mínima a la red visible: {dist_txt}. {centro_txt}")
            st.dataframe(
                det,
                width="stretch",
                hide_index=True,
                column_config={
                    "Distancia (m)": st.column_config.NumberColumn(format="%.0f m"),
                    "Km de variante": st.column_config.NumberColumn(format="%.2f"),
                },
            )
            st.caption(
                "Km de variante = longitud del recorrido/variante; la línea al centro no considera transbordos. "
                f"Colectivo a ≤ {BARRIO_BUS_RADIUS_M} m; subte y ferrocarril a ≤ {BARRIO_RAIL_RADIUS_M} m."
            )

st.subheader("Resumen por partido / comuna")
resumen = (
    ren_centroids.groupby("partido", as_index=False)
    .agg(
        barrios=("id", "count"),
        con_centro=("acceso_centro", "sum"),
        solo_perif=("periferico", "sum"),
        sin_cob=("sin_cobertura", "sum"),
        familias=("familias", "sum"),
        fam_centro=("familias", lambda s: s[ren_centroids.loc[s.index, "acceso_centro"]].sum()),
    )
)
resumen["pct_centro"] = 100.0 * resumen["con_centro"] / resumen["barrios"]
resumen["pct_fam_centro"] = 100.0 * resumen["fam_centro"] / resumen["familias"]
resumen = resumen.sort_values("pct_centro", ascending=True).reset_index(drop=True)
resumen = resumen.rename(
    columns={
        "partido": "Partido / Comuna",
        "barrios": "Barrios",
        "con_centro": CENTER_STATE_LABEL,
        "solo_perif": "Solo periférico",
        "sin_cob": "Sin cobertura",
        "familias": "Familias",
        "fam_centro": "Fam. con línea al centro",
        "pct_centro": "% con línea al centro",
        "pct_fam_centro": "% fam. con línea al centro",
    }
)

st.dataframe(resumen, width="stretch", hide_index=True)

csv_df = resumen.copy()
csv_df.insert(0, "Escenario (m)", radius_m)
csv = csv_df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "Descargar resumen (CSV)",
    data=csv,
    file_name=f"acceso_centro_renabap_amba_{radius_m}m.csv",
    mime="text/csv",
)

with st.expander("Sobre los datos y la metodología"):
    st.markdown(
        "**Fuentes:** Barrios populares: [RE-NABAP](https://www.argentina.gob.ar/obras-publicas/sisu/renabap) "
        f"(Registro Nacional de Barrios Populares, dataset 2023 filtrado a AMBA: "
        f"{_fmt(len(ren_centroids_full))} barrios, {_fmt(int(ren_centroids_full['familias'].sum()))} familias "
        "aproximadas). Colectivos: [BA Data](https://data.buenosaires.gob.ar) (recorridos y paradas, CC-BY-2.5-AR) + "
        "[Recorridos RMBA](https://datos.transporte.gob.ar/dataset/recorridos-de-lineas-de-transporte-rmba-jn) "
        "(Secretaría de Transporte: nacionales, provinciales y municipales). Subte y ferrocarril: datasets RMBA + "
        "[estaciones de ferrocarril de BA Data](https://data.buenosaires.gob.ar/dataset/juqdkmgo-102). "
        "Demanda: transacciones SUBE por línea (Secretaría de Transporte)."
    )
    st.markdown(
        "**Metodología:** un barrio popular tiene *cobertura* cuando algún **vértice de la frontera** de su "
        f"polígono queda a ≤ {_fmt(radius_m)} m del <b>trazado</b> de al menos una línea activa de las redes consideradas "
        "(colectivo del AMBA completo y, según los tildes, subte y/o ferrocarril). Tiene *línea que toca el centro* "
        f"cuando además alguna de esas líneas entra en **{CENTER_LABEL}**. Si tiene cobertura pero ninguna línea "
        "llega al centro, se clasifica como *solo periférico*. Se usan los vértices y no el centroide para no perder "
        "barrios alargados (p.ej. Villa Itatí) que bordean una ruta aunque su centroide quede lejos. Las *personas* "
        f"son una estimación gruesa: familias × {FAMILIAS_A_PERSONAS} (excluye otras tipologías). El conteo de las líneas de colectivo usa "
        f"la geometría completa de los {_fmt(len(routes_df))} recorridos AMBA. `km_center` y `share_center` suman la "
        "longitud de las variantes cercanas que llegan al centro y su peso sobre el total cercano: son una medida de "
        "intensidad, no de frecuencia ni de tiempo de viaje. "
        f"Los radios de {_fmt(BARRIO_BUS_RADIUS_M)} m (colectivo) y {_fmt(BARRIO_RAIL_RADIUS_M)} m "
        "(subte/ferrocarril) que filtran las líneas mostradas en el mapa son solo de visualización; "
        f"la cobertura y la línea al centro se calculan siempre con {_fmt(radius_m)} m desde los vértices al trazado. "
        f"{_fmt(DEFAULT_RADIUS_M)} m es la medición de referencia; los demás valores son escenarios what-if, "
        "no una medición oficial. Ninguno modela frecuencia, tiempo de viaje ni transbordos. "
        "Las distancias informadas van de vértices del polígono a puntos de la red (no a tramos), así que son orientativas."
    )
    st.markdown(
        "**Nota:** esta app mide *proximidad espacial al trazado de la red* y *destino directo*, no tiempo de viaje ni "
        "frecuencia. Un barrio puede quedar cerca de una línea que no lo conecta al centro; por eso se distingue el "
        "línea al centro. No se contabilizan transbordos: un barrio *solo periférico* podría llegar al centro "
        f"combinando dos líneas. La *demanda de las líneas a ≤ {BARRIO_BUS_RADIUS_M} m* es la suma de los usos SUBE "
        "(AMBA) de esas líneas, un proxy de cuánto transporte circula al borde del barrio. "
        "En una próxima etapa se podrán agregar frecuencias, tiempos de viaje y transbordos."
    )

with st.sidebar:
    st.markdown("---")
    st.caption(
        f"**Contacto:** {CONTACT_NAME} · "
        f"[email](mailto:{CONTACT_EMAIL}) · [GitHub]({CONTACT_GITHUB_URL})"
    )
