import os
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
import folium
from folium.features import GeoJsonTooltip, GeoJsonPopup
from streamlit_folium import st_folium

from data_loaders import (
    ensure_local_data,
    load_stops_df,
    load_routes_df,
    load_osm_stops,
    load_subte_lines,
    load_subte_stations,
    load_ffcc_lines,
    load_ffcc_stations,
    load_comunas,
    load_sube_transactions,
    load_sube_daily,
    _load_renabap_geojson,
    _sube_source_token,
    _subte_line_color,
    comuna_demand_table,
    stops_near_route,
    route_points_latlon,
    route_colors,
    draw_route,
    draw_osm_stops,
    draw_renabap,
    draw_subte_stations,
    draw_ffcc_stations,
    routes_to_geojson,
    _metric_box_html,
    _delta_pill_html,
    THEME_CSS,
    SUBE_MONTHLY_FILE,
    SUBE_SOURCE_FILES,
    AMBA_BUS_BOUNDS,
    OSM_STOP_RADIUS_M,
    CHOROPLETH_BINS,
    JUR_COLOR,
    LINE_COLORS,
    FFCC_COLOR,
    SEL_LINEA,
    VISTA_MENSUAL,
    VISTA_DIA,
    VISTA_SEMANA,
    _fmt,
    _fmt_dec,
)

DIA_SEMANA_ORDER = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DIA_SEMANA_MAP = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}

st.set_page_config(
    page_title="Transporte CABA - Transporte Público",
    page_icon="🚌",
    layout="wide",
)

st.markdown(THEME_CSS, unsafe_allow_html=True)

st.title("Transporte Público AMBA")
st.subheader("Colectivos, ferrocarril y subte - recorridos, paradas y demanda")

data_messages = ensure_local_data()
for message in data_messages:
    st.caption(message)

with st.spinner("Cargando datos de colectivos..."):
    stops_df = load_stops_df()
    routes_df = load_routes_df()

stop_lineas = set(stops_df["linea"])

sube_token = _sube_source_token()
sube_all = pd.DataFrame()
if os.path.exists(SUBE_MONTHLY_FILE) or any(os.path.exists(p) for p in SUBE_SOURCE_FILES):
    sube_all = load_sube_transactions(sube_token)

col_sel, col_info = st.columns([1, 3])

with col_sel:
    JUR_OPTS = ["CABA", "NACIONAL", "PROVINCIAL", "MUNICIPAL"]
    jurs = st.multiselect(
        "Jurisdicciones",
        JUR_OPTS,
        default=JUR_OPTS,
        key="jur_sel",
    )
    st.caption("La demanda SUBE es siempre AMBA completa; este filtro aplica a recorridos y paradas.")
    routes_df = routes_df[routes_df["jurisdiccion"].isin(jurs)].reset_index(drop=True)
    lineas = sorted(set(routes_df["linea"]) | stop_lineas, key=int)

    linea = st.selectbox(
        "Línea de colectivo",
        [SEL_LINEA, "Todas las líneas"] + lineas,
        index=0,
    )
    real_linea = linea not in (SEL_LINEA, "Todas las líneas")

    show_subte = st.checkbox("Subte (CABA)", value=False)
    show_ffcc = st.checkbox("Ferrocarril (AMBA)", value=False)
    show_renabap = st.checkbox("Barrios populares RE-NABAP (AMBA)", value=False)

    recorrido = "Todos"
    sentido = "Ambos"
    show_osm_stops = False
    show_demanda_comuna = False
    vista = VISTA_MENSUAL
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
        if not sube_all.empty:
            vista = st.selectbox(
                "Vista de demanda",
                [VISTA_MENSUAL, VISTA_DIA, VISTA_SEMANA],
                key="vista_sel",
            )
    elif linea == "Todas las líneas":
        show_demanda_comuna = st.checkbox("Demanda estimada por comuna (CABA)", value=False)

if not jurs:
    st.warning("Seleccioná al menos una jurisdicción para ver recorridos.")

if "last_jur" in st.session_state and st.session_state["last_jur"] != jurs:
    for key in ("last_linea", "recorrido_sel", "sentido_sel", "vista_sel"):
        st.session_state.pop(key, None)
if "last_linea" in st.session_state and st.session_state["last_linea"] != linea:
    for key in ("recorrido_sel", "sentido_sel", "vista_sel"):
        st.session_state.pop(key, None)
