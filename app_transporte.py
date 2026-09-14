import os
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
import folium
from streamlit_folium import st_folium

from data_loaders import (
    ensure_local_data,
    load_geojson,
    load_osm_stops,
    load_subte_lines,
    load_subte_stations,
    load_ffcc_lines,
    load_ffcc_stations,
    load_comunas,
    load_sube_transactions,
    load_sube_daily,
    _load_amba_sources,
    _load_renabap_geojson,
    _sube_source_token,
    _subte_line_color,
    build_stops_table,
    build_routes_table_amba,
    comuna_demand_table,
    stops_near_route,
    route_colors,
    draw_route,
    draw_osm_stops,
    draw_renabap,
    _index_series,
    _metric_box_html,
    _delta_pill_html,
    THEME_CSS,
    STOPS_FILE,
    STOPS_URL,
    ROUTES_FILE,
    ROUTES_URL,
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
    BENCH_NINGUNO,
    BENCH_AMBA,
    _fmt,
    _fmt_dec,
)

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
    stops_fc = load_geojson(STOPS_FILE, STOPS_URL)
    routes_fc = load_geojson(ROUTES_FILE, ROUTES_URL)

stops_df = build_stops_table(stops_fc)
routes_df = build_routes_table_amba(routes_fc, _load_amba_sources())

stop_lineas = set(stops_df["linea"])

sube_token = _sube_source_token()
sube_all = pd.DataFrame()
if os.path.exists(SUBE_MONTHLY_FILE) or any(os.path.exists(p) for p in SUBE_SOURCE_FILES):
    sube_all = load_sube_transactions(sube_token)

col_sel, col_info = st.columns([1, 3])

with col_sel:
    ambito = st.radio("Ámbito", ["AMBA", "CABA"], horizontal=True, key="ambito_sel")
    active_routes = (
        routes_df[routes_df["jurisdiccion"] == "CABA"].reset_index(drop=True)
        if ambito == "CABA"
        else routes_df
    )
    routes_df = active_routes
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
    benchmark = BENCH_NINGUNO
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
                [VISTA_MENSUAL, VISTA_DIA],
                key="vista_sel",
            )
            if vista == VISTA_MENSUAL:
                top_lines = (
                    sube_all.groupby("linea")["transacciones"].sum()
                    .sort_values(ascending=False).head(20)
                )
                bench_opts = [BENCH_NINGUNO, BENCH_AMBA] + [f"Línea {l}" for l in top_lines.index]
                benchmark = st.selectbox("Comparar evolución con", bench_opts, key="bench_sel")
    elif linea == "Todas las líneas":
        show_demanda_comuna = st.checkbox("Demanda estimada por comuna (CABA)", value=False)

if "last_linea" in st.session_state and st.session_state["last_linea"] != linea:
    for key in ("recorrido_sel", "sentido_sel", "vista_sel", "bench_sel"):
        st.session_state.pop(key, None)
if real_linea:
    st.session_state["last_linea"] = linea

if real_linea:
    line_routes = routes_df[routes_df["linea"] == linea]
    if recorrido != "Todos":
        line_routes = line_routes[line_routes["recorrido"] == recorrido]
    if sentido != "Ambos":
        line_routes = line_routes[line_routes["sentido"] == sentido]
    n_paradas = len(stops_df[stops_df["linea"] == linea])
    osm_force = ambito == "AMBA" and n_paradas == 0
else:
    n_paradas = 0
    osm_force = False

osm_match = pd.DataFrame()
if real_linea and (show_osm_stops or osm_force):
    with st.spinner("Filtrando paradas AMBA (OSM)..."):
        osm_stops_all = load_osm_stops()
        lats, lons = [], []
        for _, route_row in line_routes.iterrows():
            for segment in route_row["coords"]:
                lats.extend(float(c[1]) for c in segment)
                lons.extend(float(c[0]) for c in segment)
        osm_match = stops_near_route(osm_stops_all, lats, lons)

line_sube = pd.DataFrame()
line_sube_daily = pd.DataFrame()
if real_linea:
    line_sube = sube_all[sube_all["linea"] == linea]
    if vista == VISTA_DIA and not sube_all.empty:
        line_sube_daily = load_sube_daily(sube_token)
        line_sube_daily = line_sube_daily[line_sube_daily["linea"] == linea]

with col_info:
    if real_linea:
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
        if ambito == "AMBA":
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
    for _, route_row in routes_df.iterrows():
        color = JUR_COLOR.get(route_row.get("jurisdiccion"), "#7f7f7f")
        if route_row.get("jurisdiccion") in (None, "CABA"):
            color, _ = route_colors(LINE_COLORS.get(route_row["linea"]))
        draw_route(
            m,
            route_row["coords_simple"],
            color,
            None,
            weight=2,
            opacity=0.45,
        )

    if ambito == "AMBA":
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
    for _, r in subte_stations.iterrows():
        folium.CircleMarker(
            location=[r["lat"], r["lon"]],
            radius=4,
            color="white",
            fill=True,
            fill_color=_subte_line_color(r["linea"]),
            fill_opacity=0.9,
            tooltip=f"{r['estacion']} · Línea {r['linea']}" if r["estacion"] else f"Subte Línea {r['linea']}",
            popup=folium.Popup(
                f"<b>{r['estacion']}</b><br>Línea {r['linea']}",
                max_width=220,
            ) if r["estacion"] else "",
        ).add_to(m)

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
    for _, r in ffcc_stations.iterrows():
        folium.CircleMarker(
            location=[r["lat"], r["lon"]],
            radius=4,
            color="white",
            fill=True,
            fill_color=FFCC_COLOR,
            fill_opacity=0.9,
            tooltip=f"{r['nombre']} · {r['linea']}" if r["nombre"] else f"Ferrocarril {r['linea']}",
            popup=folium.Popup(
                f"<b>{r['nombre']}</b><br>Línea {r['linea']}",
                max_width=220,
            ) if r["nombre"] else "",
        ).add_to(m)

