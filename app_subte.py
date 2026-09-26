import calendar
import math

import altair as alt
import folium
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from data_loaders import (
    ACCENT,
    ACCENT_SOFT,
    FERIADOS_ARG,
    INK_DIM,
    INK_FAINT,
    NEG_COLOR,
    POS_COLOR,
    RAMP_DELTA,
    RAMP_VIAJES,
    THEME_CSS,
    _clean_label,
    _delta_pill_html,
    _fmt,
    _fmt_dec,
    _metric_box_html,
    _molinetes_source_token,
    _subte_line_color,
    _subte_line_letter,
    app_header_html,
    draw_route,
    load_molinetes,
    load_subte_lines,
    load_subte_stations_geo,
    log_norm,
    make_map,
    marker_outline,
    marker_radius,
    ramp_color,
    ramp_legend_html,
    tema_mapa_selector,
)

LINEA_OPTS = ["A", "B", "C", "D", "E", "H", "PM"]
LINEA_LABEL = {l: ("Premetro (PM)" if l == "PM" else f"Línea {l}") for l in LINEA_OPTS}
MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

COL_VIAJES = "Viajes del período"
COL_DELTA = "Δ vs año anterior"
N_TOP = 15

st.set_page_config(
    page_title="Transporte CABA - Viajes por molinete",
    page_icon="\U0001F687",
    layout="wide",
)