if real_linea:
    st.session_state["last_linea"] = linea
st.session_state["last_jur"] = jurs

if real_linea:
    line_routes = routes_df[routes_df["linea"] == linea]
    if recorrido != "Todos":
        line_routes = line_routes[line_routes["recorrido"] == recorrido]
    if sentido != "Ambos":
        line_routes = line_routes[line_routes["sentido"] == sentido]
    n_paradas = len(stops_df[stops_df["linea"] == linea])
    osm_force = n_paradas == 0
else:
    n_paradas = 0
    osm_force = False

osm_match = pd.DataFrame()
if real_linea and (show_osm_stops or osm_force):
    with st.spinner("Filtrando paradas AMBA (OSM)..."):
        osm_stops_all = load_osm_stops()
        lats, lons = route_points_latlon(line_routes)
        osm_match = stops_near_route(osm_stops_all, lats, lons)

line_sube = pd.DataFrame()
line_sube_daily = pd.DataFrame()
if real_linea:
    line_sube = sube_all[sube_all["linea"] == linea]
    if vista in (VISTA_DIA, VISTA_SEMANA) and not sube_all.empty:
        line_sube_daily = load_sube_daily(sube_token)
        line_sube_daily = line_sube_daily[line_sube_daily["linea"] == linea]

with col_info:
    if real_linea:
        if line_routes.empty:
            st.warning(
                "La línea seleccionada no tiene recorridos para la jurisdicción elegida."
            )
        total_km = line_routes["longitud_m"].sum() / 1000.0
        caption = (
            f"{n_paradas} paradas (CABA), "
            f"{len(line_routes)} recorridos "
            f"(recorrido {recorrido}, {sentido})."
        )
        if show_osm_stops:
            caption += f" Paradas AMBA (OSM): {len(osm_match)}."
        elif osm_force and not osm_match.empty:
            caption += (
                f" Sin paradas registradas en CABA; {len(osm_match)} paradas "
                f"del conurbano (OSM, ≤{OSM_STOP_RADIUS_M} m del recorrido)."
            )
        st.caption(caption)

        if line_sube.empty:
            k1, k2, k3 = st.columns(3)
            with k1:
                st.markdown(
                    _metric_box_html(
                        f"Recorrido · Línea {linea}",
                        f'{_fmt_dec(total_km)}<small>km</small>',
                        (
                            f'<span>{len(line_routes)} recorrido(s) · '
                            f'{len(osm_match) if osm_force else n_paradas} paradas '
                            f'({"OSM" if osm_force else "CABA"})</span>'
                        ),
                    ),
                    unsafe_allow_html=True,
                )
        else:
            sube_12 = line_sube.tail(12)
            prom_mensual = sube_12["transacciones"].mean()
            total_anual = sube_12["transacciones"].sum()
            ult_mes = sube_12["fecha"].iloc[-1]
            usos_dia = sube_12["transacciones"].iloc[-1] / ult_mes.days_in_month
            usos_km = total_anual / total_km if total_km > 0 else float("nan")

            delta_anual = None
            if len(line_sube) >= 24:
                prev_total = line_sube.iloc[:-12]["transacciones"].sum()
                if prev_total:
                    delta_anual = (total_anual - prev_total) / prev_total * 100.0

            delta_mensual = None
            if len(line_sube) >= 2:
                prev_month = line_sube["transacciones"].iloc[-2]
                if prev_month:
                    last_month = line_sube["transacciones"].iloc[-1]
                    delta_mensual = (last_month - prev_month) / prev_month * 100.0

            delta_anual_mes = None
            if len(line_sube) >= 13:
                prev_year_rows = line_sube[line_sube["fecha"].dt.month == ult_mes.month]
                prev_year_rows = prev_year_rows[prev_year_rows["fecha"].dt.year == ult_mes.year - 1]
                if not prev_year_rows.empty and prev_year_rows["transacciones"].iloc[0]:
                    delta_anual_mes = (
                        (line_sube["transacciones"].iloc[-1] - prev_year_rows["transacciones"].iloc[0])
                        / prev_year_rows["transacciones"].iloc[0] * 100.0
                    )

            k1, k2, k3 = st.columns(3)
            with k1:
                st.markdown(
                    _metric_box_html(
                        f"Recorrido · Línea {linea}",
                        f'{_fmt_dec(total_km)}<small>km</small>',
                        f'<span>Longitud ida + vuelta ({len(line_routes)} recorrido(s))</span>',
                    ),
                    unsafe_allow_html=True,
                )
            with k2:
                st.markdown(
                    _metric_box_html(
                        "Usos por día",
                        f'{_fmt(usos_dia)}<small>usos</small>',
                        f'<span>Prom. de {_fmt(sube_12["transacciones"].iloc[-1])} usos en {ult_mes:%m/%Y}</span>',
                    ),
                    unsafe_allow_html=True,
                )
            with k3:
                st.markdown(
                    _metric_box_html(
                        "Usos por km (anual)",
                        f'{_fmt_dec(usos_km)}<small>usos/km</small>',
                        f'<span>Total 12 meses <span class="num">{_fmt(total_anual)}</span></span>',
                    ),
                    unsafe_allow_html=True,
                )

            badges = (
                f'{_delta_pill_html(delta_anual)}<span style="color:#8b95ab;font-size:13px;">vs año ant.</span> '
                f'{_delta_pill_html(delta_mensual)}<span style="color:#8b95ab;font-size:13px;">vs mes ant.</span> '
                f'{_delta_pill_html(delta_anual_mes)}<span style="color:#8b95ab;font-size:13px;">vs mismo mes año ant.</span>'
            )
            tx_html = _metric_box_html(
                f"Transacciones SUBE · Línea {linea}",
                f'{_fmt(prom_mensual)}<small>prom. mensual</small>',
                (
                    f'<span>Total últimos 12 meses</span>'
                    f'<span class="num">{_fmt(total_anual)}</span>'
                ),
                badges,
            )
            st.markdown(
                f'<div class="tx-detached">{tx_html}</div>',
                unsafe_allow_html=True,
            )
    elif linea == "Todas las líneas":
        total_km = routes_df["longitud_m"].sum() / 1000.0
        caption = (
            f"{len(stops_df)} paradas y {len(routes_df)} recorridos "
            f"para {len(lineas)} líneas ({total_km:,.0f} km acumulados ida+vuelta)."
        )
        if not routes_df.empty:
            cnt = routes_df.groupby("jurisdiccion").size()
            detalle = ", ".join(
                f"{cnt.get(j, 0)} {j.lower()}" for j in ("CABA", "NACIONAL", "PROVINCIAL", "MUNICIPAL")
            )
            caption += f" Por jurisdicción: {detalle}."
        st.caption(caption)
    else:
        st.caption("Seleccioná una línea para ver sus recorridos y paradas, o mostrá todas las líneas.")

