import copy
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

st.set_page_config(
    page_title="Acceso a la Ciudad AMBA",
    page_icon="🏘️",
    layout="wide",
)

st.markdown(THEME_CSS, unsafe_allow_html=True)

with st.spinner("Cargando datos..."):
    routes_df = load_routes_df()
    ren_centroids_full = load_renabap_centroids()

st.markdown(
    app_header_html(
        "Buenos Aires Data · Secretaría de Transporte",
        "Acceso a la Ciudad desde Barrios Populares",
        "Cobertura de colectivo, subte y ferrocarril y acceso directo al centro en los barrios RE-NABAP del AMBA",
        chips=[
            f"Barrios RE-NABAP <b>{_fmt(len(ren_centroids_full))}</b>",
            f"Red de colectivo <b>{_fmt(len(routes_df))} recorridos</b>",
            f"Umbral de cercanía <b>{_fmt_dec(RENABAP_RADIUS_M)} m</b>",
            f"Acceso directo <b>{CENTER_LABEL}</b>",
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
def _renabap_fc_with_estado(centro_ids: frozenset, perif_ids: frozenset):
    fc = _load_renabap_geojson()
    if fc is None:
        return None
    out = copy.deepcopy(fc)
    for feature in out["features"]:
        eid = feature["properties"].get("id_renabap")
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            eid = None
        if eid in centro_ids:
            estado = "con acceso al centro"
        elif eid in perif_ids:
            estado = "solo periférico"
        else:
            estado = "sin cobertura"
        feature["properties"]["estado"] = estado
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
        "El acceso directo al centro se evalúa con las redes tildadas. "
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
        ["Todos", "Con acceso al centro", "Solo periférico", "Sin cobertura"],
        help=(
            "Con acceso al centro: cerca de la red y con al menos una línea directa "
            f"a {CENTER_LABEL}. Solo periférico: cerca de la red, pero sin línea directa."
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
with st.spinner("Midiendo cobertura y acceso al centro..."):
    profile = barrio_access_profile(RENABAP_RADIUS_M, CENTER_COMUNA_IDS, profile_token)
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
ren_full["personas"] = ren_full["familias"] * 4

ren_centroids = ren_full.copy()
if partido_filter != "Todos":
    ren_centroids = ren_centroids[ren_centroids["partido"] == partido_filter].reset_index(drop=True)
if estado_filter != "Todos":
    estado_col = {
        "Con acceso al centro": "acceso_centro",
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
pct_centro = 100.0 * con_centro / total_barrios if total_barrios else 0.0

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        _metric_box_html(
            "Barrios con acceso al centro",
            f"{_fmt(con_centro)}<small>/ {_fmt(total_barrios)}</small>",
            f'<span>a ≤ {RENABAP_RADIUS_M} m y línea directa a {CENTER_LABEL}</span>',
        ),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        _metric_box_html(
            "Solo cobertura periférica",
            f'<span style="color:{PERIF_COLOR};">{_fmt(solo_perif)}</span>',
            f'<span>{_fmt(fam_perif)} fam. · cerca de la red, sin línea directa al centro</span>',
        ),
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        _metric_box_html(
            "Barrios sin cobertura",
            f'<span style="color:{NO_COBERTO_COLOR};">{_fmt(sin_cob)}</span>',
            '<span>lejos de toda la red considerada</span>',
        ),
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        _metric_box_html(
            "Familias con acceso al centro",
            f"{_fmt(fam_centro)}<small>fam.</small>",
            f'<span>~ {_fmt(fam_centro * 4)} personas (×4) · {_fmt_dec(pct_centro)}% de los barrios</span>',
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
    f"Un barrio cuenta como <b>con acceso al centro</b> cuando la <b>frontera</b> de su polígono cae a "
    f"≤ {RENABAP_RADIUS_M} m de al menos una línea de {red_label} que entra en <b>{CENTER_LABEL}</b>. "
    f"Si está cerca de la red pero ninguna de esas líneas llega al centro, queda como <b>solo periférico</b>. "
    f"El acceso directo no considera transbordos. El conteo usa los vértices del polígono "
    f"(barrios alargados bordean la red aunque su centroide quede lejos).",
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

centro_ids = frozenset(ren_full.loc[ren_full["acceso_centro"], "id"].astype(int))
perif_ids = frozenset(ren_full.loc[ren_full["periferico"], "id"].astype(int))
renabap_fc = _renabap_fc_with_estado(centro_ids, perif_ids)
if renabap_fc is not None:
    def style_fn(feature):
        estado = feature["properties"].get("estado")
        if estado == "con acceso al centro":
            color = CENTER_COLOR
        elif estado == "solo periférico":
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
    f'<span><span style="display:inline-block;width:14px;height:14px;background:{CENTER_COLOR};'
    f'border-radius:2px;margin-right:6px;"></span>Con acceso al centro</span>'
    f'<span><span style="display:inline-block;width:14px;height:14px;background:{PERIF_COLOR};'
    f'border-radius:2px;margin-right:6px;"></span>Solo periférico</span>'
    f'<span><span style="display:inline-block;width:14px;height:14px;background:{NO_COBERTO_COLOR};'
    f'border-radius:2px;margin-right:6px;"></span>Sin cobertura</span></div>',
    unsafe_allow_html=True,
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
            f"<span>{_fmt_dec(share_visible)}% del km cercano (≤{RENABAP_RADIUS_M} m) · no pondera frecuencia</span>",
        ),
        unsafe_allow_html=True,
    )

    det_rows = []
    for _, r in bus_routes.iterrows():
        det_rows.append(
            {
                "Modo": "Colectivo",
                "Línea": r["linea"],
                "Ramal": r.get("recorrido"),
                "Sentido": r.get("sentido"),
                "Km": float(r.get("longitud_m") or 0.0) / 1000.0,
                "Llega al centro": "Sí" if bool(r.get("acceso_centro")) else "No",
            }
        )
    if show_subte and near_subte_idx:
        subte_df = load_subte_lines()
        for pos in sorted(near_subte_idx):
            r = subte_df.iloc[pos]
            det_rows.append(
                {
                    "Modo": "Subte",
                    "Línea": r.get("label"),
                    "Ramal": None,
                    "Sentido": None,
                    "Km": _route_length_m(r["coords"]) / 1000.0,
                    "Llega al centro": "Sí" if subte_center_flags[pos] else "No",
                }
            )
    if show_ffcc and near_ffcc_idx:
        ffcc_df = load_ffcc_lines()
        for pos in sorted(near_ffcc_idx):
            r = ffcc_df.iloc[pos]
            det_rows.append(
                {
                    "Modo": "Ferrocarril",
                    "Línea": r.get("linea"),
                    "Ramal": r.get("descrip"),
                    "Sentido": None,
                    "Km": _route_length_m(r["coords"]) / 1000.0,
                    "Llega al centro": "Sí" if ffcc_center_flags[pos] else "No",
                }
            )
    if det_rows:
        det = pd.DataFrame(det_rows).sort_values(
            ["Llega al centro", "Km"], ascending=[False, False]
        )
        with st.expander(f"Líneas cercanas a {barrio_sel} y acceso al centro"):
            st.dataframe(det, width="stretch", hide_index=True)
            st.caption(
                "Km = longitud del recorrido/variante; el acceso directo no considera transbordos. "
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
resumen = resumen.sort_values("pct_centro", ascending=True).reset_index(drop=True)
resumen.columns = [
    "Partido / Comuna", "Barrios", "Con acceso al centro", "Solo periférico",
    "Sin cobertura", "Familias", "Fam. con acceso al centro", "% con acceso al centro",
]

st.dataframe(resumen, width="stretch", hide_index=True)

csv = resumen.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "Descargar resumen (CSV)",
    data=csv,
    file_name="acceso_centro_renabap_amba.csv",
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
        "**Metodología:** un barrio popular tiene *cobertura* cuando algún **vértice de la frontera** de su "
        f"polígono queda a ≤ {_fmt(RENABAP_RADIUS_M)} m de al menos una línea activa de las redes consideradas "
        "(colectivo del AMBA completo y, según los tildes, subte y/o ferrocarril). Tiene *acceso directo al centro* "
        f"cuando además alguna de esas líneas entra en **{CENTER_LABEL}**. Si tiene cobertura pero ninguna línea "
        "llega al centro, se clasifica como *solo periférico*. Se usan los vértices y no el centroide para no perder "
        "barrios alargados (p.ej. Villa Itatí) que bordean una ruta aunque su centroide quede lejos. Las *personas* "
        "son una estimación gruesa: familias × 4 (excluye otras tipologías). El conteo de las líneas de colectivo usa "
        f"la geometría completa de los {_fmt(len(routes_df))} recorridos AMBA. `km_center` y `share_center` suman la "
        "longitud de las variantes cercanas que llegan al centro y su peso sobre el total cercano: son una medida de "
        "intensidad, no de frecuencia ni de tiempo de viaje. "
        f"Los radios de {_fmt(BARRIO_BUS_RADIUS_M)} m (colectivo) y {_fmt(BARRIO_RAIL_RADIUS_M)} m "
        "(subte/ferrocarril) que filtran las líneas mostradas en el mapa son solo de visualización; "
        f"la cobertura y el acceso al centro se calculan siempre con {_fmt(RENABAP_RADIUS_M)} m desde los vértices."
    )
    st.markdown(
        "**Nota:** esta app mide *proximidad espacial a la red* y *destino directo*, no tiempo de viaje ni "
        "frecuencia. Un barrio puede quedar cerca de una línea que no lo conecta al centro; por eso se distingue el "
        "acceso directo. No se contabilizan transbordos: un barrio *solo periférico* podría llegar al centro "
        f"combinando dos líneas. La *demanda de las líneas a ≤ {BARRIO_BUS_RADIUS_M} m* es la suma de los usos SUBE "
        "(AMBA) de esas líneas, un proxy de cuánto transporte circula al borde del barrio. "
        "En una próxima etapa se podrán agregar frecuencias, tiempos de viaje y transbordos."
    )