st.markdown(THEME_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Períodos y agregados
# ---------------------------------------------------------------------------
def _window(year: int, month: int | None = None):
    if month:
        start = pd.Timestamp(year, month, 1)
        end = start.to_period("M").to_timestamp("M")
    else:
        start = pd.Timestamp(year, 1, 1)
        end = pd.Timestamp(year + 1, 1, 1) - pd.Timedelta(days=1)
    return start, end


def _clamp_end(mol, start, end, year: int) -> pd.Timestamp:
    ymax = mol.loc[mol["fecha"].dt.year == year, "fecha"].max()
    if not pd.isna(ymax) and ymax < end:
        return ymax
    return end


def _filter_window(mol, start, end, h0, h1, lineas) -> pd.DataFrame:
    m = mol[(mol["fecha"] >= start) & (mol["fecha"] <= end)]
    m = m[(m["hora"] >= h0) & (m["hora"] <= h1)]
    if lineas:
        m = m[m["linea"].isin(lineas)]
    return m


def _weekday_avg(mol, start, end, lineas) -> pd.DataFrame:
    m = mol[(mol["fecha"] >= start) & (mol["fecha"] <= end)]
    if lineas:
        m = m[m["linea"].isin(lineas)]
    m = m.copy()
    m["dow"] = m["fecha"].dt.dayofweek
    m["fer"] = m["fecha"].dt.strftime("%Y-%m-%d").isin(FERIADOS_ARG)
    m = m[(m["dow"] < 5) & (~m["fer"])]
    if m.empty:
        return pd.DataFrame(columns=["linea", "estacion", "hora", "promedio"]), 0
    ndays = m["fecha"].nunique()
    per = m.groupby(["linea", "estacion", "hora"], as_index=False)["viajes"].sum()
    per["promedio"] = per["viajes"] / ndays
    return per, ndays


@st.cache_data(show_spinner=False)
def _perfil_horario(token: str, start, end, lineas: tuple):
    """Perfil de día hábil promedio. Cacheado: recalcularlo cuesta ~1 s sobre
    1,4M de filas (incluye un `.dt.strftime()` denso) y se recalcula en cada
    rerun del slider."""
    return _weekday_avg(load_molinetes(token), start, end, list(lineas))


@st.cache_data(show_spinner=False)
def _agregado_ventana(token: str, start, end, h0, h1, lineas: tuple) -> dict:
    """Totales y desagregados de una ventana (período + franja + líneas)."""
    mol = load_molinetes(token)
    m = _filter_window(mol, start, end, h0, h1, list(lineas))
    por_est = pd.DataFrame(columns=["linea", "estacion", "viajes"])
    por_linea = pd.DataFrame(columns=["linea", "viajes"])
    if m.empty:
        return {"total": 0, "por_est": por_est, "por_linea": por_linea, "max_por_mes": pd.Series(dtype="datetime64[ns]")}
    return {
        "total": int(m["viajes"].sum()),
        "por_est": m.groupby(["linea", "estacion"], as_index=False)["viajes"].sum(),
        "por_linea": m.groupby("linea", as_index=False)["viajes"].sum(),
        "max_por_mes": m.groupby(m["fecha"].dt.month)["fecha"].max(),
    }


@st.cache_data(show_spinner=False)
def _agregado_mes(token: str, year: int, month: int, h0, h1, lineas: tuple) -> dict:
    """Lo mismo que `_agregado_ventana` pero acotado a un mes calendario."""
    start, end = _window(year, month)
    end = _clamp_end(load_molinetes(token), start, end, year)
    return _agregado_ventana(token, start, end, h0, h1, lineas)


@st.cache_data(show_spinner=False)
def _estaciones_con_coordenadas(stations_df: pd.DataFrame, stations_geo: pd.DataFrame) -> pd.DataFrame:
    """Cruza los viajes por estación con las coordenadas del geojson oficial.

    El cruce es por (estación, línea) y no por nombre solo: hay estaciones
    homónimas en líneas distintas (Callao y Pueyrredón en B y D, Independencia
    en C y E) con coordenadas propias, y por nombre se ubicarían en la traza
    de la línea equivocada. El fallback por nombre se usa únicamente cuando ese
    nombre pertenece a una sola línea del geojson.
    """
    if stations_df.empty:
        return stations_df.assign(lat=np.nan, lon=np.nan)
    por_nombre = stations_geo.groupby("nombre")["linea"].nunique()
    geo_by_name = (
        stations_geo[stations_geo["nombre"].isin(set(por_nombre[por_nombre == 1].index))]
        .drop_duplicates("nombre")
        .set_index("nombre")[["lat", "lon"]]
    )
    out = stations_df.merge(stations_geo.rename(columns={"nombre": "estacion"}), on=["estacion", "linea"], how="left")
    miss = out["lat"].isna() & out["estacion"].isin(geo_by_name.index)
    if miss.any():
        out.loc[miss, "lat"] = out.loc[miss, "estacion"].map(geo_by_name["lat"])
        out.loc[miss, "lon"] = out.loc[miss, "estacion"].map(geo_by_name["lon"])
    out = out.dropna(subset=["lat", "lon"])
    return out[~out["estacion"].isin(["", "null"])]


def _peak_window(profile_series: pd.Series) -> tuple:
    best_h, best_v = -1, -1.0
    for h in range(23):
        v = float(profile_series.get(h, 0) + profile_series.get(h + 1, 0))
        if v > best_v:
            best_v, best_h = v, h
    return best_h, best_v


def _peak_windows(profile_series: pd.Series) -> tuple:
    day_total = float(profile_series.sum())
    manana = profile_series[profile_series.index < 12]
    tarde = profile_series[profile_series.index >= 12]
    (am_h, am_v), (pm_h, pm_v) = _peak_window(manana), _peak_window(tarde)
    am_share = (max(am_v, 0.0) / day_total * 100.0) if day_total > 0 else 0.0
    pm_share = (max(pm_v, 0.0) / day_total * 100.0) if day_total > 0 else 0.0
    return (am_h, am_v, am_share), (pm_h, pm_v, pm_share)


def _peak_str(h: int) -> str:
    return f"{h:02d}:00\u2013{h + 1:02d}:59" if h >= 0 else "s/d"


def _delta_span(pct) -> str:
    if pct is None or (isinstance(pct, float) and pct != pct):
        return f'<span style="color:{INK_FAINT};font-weight:700;">—</span>'
    cls, arrow = (POS_COLOR, "\u25B2") if pct > 0 else ((NEG_COLOR, "\u25BC") if pct < 0 else (INK_DIM, "\u25AC"))
    return f'<span style="color:{cls};font-weight:700;">{arrow} {_fmt_dec(abs(pct))}%</span>'


def _peak_rules(am_h: int, pm_h: int) -> alt.Chart:
    df = pd.DataFrame({"hora": [am_h, pm_h], "Pico": ["Mañana", "Tarde"]})
    return (
        alt.Chart(df)
        .mark_rule(strokeWidth=2, strokeDash=[5, 3])
        .encode(
            x=alt.X("hora:O"),
            color=alt.Color(
                "Pico:N",
                scale=alt.Scale(domain=["Mañana", "Tarde"], range=[POS_COLOR, "#f5a623"]),
                legend=alt.Legend(
                    title=None,
                    orient="top",
                    direction="horizontal",
                    symbolType="stroke",
                    symbolStrokeWidth=10,
                    labelFontSize=11,
                    labelColor=INK_DIM,
                ),
            ),
            tooltip=[alt.Tooltip("Pico:N", title="Pico"), alt.Tooltip("hora:O", title="Comienza")],
        )
    )


def _franja_banda(h0: int, h1: int) -> alt.Chart | None:
    """Franja de horas seleccionada, sombreada detrás de las barras para que el
    slider de la sidebar se vea reflejado en el perfil."""
    if h0 <= 0 and h1 >= 23:
        return None
    fila = {"ini": f"{h0:02d}:00"}
    enc = {"x": alt.X("ini:O", title="Hora")}
    if h1 < 23:
        fila["fin"] = f"{h1 + 1:02d}:00"
        enc["x2"] = "fin:O"
    return alt.Chart(pd.DataFrame([fila])).mark_rect(color=ACCENT, opacity=0.12).encode(**enc)


def _perfil_chart(df: pd.DataFrame, color: str, h0: int, h1: int, am_h: int, pm_h: int, height: int = 270) -> alt.Chart:
    barras = (
        alt.Chart(df)
        .mark_bar(color=color, cornerRadiusEnd=2)
        .encode(
            x=alt.X("hora:O", title="Hora", axis=alt.Axis(labelAngle=0, labelFontSize=11, labelColor=INK_DIM)),
            y=alt.Y("viajes:Q", title=None, axis=alt.Axis(format="~s", labelColor=INK_DIM, gridColor="#242b3b")),
            tooltip=[
                alt.Tooltip("hora:O", title="Hora"),
                alt.Tooltip("viajes:Q", title="Viajes promedio", format=",.0f"),
            ],
        )
        .properties(height=height)
    )
    capas = [c for c in (_franja_banda(h0, h1), barras, _peak_rules(am_h, pm_h)) if c is not None]
    return alt.layer(*capas).properties(height=height)


def _ranking_chart(df: pd.DataFrame, height: int) -> alt.Chart:
    """Barras horizontales del top de estaciones: acompaña al mapa para poder
    comparar posiciones y volúmenes sin depender del color del mapa."""
    orden = df["Estación"].tolist()
    barras = (
        alt.Chart(df)
        .mark_bar(color=ACCENT, height=13, cornerRadiusEnd=3)
        .encode(
            y=alt.Y("Estación:N", sort=orden, title=None, axis=alt.Axis(labelFontSize=11.5, labelColor=INK_DIM)),
            x=alt.X("viajes:Q", title=None, axis=alt.Axis(format="~s", grid=False, domain=False, tickSize=0, labelColor=INK_DIM)),
            tooltip=[
                alt.Tooltip("Estación:N", title="Estación"),
                alt.Tooltip("linea_txt:N", title="Línea"),
                alt.Tooltip("viajes:Q", title="Viajes", format=",.0f"),
                alt.Tooltip("share:Q", title="% del total", format=".1f"),
                alt.Tooltip("delta:Q", title=f"Δ vs año ant.", format="+.1f"),
            ],
        )
    )
    textos = (
        alt.Chart(df)
        .mark_text(align="left", dx=5, color=INK_DIM, fontSize=11, fontWeight="bold")
        .encode(
            y=alt.Y("Estación:N", sort=orden, title=None),
            x=alt.X("viajes:Q", title=None),
            text=alt.Text("txt:N"),
        )
    )
    return (barras + textos).properties(height=height)


def _kpi(label, value_html, sub_html="", badges_html="") -> None:
    st.markdown(_metric_box_html(label, value_html, sub_html, badges_html), unsafe_allow_html=True)


def _dominio_color(vals: pd.Series, q_lo: float = 0.05, q_hi: float = 0.95) -> tuple:
    """Dominio de la escala de color por percentiles.

    Los viajes por estación tienen una cola larguísima (el máximo multiplica
    por ~9 a la mediana y hay estaciones casi vacías), así que un dominio
    [mínimo, máximo] deja a la mitad de las estaciones entre el 28% y el 51%
    de la rampa. Recortar en percentiles 5/95 pone la mediana en el centro de
    la escala; las estaciones fuera del rango comparten el extremo (y la
    leyenda lo dice).
    """
    v = vals[vals > 0]
    if v.empty:
        return 1.0, 1.0, 0, 0
    lo = float(v.quantile(q_lo))
    hi = float(v.quantile(q_hi))
    if hi <= lo:
        hi = lo * 10.0
    return lo, hi, int((v < lo).sum()), int((v > hi).sum())


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
with st.spinner("Cargando datos de molinetes..."):
    mol = load_molinetes(_molinetes_source_token())

if mol.empty:
    st.error("No se pudieron cargar los datos de molinetes (SBASE). Verificá la conexión o los archivos en data/molinetes/.")
    st.stop()

years = sorted(int(y) for y in mol["fecha"].dt.year.unique())
years_base = [y for y in years if y - 1 in years]
if not years_base:
    st.info(f"Datos disponibles: {years}. Se necesitan al menos 2 años para comparar.")
    st.stop()
default_year = 2025 if 2025 in years_base else years_base[-1]
token = _molinetes_source_token()

# ---------------------------------------------------------------------------
# Sidebar: período y líneas
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Período")
    base_year = st.selectbox("Año base", years_base, index=years_base.index(default_year))
    ref_year = base_year - 1
    vista = st.radio("Período", ["Año completo", "Mes"], index=0)
    es_mes = vista == "Mes"
    es_anio = not es_mes
    mes_sel = None
    if es_mes:
        meses_anio = sorted(int(m) for m in mol.loc[mol["fecha"].dt.year == base_year, "fecha"].dt.month.unique())
        if not meses_anio:
            st.info(f"El año {base_year} no tiene datos de mes.")
            st.stop()
        mes_sel = st.selectbox("Mes", meses_anio, format_func=lambda m: MESES_ES.get(m, calendar.month_name[m]))

    st.markdown("### Líneas")
    lineas = st.multiselect(
        "Líneas de subte",
        LINEA_OPTS,
        default=list(LINEA_OPTS),
        format_func=lambda l: LINEA_LABEL[l],
    )
    if not lineas:
        st.warning("Sin líneas seleccionadas no hay datos que mostrar.")
        st.stop()

# ---------------------------------------------------------------------------
# Ventanas del período y perfil de día hábil (para detectar los picos)
# ---------------------------------------------------------------------------
if es_mes:
    b_start, b_end = _window(base_year, mes_sel)
else:
    b_start, b_end = _window(base_year)
b_end = _clamp_end(mol, b_start, b_end, base_year)
r_start = b_start - pd.DateOffset(years=1)
r_end = b_end - pd.DateOffset(years=1)
año_parcial = b_end < _window(base_year)[1]

with st.spinner("Calculando perfiles horarios..."):
    per_file, ndays = _perfil_horario(token, b_start, b_end, tuple(lineas))
per_net = per_file.groupby("hora", as_index=False)["promedio"].sum()
(peak_am_h, peak_am_v, peak_am_share), (peak_pm_h, peak_pm_v, peak_pm_share) = _peak_windows(
    per_net.set_index("hora")["promedio"]
)

# ---------------------------------------------------------------------------
# Sidebar: franja horaria (atajos + slider) y capas
# ---------------------------------------------------------------------------
def _set_horas(h0: int, h1: int):
    def _cb():
        st.session_state["h_sel"] = (max(0, h0), min(23, max(h1, h0)))
    return _cb


with st.sidebar:
    st.markdown("### Franja horaria")
    atajos = st.columns(3)
    atajos[0].button(
        "Todo el día", on_click=_set_horas(0, 23), help="Sin recorte horario (00:00 a 23:00)", width="stretch"
    )
    atajos[1].button(
        f"AM {peak_am_h:02d}h", on_click=_set_horas(peak_am_h, peak_am_h + 1),
        help=f"Pico mañana: {_peak_str(peak_am_h)}", width="stretch",
    )
    atajos[2].button(
        f"PM {peak_pm_h:02d}h", on_click=_set_horas(peak_pm_h, peak_pm_h + 1),
        help=f"Pico tarde: {_peak_str(peak_pm_h)}", width="stretch",
    )
    st.session_state.setdefault("h_sel", (0, 23))
    h_sel = st.select_slider(
        "Horas aplicadas a totales y mapa",
        options=list(range(24)),
        key="h_sel",
        format_func=lambda h: f"{h:02d}:00",
    )
    # El slider de rango devuelve una tupla; si llega un solo valor (por ejemplo
    # un solo handle movido), se interpreta como "todo el día" en vez de romper.
    h0, h1 = h_sel if isinstance(h_sel, (tuple, list)) else (0, 23)

    st.markdown("### Mapa")
    color_por = st.radio("Colorear estaciones por", [COL_VIAJES, COL_DELTA])
    tema_mapa = tema_mapa_selector()
    ver_etiquetas = st.checkbox("Nombres de las estaciones (top 12)", value=False)

agg_base = _agregado_ventana(token, b_start, b_end, h0, h1, tuple(lineas))
agg_ref = _agregado_ventana(token, r_start, r_end, h0, h1, tuple(lineas))
tot_base, est_base = agg_base["total"], agg_base["por_est"]
tot_ref, est_ref = agg_ref["total"], agg_ref["por_est"]
delta_year = (tot_base - tot_ref) / tot_ref * 100 if tot_ref > 0 else None

# Último mes completo del recorte (vista "Año") o mes anterior (vista "Mes")
mes_sec = mes_sel
month_tot = month_ref = delta_month = None
meses_extra: dict = {}
if es_anio:
    max_por_mes = agg_base["max_por_mes"]
    if not max_por_mes.empty:
        mes_sec = int(max_por_mes.index.max())
        if mes_sec > 1 and max_por_mes.loc[mes_sec].day < calendar.monthrange(base_year, mes_sec)[1]:
            mes_sec -= 1

mes_prev = prev_tot = delta_prev = prev_ref_year = None
if mes_sec is not None:
    agg_mes = _agregado_mes(token, base_year, mes_sec, h0, h1, tuple(lineas))
    agg_mes_ref = _agregado_mes(token, base_year - 1, mes_sec, h0, h1, tuple(lineas))
    month_tot, month_ref = agg_mes["total"], agg_mes_ref["total"]
    delta_month = (month_tot - month_ref) / month_ref * 100 if month_ref > 0 else None
    meses_extra = {"mes_base": agg_mes["por_est"], "mes_ref": agg_mes_ref["por_est"]}
    if es_mes:
        if mes_sel > 1:
            mes_prev, mes_prev_year = mes_sel - 1, base_year
        else:
            mes_prev, mes_prev_year = 12, ref_year
        agg_prev = _agregado_mes(token, mes_prev_year, mes_prev, h0, h1, tuple(lineas))
        agg_prev_ref = _agregado_mes(token, mes_prev_year - 1, mes_prev, h0, h1, tuple(lineas))
        prev_tot = agg_prev["total"]
        prev_ref = agg_prev_ref["total"]
        delta_prev = (prev_tot - prev_ref) / prev_ref * 100 if prev_ref > 0 else None
        prev_ref_year = mes_prev_year - 1

stations_df = est_base.merge(est_ref.rename(columns={"viajes": "ref"}), on=["linea", "estacion"], how="outer")
if "mes_base" in meses_extra:
    stations_df = stations_df.merge(
        meses_extra["mes_base"].rename(columns={"viajes": "viajes_m"}), on=["linea", "estacion"], how="left"
    )
    stations_df = stations_df.merge(
        meses_extra["mes_ref"].rename(columns={"viajes": "ref_m"}), on=["linea", "estacion"], how="left"
    )
stations_df["delta_year"] = np.where(
    stations_df["ref"] > 0,
    (stations_df["viajes"] - stations_df["ref"]) / stations_df["ref"] * 100,
    np.nan,
)
if "ref_m" in stations_df.columns:
    stations_df["delta_month"] = np.where(
        stations_df["ref_m"] > 0,
        (stations_df["viajes_m"] - stations_df["ref_m"]) / stations_df["ref_m"] * 100,
        np.nan,
    )
for col in ("viajes", "ref", "viajes_m", "ref_m"):
    if col in stations_df.columns:
        stations_df[col] = stations_df[col].fillna(0)

stations_geo = load_subte_stations_geo()
merged = _estaciones_con_coordenadas(stations_df, stations_geo)

with st.sidebar:
    st.markdown("### Explorar")
    combos = (
        merged[["estacion", "linea"]].drop_duplicates().sort_values(["estacion", "linea"])
        if not merged.empty
        else pd.DataFrame(columns=["estacion", "linea"])
    )
    combo_labels = {
        f"{_clean_label(r.estacion)} · Línea {_clean_label(r.linea)}": (r.estacion, r.linea)
        for r in combos.itertuples()
    }
    if combo_labels:
        sel_label = st.selectbox("Estación", list(combo_labels), key="expl_station")
        sel_station, sel_line = combo_labels[sel_label]
    else:
        st.info("No hay estaciones con datos en esta vista.")
        st.stop()

# ---------------------------------------------------------------------------
# Encabezado con el estado de los filtros
# ---------------------------------------------------------------------------
periodo_txt = f"{MESES_ES[mes_sel]} {base_year}" if es_mes else str(base_year)
lineas_txt = ", ".join(LINEA_LABEL[l] for l in lineas) if len(lineas) < len(LINEA_OPTS) else "Todas"
franja_txt = "todo el día" if (h0 == 0 and h1 == 23) else f"{h0:02d}:00–{h1:02d}:00"
st.markdown(
    app_header_html(
        "SBASE · Buenos Aires Data",
        "Subte CABA · Viajes por molinete",
        "Pasajeros por estación, hora pico y evolución interanual",
        chips=[
            f"Período <b>{periodo_txt}</b>",
            f"Franja <b>{franja_txt}</b>",
            f"Líneas <b>{lineas_txt}</b>",
            f"Estaciones <b>{len(merged)}</b> con coordenadas",
        ],
    ),
    unsafe_allow_html=True,
)
if es_anio and año_parcial:
    st.caption(
        f"El año {base_year} es parcial (datos hasta {b_end:%d/%m/%Y}); la comparación usa el mismo "
        "recorte del año anterior."
    )

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
with k1:
    _kpi(
        f"Viajes · {periodo_txt}",
        f"{_fmt(tot_base)}",
        f"<span>Franja {franja_txt}</span>",
        f'{_delta_pill_html(delta_year)}<span style="color:{INK_FAINT};font-size:13px;">vs {ref_year}</span>',
    )
with k2:
    if es_anio:
        m_label = f"{MESES_ES[mes_sec]} {base_year}" if mes_sec is not None else None
        _kpi(
            "Último mes completo",
            _fmt(month_tot) if mes_sec is not None else "—",
            f"<span>{m_label or 'Sin mes completo'}</span>",
            f'{_delta_pill_html(delta_month)}<span style="color:{INK_FAINT};font-size:13px;">vs {ref_year}</span>'
            if mes_sec is not None else "",
        )
    else:
        _kpi(
            f"Mes anterior · {MESES_ES[mes_prev]} {mes_prev_year}",
            _fmt(prev_tot),
            f"<span>Franja {franja_txt}</span>",
            f'{_delta_pill_html(delta_prev)}<span style="color:{INK_FAINT};font-size:13px;">vs {prev_ref_year}</span>',
        )
with k3:
    _kpi(
        "Pico mañana",
        f"{peak_am_h:02d}:00<small>–{peak_am_h + 1:02d}:59</small>" if peak_am_h >= 0 else "s/d",
        "<span>Viajes/día hábil</span>" + f'<span class="num">{_fmt(peak_am_v)}</span>',
        f'<span class="delta-pill flat">{_fmt_dec(peak_am_share)}% del día</span>',
    )
with k4:
    _kpi(
        "Pico tarde",
        f"{peak_pm_h:02d}:00<small>–{peak_pm_h + 1:02d}:59</small>" if peak_pm_h >= 0 else "s/d",
        "<span>Viajes/día hábil</span>" + f'<span class="num">{_fmt(peak_pm_v)}</span>',
        f'<span class="delta-pill flat">{_fmt_dec(peak_pm_share)}% del día</span>',
    )

# ---------------------------------------------------------------------------
# Mapa + ranking
# ---------------------------------------------------------------------------
vals = stations_df["viajes"].clip(lower=0)
vmin, vmax, n_bajo, n_alto = _dominio_color(vals)

dy_all = stations_df["delta_year"].abs()
dmax = float(dy_all.max()) if dy_all.notna().any() else 0.0
dmax = min(max(dmax, 5.0), 40.0)

m = make_map([-34.6037, -58.3816], zoom_start=12, theme=tema_mapa, control_scale=True)
lines_df = load_subte_lines()
lines_df = lines_df[lines_df["label"].map(_subte_line_letter).isin(lineas)]
for _, r in lines_df.iterrows():
    draw_route(m, r["coords"], _subte_line_color(r["label"]), weight=4, opacity=0.8,
               tooltip=f"Subte - Línea {_subte_line_letter(r['label'])}")

# Picos por estación y línea para el popup
peak_map = {}
for (linea, est), sub in per_file.groupby(["linea", "estacion"]):
    prof = sub.groupby("hora", as_index=False)["promedio"].sum().set_index("hora")["promedio"]
    (am_h, _, _), (pm_h, _, _) = _peak_windows(prof)
    peak_map[(est, linea)] = (am_h, pm_h)

outline = marker_outline(tema_mapa)
n_marcadores = 0
for _, r in merged.iterrows():
    viajes = float(r["viajes"] or 0)
    color_linea = _subte_line_color(r["linea"])
    if color_por == COL_VIAJES:
        fill = ramp_color(RAMP_VIAJES, log_norm(viajes, vmin, vmax))
    else:
        dy = r["delta_year"]
        fill = ramp_color(RAMP_DELTA, 0.5) if pd.isna(dy) else ramp_color(
            RAMP_DELTA, 0.5 + 0.5 * max(-1.0, min(1.0, float(dy) / dmax))
        )
    radius = marker_radius(viajes, vmin, vmax)
    am_h, pm_h = peak_map.get((r["estacion"], r["linea"]), (None, None))
    picos = (
        f"<hr><span style='color:{INK_FAINT};'>Picos día hábil</span><br>"
        f"AM <b>{_peak_str(am_h)}</b> · PM <b>{_peak_str(pm_h)}</b>"
        if am_h is not None else ""
    )
    punto = (
        f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
        f'background:{color_linea};margin-right:6px;"></span>'
    )
    filas = f"<b>{_clean_label(r['estacion'])}</b>{punto}<span style='color:{INK_FAINT};'>Línea {_clean_label(r['linea'])}</span>"
    cuerpo = f"Viajes {periodo_txt}<br><b style='font-size:15px;'>{_fmt(viajes)}</b> {_delta_span(r['delta_year'])}"
    if es_anio and mes_sec is not None:
        cuerpo += f"<br>Mes {MESES_ES.get(mes_sec, mes_sec)}: <b>{_fmt(r.get('viajes_m', 0))}</b> {_delta_span(r.get('delta_month'))}"
    popup_html = f"{filas}<hr>{cuerpo}{picos}"
    folium.CircleMarker(
        location=[r["lat"], r["lon"]],
        radius=radius,
        color=outline,
        weight=1.5,
        fill=True,
        fill_color=fill,
        fill_opacity=0.92,
        tooltip=f"{_clean_label(r['estacion'])} · L{_clean_label(r['linea'])} · {_fmt(viajes)} viajes",
        popup=folium.Popup(popup_html, max_width=290),
    ).add_to(m)
    n_marcadores += 1

if ver_etiquetas and not merged.empty:
    etiquetas = merged.sort_values("viajes", ascending=False).head(12)
    for _, r in etiquetas.iterrows():
        folium.Marker(
            location=[r["lat"], r["lon"]],
            icon=folium.DivIcon(
                icon_size=(1, 1),
                icon_anchor=(-9, 9),
                html=(
                    f'<span style="font-size:10.5px;font-weight:700;color:#f2f5fb;'
                    f'text-shadow:0 0 3px #000,0 0 3px #000,0 1px 2px #000;white-space:nowrap;">'
                    f"{_clean_label(r['estacion'])}</span>"
                ),
            ),
        ).add_to(m)

if not merged.empty:
    m.fit_bounds(
        [[merged["lat"].min(), merged["lon"].min()], [merged["lat"].max(), merged["lon"].max()]],
        padding=(30, 30),
    )
else:
    coords = [c for r in lines_df["coords"] for seg in r for lon, lat in seg]
    if coords:
        m.fit_bounds(
            [[min(c[1] for c in coords), min(c[0] for c in coords)],
             [max(c[1] for c in coords), max(c[0] for c in coords)]],
            padding=(30, 30),
        )

if color_por == COL_VIAJES:
    nota_rango = (
        f"escala logarítmica (percentiles 5–95); {n_bajo} por debajo y {n_alto} por encima "
        "comparten los extremos"
        if (n_bajo or n_alto) else "escala logarítmica (percentiles 5–95)"
    )
    leyenda = ramp_legend_html(
        f"Viajes por estación · {periodo_txt}",
        RAMP_VIAJES,
        labels=[_fmt(vmin), _fmt(math.sqrt(vmin * vmax)) if vmax > vmin else _fmt(vmax), _fmt(vmax)],
        note=f"Franja {franja_txt} · {nota_rango}",
    )
else:
    n_delta_clip = int((dy_all > dmax).sum()) if dy_all.notna().any() else 0
    nota_delta = "El tamaño del círculo sigue siendo el volumen de viajes"
    if n_delta_clip:
        nota_delta += f"; {n_delta_clip} estación/es con |Δ| mayor toman el extremo del color"
    leyenda = ramp_legend_html(
        f"Variación interanual vs {ref_year}",
        RAMP_DELTA,
        labels=[f"-{_fmt_dec(dmax)}%", "0", f"+{_fmt_dec(dmax)}%"],
        note=nota_delta,
    )

# Panel lateral: ranking de estaciones
if merged.empty:
    top = pd.DataFrame(columns=["Estación", "linea_txt", "viajes", "share", "delta", "txt"])
else:
    tot_mapa = float(merged["viajes"].sum()) or 1.0
    top = (
        merged.sort_values("viajes", ascending=False)
        .head(N_TOP)
        .assign(
            Estación=lambda d: d["estacion"].map(_clean_label),
            linea_txt=lambda d: d["linea"].map(lambda l: f"Línea {_clean_label(l)}"),
            share=lambda d: d["viajes"] / tot_mapa * 100,
            delta=lambda d: d["delta_year"],
        )
        .rename(columns={"viajes": "viajes"})[["Estación", "linea_txt", "viajes", "share", "delta"]]
        .copy()
    )
    top["txt"] = top["viajes"].map(_fmt)

col_map, col_rank = st.columns([2.5, 1], gap="medium")
with col_map:
    st_folium(m, width="100%", height=600, returned_objects=[])
    st.markdown(leyenda, unsafe_allow_html=True)
    st.caption(
        f"Color y tamaño de cada estación: {periodo_txt}, franja {franja_txt}. "
        f"{n_marcadores} estaciones con coordenadas; el Premetro y la extensión de la línea H no "
        "tienen geometría en el dataset oficial (sí cuentan en los totales y en la tabla)."
    )
with col_rank:
    if top.empty:
        st.info("No hay estaciones para rankear en esta vista.")
    else:
        st.markdown("**Top estaciones**")
        st.altair_chart(
            _ranking_chart(top, height=max(220, len(top) * 26 + 20)),
            width="stretch",
        )
        st.caption(
            f"Las {len(top)} estaciones con más viajes del período. "
            f"Tamaño del círculo en el mapa: área proporcional al valor (raíz del valor normalizado)."
        )

# ---------------------------------------------------------------------------
# Perfiles horarios
# ---------------------------------------------------------------------------
st.subheader("Perfil horario (día hábil promedio)")
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**Toda la red** · {lineas_txt.lower() if len(lineas) < len(LINEA_OPTS) else 'todas las líneas'}")
    st.altair_chart(
        _perfil_chart(
            per_net.rename(columns={"promedio": "viajes"}), ACCENT, h0, h1, peak_am_h, peak_pm_h
        ),
        width="stretch",
    )
with c2:
    per_st = (
        per_file[(per_file["estacion"] == sel_station) & (per_file["linea"] == sel_line)]
        .groupby("hora", as_index=False)["promedio"].sum()
        .rename(columns={"promedio": "viajes"})
    )
    (ph_am, _, pshare_am), (ph_pm, _, pshare_pm) = _peak_windows(per_st.set_index("hora")["viajes"])
    st.markdown(
        f"**{_clean_label(sel_station)}** · Línea {_clean_label(sel_line)} · pico mañana "
        f"{_peak_str(ph_am)} ({_fmt_dec(pshare_am)}% del día) · pico tarde "
        f"{_peak_str(ph_pm)} ({_fmt_dec(pshare_pm)}% del día)"
    )
    st.altair_chart(
        _perfil_chart(per_st, _subte_line_color(sel_line), h0, h1, ph_am, ph_pm),
        width="stretch",
    )
st.caption(
    "Promedio de pasajeros por hora de los días hábiles (lunes a viernes no feriados) del período "
    "seleccionado, sin aplicar el recorte horario: la franja elegida aparece sombreada y las "
    "líneas punteadas marcan el bloque de 2 horas con más pasajeros de la mañana y de la tarde."
)

# ---------------------------------------------------------------------------
# Tabla de hora pico
# ---------------------------------------------------------------------------
st.subheader("Hora pico por estación")
deltas = stations_df.set_index(["linea", "estacion"])["delta_year"]
peak_rows = []
for (linea, est), sub in per_file.groupby(["linea", "estacion"]):
    prof = sub.groupby("hora", as_index=False)["promedio"].sum().set_index("hora")["promedio"]
    (am_h, am_v, am_share), (pm_h, pm_v, pm_share) = _peak_windows(prof)
    dy = deltas.get((linea, est), np.nan)
    peak_rows.append(
        {
            "Estación": _clean_label(est),
            "Línea": _clean_label(linea) or "s/l",
            "Pico mañana": _peak_str(am_h),
            "Viajes AM": round(float(am_v)),
            "% día AM": round(float(am_share), 1),
            "Pico tarde": _peak_str(pm_h),
            "Viajes PM": round(float(pm_v)),
            "% día PM": round(float(pm_share), 1),
            f"Δ vs {ref_year} (%)": round(float(dy), 1) if dy == dy else np.nan,
        }
    )
peak_table = pd.DataFrame(peak_rows).sort_values("Viajes AM", ascending=False).reset_index(drop=True)

if not peak_table.empty:
    def _barra(v):
        return "background-color: rgba(76,139,245,.16);"

    def _delta_color(v):
        if v is None or (isinstance(v, float) and v != v):
            return ""
        return f"color: {POS_COLOR};" if v > 0 else (f"color: {NEG_COLOR};" if v < 0 else "")

    stylo = (
        peak_table.style.format(
            {"% día AM": "{:.1f}", "% día PM": "{:.1f}", f"Δ vs {ref_year} (%)": "{:+.1f}"}
        )
        .map(_barra, subset=["Viajes AM"])
        .map(_barra, subset=["Viajes PM"])
        .map(_delta_color, subset=[f"Δ vs {ref_year} (%)"])
    )
    st.dataframe(stylo, width="stretch", hide_index=True, height=460)
    st.download_button(
        "Descargar hora pico (CSV)",
        peak_table.to_csv(index=False).encode("utf-8-sig"),
        file_name="subte_hora_pico.csv",
        mime="text/csv",
    )
    st.caption(
        f"Pico = bloque de 2 horas consecutivas con más pasajeros del día hábil promedio, "
        f"detectado por separado para la mañana (00–11) y la tarde (12–23). "
        f"Δ vs {ref_year} compara los viajes de todo el período seleccionado contra el mismo "
        "período del año previo."
    )

# ---------------------------------------------------------------------------
# Sobre los datos
# ---------------------------------------------------------------------------
with st.expander("Sobre los datos"):
    st.markdown(
        f"""
- **Fuente**: SBASE · "Subte: Viajes Molinetes" (Buenos Aires Data, CC-BY-2.5-AR). Datos por
  **molinete, estación y rango de 15 minutos**; aquí se suman a **hora** y se agrega el tipo de
  pasaje (`pax_TOTAL`).
- Años cargados: **{", ".join(str(y) for y in years)}**. {f"{base_year} es parcial (hasta {b_end:%d/%m/%Y})." if año_parcial else ""}
- El **"vs año anterior"** compara el mismo período del año previo (recorte equivalente cuando el
  año es parcial) y aplica los mismos filtros de franja horaria y líneas.
- La **hora pico** se detecta por separado para la **mañana** (horas 00–11) y la **tarde**
  (horas 12–23): en cada franja se elige el **bloque de 2 horas consecutivas** con más pasajeros
  en el promedio de **días hábiles** (lunes a viernes no feriados) del período seleccionado,
  y se informa el **% de los viajes del día** que mueve esa ventana.
- El **color y el tamaño** de los marcadores usan una **escala logarítmica** recortada en los
  percentiles 5 y 95: los viajes están muy concentrados (la estación más cargada multiplica por ~9
  a la mediana) y una escala lineal dejaría a casi todas las estaciones del mismo color. El radio
  es la raíz del valor normalizado, así el *área* del círculo acompaña la escala sin exagerar las
  diferencias. Las estaciones fuera de los percentiles comparten el extremo del color.
- En el modo **"Δ vs año anterior"** el color pasa a ser una escala divergente centrada en 0
  (verde = sube, rojo = baja) y el tamaño sigue siendo el volumen de viajes, para no perder de
  vista el peso de la estación.
- Estaciones del Premetro (linea PM) y de la extensión reciente de la Línea H no tienen
  coordenadas en el dataset oficial y no se muestran en el mapa (sí cuentan en los totales y la tabla).
- Los datos se agregan una sola vez a `data/molinetes_subte.csv` (+ sidecar `molinetes_agg_meta.json`);
  si cambian los zip fuentes se regeneran solos (patrón igual al de los agregados SUBE).
"""
    )

st.caption(
    f"Fuente: SBASE - Buenos Aires Data. Período {b_start:%d/%m/%Y} \u2192 {b_end:%d/%m/%Y} "
    f"({len(mol['fecha'].unique())} días). Franja horaria {h0:02d}:00\u2013{h1:02d}:00 aplicada a totales y mapa. "
    "Mapa base: OpenStreetMap / CARTO."
)