m = folium.Map(location=[-34.6037, -58.3816], zoom_start=12)

comuna_demanda = pd.DataFrame()
if linea == "Todas las líneas":
    def _todos_color(r):
        jur = r.get("jurisdiccion")
        if jur in (None, "CABA"):
            color, _ = route_colors(LINE_COLORS.get(r["linea"]))
            return color
        return JUR_COLOR.get(jur, "#7f7f7f")

    folium.GeoJson(
        routes_to_geojson(routes_df, color_func=_todos_color),
        style_function=lambda f: {
            "color": f["properties"].get("color", "#7f7f7f"),
            "weight": 2,
            "opacity": 0.45,
        },
        tooltip=GeoJsonTooltip(
            fields=["linea", "ramal", "sentido"],
            aliases=["Línea", "Recorrido", "Sentido"],
            localize=True,
        ),
        name="Recorridos (Todas las líneas)",
    ).add_to(m)

    if not routes_df.empty:
        mlats, mlons = route_points_latlon(routes_df)
        if mlats:
            m.fit_bounds(
                [[min(mlats), min(mlons)], [max(mlats), max(mlons)]],
                padding=(20, 20),
            )
        else:
            m.fit_bounds(AMBA_BUS_BOUNDS, padding=(0, 0))
    else:
        m.fit_bounds(AMBA_BUS_BOUNDS, padding=(0, 0))

    if show_demanda_comuna:
        with st.spinner("Estimando demanda por comuna..."):
            comunas_fc = load_comunas()
            comuna_demanda = comuna_demand_table(stops_df, sube_all)
        if not comuna_demanda.empty:
            vals = np.linspace(0, 1, CHOROPLETH_BINS + 1)
            thresholds = np.quantile(comuna_demanda["usos"], vals).tolist()
            thresholds = sorted(set(thresholds))
            folium.Choropleth(
                geo_data=comunas_fc,
                data=comuna_demanda[["comuna", "usos"]],
                columns=["comuna", "usos"],
                key_on="feature.properties.comuna",
                fill_color="YlOrRd",
                fill_opacity=0.55,
                line_color="#333333",
                line_weight=1.5,
                threshold_scale=thresholds,
                legend_name="Usos SUBE anuales estimados por comuna",
                name="Demanda estimada por comuna (CABA)",
            ).add_to(m)
        else:
            st.warning("No alcanzaron los datos para estimar la demanda por comuna.")
