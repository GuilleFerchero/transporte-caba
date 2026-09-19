import calendar
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
import folium
from streamlit_folium import st_folium

from data_loaders import (
    load_molinetes,
    load_subte_lines,
    _molinetes_source_token,
    load_subte_stations_geo,
    _subte_line_color,
    _clean_label,
    draw_route,
    _metric_box_html,
    _delta_pill_html,
    _fmt,
    _fmt_dec,
    THEME_CSS,
    FERIADOS_ARG,
)

LINEA_OPTS = ["A", "B", "C", "D", "E", "H", "PM"]
LINEA_LABEL = {l: ("Premetro (PM)" if l == "PM" else f"Línea {l}") for l in LINEA_OPTS}

st.set_page_config(
    page_title="Transporte CABA - Viajes por molinete",
    page_icon="\U0001F687",
    layout="wide",
)

st.markdown(THEME_CSS, unsafe_allow_html=True)

st.title("Subte CABA - Viajes por molinete")
st.subheader("Pasajeros por estación, hora pico y evolución interanual")


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


def _delta_span(pct) -> str:
    if pct is None or (isinstance(pct, float) and pct != pct):
        return '<span style="color:#8b95ab;font-weight:700;">—</span>'
    cls, arrow = ("#3ddc84", "\u25B2") if pct > 0 else (("#ff7b7b", "\u25BC") if pct < 0 else ("#aeb8cc", "\u25AC"))
    return f'<span style="color:{cls};font-weight:700;">{arrow} {_fmt_dec(abs(pct))}%</span>'


def _scale_color(v, lo, hi):
    t = 0.5 if hi <= lo else max(0.0, min(1.0, (v - lo) / (hi - lo)))
    c1 = (240, 249, 255)
    c2 = (8, 48, 107)
    r, g, b = [int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)]
    return f"#{r:02x}{g:02x}{b:02x}"


def _weekday_avg(mol, start, end, lineas) -> pd.DataFrame:
    m = mol[(mol["fecha"] >= start) & (mol["fecha"] <= end)]
    if lineas:
        m = m[m["linea"].isin(lineas)]
    m = m.copy()
    m["dow"] = m["fecha"].dt.dayofweek
    m["fer"] = m["fecha"].dt.strftime("%Y-%m-%d").isin(FERIADOS_ARG)
    m = m[(m["dow"] < 5) & (~m["fer"])]
    if m.empty:
        return pd.DataFrame(columns=["hora", "viajes"]), 0
    ndays = m["fecha"].nunique()
    per = m.groupby(["estacion", "hora"], as_index=False)["viajes"].sum()
    per["promedio"] = per["viajes"] / ndays
    return per, ndays


def _peak_window(profile_series: pd.Series) -> tuple:
    total = float(profile_series.sum())
    best_h, best_v = -1, -1.0
    for h in range(23):
        v = float(profile_series.get(h, 0) + profile_series.get(h + 1, 0))
        if v > best_v:
            best_v, best_h = v, h
    share = (best_v / total * 100.0) if total > 0 else 0.0
    return best_h, best_v, share


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

st.sidebar.header("Filtros")
base_year = st.sidebar.selectbox("Año base", years_base, index=years_base.index(default_year))
ref_year = base_year - 1

vista = st.sidebar.radio("Período", ["Año completo", "Mes"], index=0)
mes_sel = None
if vista == "Mes":
    meses_anio = sorted(int(m) for m in mol.loc[mol["fecha"].dt.year == base_year, "fecha"].dt.month.unique())
    if not meses_anio:
        st.info(f"El año {base_year} no tiene datos de mes.")
        st.stop()
    mes_sel = st.sidebar.selectbox("Mes", meses_anio, format_func=lambda m: calendar.month_name[m])

h_sel = st.sidebar.select_slider(
    "Franja horaria",
    options=list(range(24)),
    value=(0, 23),
    format_func=lambda h: f"{h:02d}:00",
)
h0, h1 = h_sel

lineas = st.sidebar.multiselect(
    "Líneas",
    LINEA_OPTS,
    default=list(LINEA_OPTS),
    format_func=lambda l: LINEA_LABEL[l],
)
if not lineas:
    st.sidebar.warning("Sin líneas seleccionadas no hay datos que mostrar.")
    st.stop()

if vista == "Mes":
    b_start, b_end = _window(base_year, mes_sel)
else:
    b_start, b_end = _window(base_year)
b_end = _clamp_end(mol, b_start, b_end, base_year)
r_start = b_start - pd.DateOffset(years=1)
r_end = b_end - pd.DateOffset(years=1)