st_folium(m, width="100%", height=650, returned_objects=[])

if real_linea:
    if line_sube.empty:
        st.info(f"No hay indicadores de transacciones SUBE para la línea {linea}.")
    else:
        color, _ = route_colors(LINE_COLORS.get(linea))

        if vista == VISTA_DIA:
            if line_sube_daily.empty:
                st.info(f"No hay desagregación diaria para la línea {linea}.")
            else:
                st.subheader(f"Usos por tipo de día - Línea {linea}")
                tipo_labels = ["Día hábil", "Sábado", "Domingo"]
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
                    f"(AMBA, últimos 12 meses completos), de {line_sube_daily['fecha'].min():%d/%m/%Y} "
                    f"a {line_sube_daily['fecha'].max():%d/%m/%Y}."
                )
        else:
            st.subheader(f"Transacciones SUBE - Línea {linea}")
            sube_12 = line_sube.tail(12)
            window_min = sube_12["fecha"].min()
            window_max = sube_12["fecha"].max()

            bench_series = None
            bench_label = None
            if benchmark != BENCH_NINGUNO:
                if benchmark == BENCH_AMBA:
                    bench_series = sube_all.groupby("fecha", as_index=False)["transacciones"].sum()
                    bench_label = "Total AMBA"
                else:
                    bench_code = benchmark.split()[-1]
                    if bench_code != linea:
                        bench_series = sube_all[sube_all["linea"] == bench_code][["fecha", "transacciones"]]
                        bench_label = f"Línea {bench_code}"
                if bench_series is not None:
                    bench_series = bench_series[
                        (bench_series["fecha"] >= window_min) & (bench_series["fecha"] <= window_max)
                    ]
                    if bench_series.empty:
                        bench_series = None

            if bench_series is not None and len(bench_series) > 1:
                d_line = _index_series(sube_12[["fecha", "transacciones"]])
                d_bench = _index_series(bench_series[["fecha", "transacciones"]])
                c_line = (
                    alt.Chart(d_line)
                    .mark_line(color=color, point=alt.OverlayMarkDef(color=color, filled=True, size=70, strokeWidth=0))
                    .encode(
                        x=alt.X("fecha:T", title="Mes", axis=alt.Axis(format="%m/%Y", grid=True)),
                        y=alt.Y("idx:Q", title="Índice (base = 100 en el primer mes)"),
                        tooltip=[
                            alt.Tooltip("fecha:T", title="Mes"),
                            alt.Tooltip("transacciones:Q", title=f"Usos {linea}", format="~s"),
                        ],
                    )
                )
                c_bench = (
                    alt.Chart(d_bench)
                    .mark_line(color="#9aa7bd", opacity=0.8, strokeDash=[5, 4])
                    .encode(
                        x=alt.X("fecha:T", title="Mes"),
                        y=alt.Y("idx:Q", title="Índice (base = 100)"),
                        tooltip=[
                            alt.Tooltip("fecha:T", title="Mes"),
                            alt.Tooltip("transacciones:Q", title=f"Usos {bench_label}", format="~s"),
                        ],
                    )
                )
                chart = alt.layer(c_line, c_bench).resolve_scale(y="shared")
                st.altair_chart(chart, width="stretch")
                st.caption(
                    f"Evolución indexada (base 100 = primer mes): Línea {linea} vs {bench_label}. "
                    f"Ambas curvas parten del mismo valor para comparar el ritmo de crecimiento."
                )
            else:
                point = alt.OverlayMarkDef(color=color, filled=True, size=80, strokeWidth=0)
                chart = (
                    alt.Chart(sube_12[["fecha", "transacciones"]].copy())
                    .mark_line(color=color, point=point)
                    .encode(
                        x=alt.X("fecha:T", title="Mes", axis=alt.Axis(format="%m/%Y", grid=True)),
                        y=alt.Y("transacciones:Q", title="Transacciones", axis=alt.Axis(format="~s")),
                    )
                )
                st.altair_chart(chart, width="stretch")
                st.caption(
                    f"Fuente: Secretaría de Transporte (datos.transporte.gob.ar) - "
                    f"transacciones SUBE (usos) por fecha. Usos diarios agregados por mes "
                    f"(AMBA), de {window_min:%m/%Y} a {window_max:%m/%Y}."
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
        "cada trazo. En el modo AMBA, los recorridos provinciales y municipales se "
        "dibujan en un color propio (verde/naranja) y el azul identifica "
        "jurisdicción nacional/CABA."
    )
    st.markdown(
        "**Métricas e interpretación:** *usos* son transbordos de tarjeta SUBE (una validación por "
        "uso, incluye transbordos, no incluye pago en efectivo). La serie es AMBA completo aunque la "
        "línea se elija como CABA. Las métricas de demanda NO están ajustadas por cantidad de "
        "colectivos ni por estacionalidad. "
        "**Usos por km** = total de usos de los últimos 12 meses dividido la longitud del recorrido "
        "seleccionado (ida + vuelta); es una proxy de productividad por corredor. "
        "**Demanda por comuna** es una estimación: se reparte la demanda AMBA de cada línea entre "
        "sus paradas de CABA (proporcional al número de paradas por comuna), no es demanda real por "
        "parada."
    )