elif real_linea:
    for _, route_row in line_routes.iterrows():
        color, band = route_colors(LINE_COLORS.get(linea))
        draw_route(
            m,
            route_row["coords"],
            color,
            band,
            tooltip=(
                f"Línea {route_row['linea']} - "
                f"Recorrido {route_row['recorrido']} - {route_row['sentido']}"
            ),
        )

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

    if (show_osm_stops or osm_force) and not osm_match.empty:
        draw_osm_stops(m, osm_match)

    lats, lons = route_points_latlon(line_routes)
    if lats:
        m.fit_bounds(
            [[min(lats), min(lons)], [max(lats), max(lons)]],
            padding=(20, 20),
        )

if show_renabap:
    with st.spinner("Cargando barrios populares RE-NABAP (AMBA)..."):
        renabap_fc = _load_renabap_geojson()
    if renabap_fc is not None:
        draw_renabap(m, renabap_fc)
    else:
        st.warning("No se pudieron cargar los barrios populares RE-NABAP; se omite la capa.")

if show_subte:
    with st.spinner("Dibujando red de subte..."):
        subte_lines = load_subte_lines()
        subte_stations = load_subte_stations()
    for _, r in subte_lines.iterrows():
        subte_color = _subte_line_color(r["label"])
        draw_route(
            m, r["coords"], subte_color, None,
            weight=2.5, opacity=0.75, tooltip=f"Subte - Línea {r['label']}",
        )
    draw_subte_stations(m, subte_stations)

if show_ffcc:
    with st.spinner("Dibujando red ferroviaria..."):
        ffcc_lines = load_ffcc_lines()
        ffcc_stations = load_ffcc_stations()
    for _, r in ffcc_lines.iterrows():
        label = f"Ferrocarril {r['linea']}"
        if r["descrip"]:
            label += f" - {r['descrip']}"
        draw_route(
            m, r["coords"], FFCC_COLOR, None,
            weight=2.5, opacity=0.75, tooltip=label,
        )
    draw_ffcc_stations(m, ffcc_stations)

st_folium(m, width="100%", height=650, returned_objects=[])

if real_linea:
    if line_sube.empty:
        st.info(f"No hay indicadores de transacciones SUBE para la línea {linea}.")
    else:
        color, _ = route_colors(LINE_COLORS.get(linea))

        if vista in (VISTA_DIA, VISTA_SEMANA):
            if line_sube_daily.empty:
                st.info(f"No hay desagregación diaria para la línea {linea}.")
            else:
                if vista == VISTA_DIA:
                    st.subheader(f"Usos por tipo de día - Línea {linea}")
                    tipo_labels = ["Día hábil", "Sábado", "Domingo", "Feriado"]
                    daily_avg = (
                        line_sube_daily.groupby("tipo_dia", as_index=False)["transacciones"].mean()
                    )
                    daily_avg["tipo_dia"] = pd.Categorical(
                        daily_avg["tipo_dia"], categories=tipo_labels, ordered=True
                    )
                    bar = (
                        alt.Chart(daily_avg)
                        .mark_bar(color=color, size=70)
                        .encode(
                            x=alt.X("tipo_dia:N", title="Tipo de día", sort=tipo_labels),
                            y=alt.Y("transacciones:Q", title="Usos promedio por día"),
                            tooltip=[
                                alt.Tooltip("tipo_dia:N", title="Tipo de día"),
                                alt.Tooltip("transacciones:Q", title="Usos/día", format="~s"),
                            ],
                        )
                        .properties(height=340)
                    )
                    st.altair_chart(bar, width="stretch")
                    st.caption(
                        f"Promedio de transacciones SUBE diarias por tipo de día "
                        f"(AMBA, últimos 12 meses completos, feriados nacionales excluidos de los días hábiles), "
                        f"de {line_sube_daily['fecha'].min():%d/%m/%Y} a {line_sube_daily['fecha'].max():%d/%m/%Y}."
                    )
                else:
                    st.subheader(f"Semana tipo - Línea {linea}")
                    daily_avg = line_sube_daily.copy()
                    daily_avg["dia"] = daily_avg["fecha"].dt.dayofweek.map(DIA_SEMANA_MAP)
                    daily_avg = daily_avg.groupby("dia", as_index=False)["transacciones"].mean()
                    daily_avg["dia"] = pd.Categorical(
                        daily_avg["dia"], categories=DIA_SEMANA_ORDER, ordered=True
                    )
                    bar = (
                        alt.Chart(daily_avg)
                        .mark_bar(color=color, size=60)
                        .encode(
                            x=alt.X("dia:N", title="Día de la semana", sort=DIA_SEMANA_ORDER),
                            y=alt.Y("transacciones:Q", title="Usos promedio por día"),
                            tooltip=[
                                alt.Tooltip("dia:N", title="Día"),
                                alt.Tooltip("transacciones:Q", title="Usos/día", format="~s"),
                            ],
                        )
                        .properties(height=340)
                    )
                    st.altair_chart(bar, width="stretch")
                    st.caption(
                        f"Promedio diario por día de la semana (AMBA, últimos 12 meses completos), "
                        f"de {line_sube_daily['fecha'].min():%d/%m/%Y} a {line_sube_daily['fecha'].max():%d/%m/%Y}."
                    )