año_parcial = b_end < _window(base_year)[1]
if vista == "Año" and año_parcial:
    st.caption(
        f"El año {base_year} es parcial (datos hasta {b_end:%d/%m/%Y}); la comparación usa el mismo "
        "recorte del año anterior."
    )
elif base_year == ref_year + 1 and not año_parcial:
    st.caption(f"Año {base_year} completo comparado contra el mismo período de {ref_year}.")

# Perfiles horarios (día hábil promedio, ventana sin filtro de horas para no achicar la curva)
per_file, ndays = _weekday_avg(mol, b_start, b_end, lineas)
per_net = per_file.groupby("hora", as_index=False)["promedio"].sum()
peak_net_h, peak_net_v, peak_net_share = _peak_window(per_net.set_index("hora")["promedio"])

# Totales por estación (con filtros de horas y líneas) y su Δ anual
mb = _filter_window(mol, b_start, b_end, h0, h1, lineas)
mr = _filter_window(mol, r_start, r_end, h0, h1, lineas)
tot_base = int(mb["viajes"].sum())
tot_ref = int(mr["viajes"].sum())
delta_year = (tot_base - tot_ref) / tot_ref * 100 if tot_ref > 0 else None

# Último mes completo del recorte (para la 2ª comparación)
mes_sec_year = base_year
if vista == "Año":
    mm = mb["fecha"].dt.month
    last_m = int(mm.max()) if not mb.empty else None
    if last_m is not None:
        days = set(mb.loc[mb["fecha"].dt.month == last_m, "fecha"].dt.day)
        if days and max(days) < calendar.monthrange(base_year, last_m)[1] and last_m > 1:
            last_m -= 1
    mes_sec = last_m
else:
    mes_sec = mes_sel

if mes_sec is None:
    month_tot = None
    month_ref = None
    delta_month = None
    ms = pd.DataFrame(columns=["fecha", "hora", "linea", "estacion", "viajes"])
    msr = ms
else:
    ms_start, ms_end = _window(mes_sec_year, mes_sec)
    ms_end = _clamp_end(mol, ms_start, ms_end, mes_sec_year)
    ms = _filter_window(mol, ms_start, ms_end, h0, h1, lineas)
    msr = _filter_window(mol, ms_start - pd.DateOffset(years=1), ms_end - pd.DateOffset(years=1), h0, h1, lineas)
    month_tot = int(ms["viajes"].sum())
    month_ref = int(msr["viajes"].sum())
    delta_month = (month_tot - month_ref) / month_ref * 100 if month_ref > 0 else None

# Agregados por estación para el mapa y el popup
station_year = mb.groupby("estacion", as_index=False)["viajes"].sum()
stations_df = station_year.merge(
    mr.groupby("estacion", as_index=False)["viajes"].sum().rename(columns={"viajes": "ref"}),
    on="estacion", how="outer",
)
if mes_sec is not None:
    stations_df = stations_df.merge(
        ms.groupby("estacion", as_index=False)["viajes"].sum().rename(columns={"viajes": "viajes_m"}),
        on="estacion", how="left",
    )
    stations_df = stations_df.merge(
        msr.groupby("estacion", as_index=False)["viajes"].sum().rename(columns={"viajes": "ref_m"}),
        on="estacion", how="left",
    )

stations_df["delta_year"] = np.where(
    stations_df["ref"] > 0,
    (stations_df["viajes"] - stations_df["ref"]) / stations_df["ref"] * 100,
    np.nan,
)
if mes_sec is not None:
    stations_df["delta_month"] = np.where(
        stations_df["ref_m"] > 0,
        (stations_df["viajes_m"] - stations_df["ref_m"]) / stations_df["ref_m"] * 100,
        np.nan,
    )
for col in ("viajes", "ref", "viajes_m", "ref_m"):
    if col in stations_df.columns:
        stations_df[col] = stations_df[col].fillna(0)

## KPIs ----------------------------------------------------------------------
k1, k2, k3 = st.columns(3)
with k1:
    label1 = f"Viajes · {calendar.month_name[mes_sel]}" if vista == "Mes" else f"Viajes · {base_year}"
    sub1 = f'<span>Ventana seleccionada</span><span class="num">{_fmt(tot_base)}</span>'
    st.markdown(
        _metric_box_html(
            label1,
            f'<span style="font-size:34px;">{_fmt(tot_base)}</span>',
            sub1,
            f'{_delta_pill_html(delta_year)}<span style="color:#8b95ab;font-size:13px;">vs {ref_year}</span>',
        ),
        unsafe_allow_html=True,
    )