if not sube_all.empty:
    st.subheader("Ranking de productividad AMBA")
    rk = st.columns(3)
    with rk[0]:
        top_n = st.selectbox("Mostrar", ["10", "20", "50", "Todas"], index=1, key="rank_topn")
    with rk[1]:
        sort_by = st.selectbox(
            "Ordenar por",
            ["usos por km", "usos por día", "usos 12m", "Δ vs año anterior"],
            key="rank_sort",
        )
    with rk[2]:
        jur_opts = ["CABA", "NACIONAL", "PROVINCIAL", "MUNICIPAL"]
        rk_jurs = st.multiselect("Jurisdicción", jur_opts, default=jur_opts, key="rank_jur")

    sube12 = sube_all[sube_all["fecha"] >= sube_all["fecha"].max() - pd.DateOffset(months=11)]
    min12 = sube12["fecha"].min()
    prev = sube_all[(sube_all["fecha"] >= min12 - pd.DateOffset(months=12)) & (sube_all["fecha"] < min12)]
    cur = sube12.groupby("linea", as_index=False)["transacciones"].sum().rename(columns={"transacciones": "usos_12m"})
    prv = prev.groupby("linea", as_index=False)["transacciones"].sum().rename(columns={"transacciones": "usos_prev"})
    km = routes_df.groupby("linea", as_index=False)["longitud_m"].sum().rename(columns={"longitud_m": "km"})
    km["km"] = km["km"] / 1000.0
    jur = routes_df.drop_duplicates("linea")[["linea", "jurisdiccion"]]
    rk_df = cur.merge(prv, on="linea", how="left").merge(km, on="linea").merge(jur, on="linea")
    rk_df = rk_df[rk_df["km"] > 0].copy()
    rk_df["usos_dia"] = rk_df["usos_12m"] / 365.0
    rk_df["usos_km"] = rk_df["usos_12m"] / rk_df["km"]
    rk_df["var_aa"] = np.where(
        rk_df["usos_prev"] > 0,
        100.0 * (rk_df["usos_12m"] - rk_df["usos_prev"]) / rk_df["usos_prev"],
        np.nan,
    )
    rk_df = rk_df[rk_df["jurisdiccion"].isin(rk_jurs)]
    if rk_df.empty:
        st.warning("No hay líneas con datos para los filtros elegidos.")
    else:
        sort_map = {
            "usos por km": "usos_km",
            "usos por día": "usos_dia",
            "usos 12m": "usos_12m",
            "Δ vs año anterior": "var_aa",
        }
        rk_df = rk_df.sort_values(sort_map[sort_by], ascending=False, na_position="last")
        if top_n != "Todas":
            rk_df = rk_df.head(int(top_n)).copy()
        rk_df.insert(0, "puesto", range(1, len(rk_df) + 1))
        disp = rk_df[["puesto", "linea", "jurisdiccion", "km", "usos_12m", "usos_dia", "usos_km", "var_aa"]].copy()
        disp.columns = ["#", "Línea", "Jurisdicción", "Km (ida+vuelta)", "Usos 12m", "Usos/día", "Usos/km (anual)", "Δ vs año ant. (%)"]
        disp["Usos/día"] = disp["Usos/día"].round().astype(int)
        disp["Usos/km (anual)"] = disp["Usos/km (anual)"].round(1)
        disp["Δ vs año ant. (%)"] = disp["Δ vs año ant. (%)"].round(1)
        fmt_cols = {
            "Km (ida+vuelta)": "{:.0f}",
            "Usos 12m": "{:,.0f}",
            "Usos/día": "{:,.0f}",
            "Usos/km (anual)": "{:,.1f}",
            "Δ vs año ant. (%)": "{:,.1f}",
        }
        st.dataframe(disp.style.format(fmt_cols), width="stretch", hide_index=True)
        csv_rank = disp.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Descargar ranking (CSV)",
            data=csv_rank,
            file_name="ranking_productividad_amba.csv",
            mime="text/csv",
        )
        st.caption(
            "Usos 12m: transacciones SUBE (AMBA) de los últimos 12 meses completos. "
            "Usos/día: promedio diario del período (total/365). Usos/km: productividad anual por kilómetro "
            "ida+vuelta (suma de los recorridos de la línea). Δ vs año anterior: variación del total 12m "
            "contra los 12 meses previos."
        )

with st.expander("Sobre los datos"):
    st.markdown(
        "Fuente: [BA Data](https://data.buenosaires.gob.ar) - "
        "[Colectivos: recorridos](https://data.buenosaires.gob.ar/dataset/colectivos-recorridos), "
        "[Colectivos: paradas](https://data.buenosaires.gob.ar/dataset/colectivos-paradas), "
        "[Comunas](https://data.buenosaires.gob.ar/dataset/comunas). "
        "Licencia CC-BY-2.5-AR. "
        "Recorridos del conurbano: [Recorridos de Líneas de Transporte "
        "RMBA](https://datos.transporte.gob.ar/dataset/recorridos-de-lineas-de-transporte-rmba-jn) "
        "(Secretaría de Transporte: jurisdicciones nacional, provincial y municipal); "
        "red de subte y ferrocarril del mismo dataset RMBA más "
        "[estaciones de ferrocarril de BA Data](https://data.buenosaires.gob.ar/dataset/juqdkmgo-102). "
        "Barrios populares: [RE-NABAP](https://www.argentina.gob.ar/obras-publicas/sisu/renabap) "
        "(Registro Nacional de Barrios Populares, dataset 2023 filtrado a AMBA). "
        "Paradas del conurbano: [OpenStreetMap](https://www.openstreetmap.org) "
        "(paradas de colectivo descargadas vía Overpass, filtradas por proximidad al recorrido). "
        "Transacciones SUBE: [Secretaría de Transporte](https://datos.transporte.gob.ar) - "
        "[Cantidad de transacciones SUBE (usos) por fecha](https://datos.transporte.gob.ar/dataset/sube-cantidad-de-transacciones-usos-por-fecha) "
        "(usos diarios por línea en AMBA, agregados mensualmente). "
        "Los recorridos se colorean según la librea definida por línea (colores cargados "
        "manualmente); el sentido se indica en el tooltip de "
        "cada trazo. Los recorridos provinciales y municipales se "
        "dibujan en un color propio (verde/naranja) y el azul identifica "
        "jurisdicción nacional/CABA."
    )
    st.markdown(
        "**Métricas e interpretación:** *usos* son transbordos de tarjeta SUBE (una validación por "
        "uso, incluye transbordos, no incluye pago en efectivo). La serie es AMBA completo "
        "independientemente del filtro de jurisdicciones. Las métricas de demanda NO están ajustadas por cantidad de "
        "colectivos ni por estacionalidad. "
        "**Usos por km** = total de usos de los últimos 12 meses dividido la longitud del recorrido "
        "seleccionado (ida + vuelta); es una proxy de productividad por corredor. "
        "**Demanda por comuna** es una estimación: se reparte la demanda AMBA de cada línea entre "
        "sus paradas de CABA (proporcional al número de paradas por comuna), no es demanda real por "
        "parada."
    )