with k2:
    if mes_sec is not None:
        label2 = "Último mes completo" if vista == "Año" else f"Viajes · {calendar.month_name[mes_sec]}"
        sub2 = f'<span>Mes · {mes_sec:02d}</span><span class="num">{_fmt(month_tot)}</span>'
        badges = f'{_delta_pill_html(delta_month)}<span style="color:#8b95ab;font-size:13px;">vs {ref_year}</span>'
    else:
        label2 = "Último mes completo"
        sub2 = "<span>Sin mes completo en el recorte</span>"
        badges = ""
    st.markdown(
        _metric_box_html(
            label2,
            f'<span style="font-size:34px;">{_fmt(month_tot)}</span>' if month_tot else "—",
            sub2,
            badges,
        ),
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        _metric_box_html(
            "Hora pico de la red",
            f'<span style="font-size:34px;">{peak_net_h:02d}:00\u2013{peak_net_h + 1:02d}:59</span>',
            f'<span>Viajes/día hábil</span><span class="num">{_fmt(peak_net_v)}</span> '
            f'<span>· {_fmt_dec(peak_net_share)}% del día</span>',
        ),
        unsafe_allow_html=True,
    )

## Mapa -----------------------------------------------------------------------
stations_geo = load_subte_stations_geo()
m = folium.Map(tiles="CartoDB positron", control_scale=True)

lines_df = load_subte_lines()
for _, r in lines_df.iterrows():
    draw_route(m, r["coords"], _subte_line_color(r["label"]), weight=4, opacity=0.75)

vals = stations_df["viajes"].clip(lower=0)
vmax = float(vals.max()) if not vals.empty else 0.0
vmin = float(vals.min()) if not vals.empty else 0.0

merged = stations_geo.merge(stations_df, left_on="nombre", right_on="estacion", how="left")
merged = merged[~merged["nombre"].isin(["", "null"])]

if not merged.empty:
    mlats = merged["lat"].tolist()
    mlons = merged["lon"].tolist()
else:
    mlats, mlons = [], []

for _, r in merged.iterrows():
    viajes = float(r["viajes"] or 0)
    color = _scale_color(viajes, vmin, vmax)
    radius = 3.5 + 13.0 * ((viajes - vmin) / (vmax - vmin) if vmax > vmin else 0.0)
    dy = r["delta_year"]
    if mes_sec is not None:
        dm = r.get("delta_month")
        popup_html = (
            f'<div style="font-family:Calibri,Segoe UI,sans-serif;font-size:13px;">'
            f"<b>{_clean_label(r['nombre'])}</b> · Línea {_clean_label(r['linea'])}<hr style='margin:6px 0;'>"
            f"Viajes · {vista.lower()}: <b>{_fmt(viajes)}</b> {_delta_span(dy)}<br>"
            f"Mes {mes_sec:02d}: <b>{_fmt(r['viajes_m'])}</b> {_delta_span(dm)}</div>"
        )
    else:
        popup_html = (
            f'<div style="font-family:Calibri,Segoe UI,sans-serif;font-size:13px;">'
            f"<b>{_clean_label(r['nombre'])}</b> · Línea {_clean_label(r['linea'])}<hr style='margin:6px 0;'>"
            f"Viajes · {vista.lower()}: <b>{_fmt(viajes)}</b> {_delta_span(dy)}</div>"
        )
    folium.CircleMarker(
        location=[r["lat"], r["lon"]],
        radius=radius,
        color="white",
        weight=1.5,
        fill=True,
        fill_color=color,
        fill_opacity=0.9,
        tooltip=f"{_clean_label(r['nombre'])} · {_fmt(viajes)}",
        popup=folium.Popup(popup_html, max_width=280),
    ).add_to(m)

if mlats:
    m.fit_bounds([[min(mlats), min(mlons)], [max(mlats), max(mlons)]], padding=(30, 30))
else:
    lb_lats, lb_lons = [], []
    for _, r in lines_df.iterrows():
        for seg in r["coords"]:
            for lon, lat in seg:
                lb_lats.append(lat)
                lb_lons.append(lon)
    if lb_lats:
        m.fit_bounds([[min(lb_lats), min(lb_lons)], [max(lb_lats), max(lb_lons)]], padding=(30, 30))

st_folium(m, width="100%", height=650, returned_objects=[])
st.caption(
    "Color e intensidad de los marcadores según los viajes del período elegido (con el filtro horario aplicado). "
    "Las estaciones del Premetro no tienen coordenadas en el dataset oficial."
)

## Perfiles horarios ------------------------------------------------------------
st.subheader("Perfil horario (día hábil promedio)")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Toda la red**")
    net_chart_data = per_net.rename(columns={"promedio": "viajes"})
    bar1 = (
        alt.Chart(net_chart_data)
        .mark_bar(color="#2f6fb2")
        .encode(
            x=alt.X("hora:O", title="Hora"),
            y=alt.Y("viajes:Q", title="Viajes promedio"),
            tooltip=[alt.Tooltip("hora:O", title="Hora"), alt.Tooltip("viajes:Q", title="Viajes", format=",.0f")],
        )
        .properties(height=260)
    )
    st.altair_chart(bar1, width="stretch")
with c2:
    exploded = per_file[per_file["estacion"].isin(merged["nombre"])]
    est_opts = sorted(exploded["estacion"].unique())
    if not est_opts:
        st.info("No hay estaciones con datos en esta vista.")
    else:
        sel_station = st.selectbox("Explorar estación", est_opts, key="expl_station")
        per_st = (
            per_file[per_file["estacion"] == sel_station]
            .groupby("hora", as_index=False)["promedio"].sum()
            .rename(columns={"promedio": "viajes"})
        )
        ph, pv, pshare = _peak_window(per_st.set_index("hora")["viajes"])
        st.markdown(f"**{_clean_label(sel_station)}** · pico {ph:02d}:00\u2013{ph + 1:02d}:59 ({_fmt_dec(pshare)}% del día)")
        bar2 = (
            alt.Chart(per_st)
            .mark_bar(color="#7b2fbf")
            .encode(
                x=alt.X("hora:O", title="Hora"),
                y=alt.Y("viajes:Q", title="Viajes promedio"),
                tooltip=[alt.Tooltip("hora:O", title="Hora"), alt.Tooltip("viajes:Q", title="Viajes", format=",.0f")],
            )
            .properties(height=260)
        )
        st.altair_chart(bar2, width="stretch")

## Hora pico por estación -------------------------------------------------------
st.subheader("Hora pico por estación")
peak_rows = []
for est, sub in per_file.groupby("estacion"):
    prof = sub.groupby("hora", as_index=False)["promedio"].sum().set_index("hora")["promedio"]
    h_pk, v_pk, share = _peak_window(prof)
    línea = merged.loc[merged["nombre"] == est, "linea"].iloc[0] if (merged["nombre"] == est).any() else "s/l"
    peak_rows.append(
        {
            "Estación": _clean_label(est),
            "Línea": _clean_label(línea) or "s/l",
            "Franja pico": f"{h_pk:02d}:00\u2013{h_pk + 1:02d}:59",
            "Viajes/día hábil": round(float(v_pk)),
            "% del día": round(float(share), 1),
        }
    )
peak_table = pd.DataFrame(peak_rows).sort_values("Viajes/día hábil", ascending=False).reset_index(drop=True)
st.dataframe(peak_table, width="stretch", hide_index=True)
st.download_button(
    "Descargar hora pico (CSV)",
    peak_table.to_csv(index=False).encode("utf-8-sig"),
    file_name="subte_hora_pico.csv",
    mime="text/csv",
)

## Sobre los datos ----------------------------------------------------------------
with st.expander("Sobre los datos"):
    st.markdown(
        f"""
- **Fuente**: SBASE · "Subte: Viajes Molinetes" (Buenos Aires Data, CC-BY-2.5-AR). Datos por
  **molinete, estación y rango de 15 minutos**; aquí se suman a **hora** y se agrega el tipo de
  pasaje (`pax_TOTAL`).
- Años cargados: **{", ".join(str(y) for y in years)}**. {f"{base_year} es parcial (hasta {b_end:%d/%m/%Y})." if año_parcial else ""}
- El **"vs año anterior"** compara el mismo período del año previo (recorte equivalente cuando el
  año es parcial) y aplica los mismos filtros de franja horaria y líneas.
- La **hora pico** es la franja de 2 horas con más pasajeros en el promedio de **días hábiles**
  (lunes a viernes no feriados) del período seleccionado.
- Estaciones del Premetro (linea PM) y de la extensión reciente de la Línea H no tienen
  coordenadas en el dataset oficial y no se muestran en el mapa (sí cuentan en los totales y la tabla).
- Los datos se agregan una sola vez a `data/molinetes_subte.csv` (+ sidecar `molinetes_agg_meta.json`);
  si cambian los zip fuentes se regeneran solos (patrón igual al de los agregados SUBE).
"""
    )

st.caption(
    f"Fuente: SBASE - Buenos Aires Data. Período {b_start:%d/%m/%Y} \u2192 {b_end:%d/%m/%Y} "
    f"({len(mol['fecha'].unique())} días). Franja horaria {h0:02d}:00\u2013{h1:02d}:00 aplicada a totales y mapa."
)