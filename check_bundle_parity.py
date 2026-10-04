"""Smoke test del bundle: comprueba que data_bundle/ sea fiel a las fuentes crudas.

Si un builder cambia (o se rompe), el bundle commiteado queda desactualizado en
silencio y las apps muestran números viejos. Este script lo detecta en segundos:

    venv\\Scripts\\python check_bundle_parity.py

Sale con código 1 si algo no cuadra, así sirve como paso de CI o pre-commit.

Hace dos cosas:

A) Invariantes que no necesitan los datos crudos (baratos y detectan los bugs
   más caros): el filtro de grafías SUBE, el dtype de `fecha` del bundle y la
   completitud de `_grid_matches`.
B) Paridad bundle <-> crudo: reconstruye las tablas geográficas desde `data/`
   con los MISMOS builders de `data_loaders` y las compara contra los parquet.
   Los agregados (SUBE, molinetes) no se reconstruyen: se comparan contra los
   CSV agregados ya escritos en `data/`, que es lo que produce el bundle.

Nota: no rebuilda los agregados a propósito (reingerir los ZIP de molinetes
tarda ~300 s y escribiría en `data/`).
"""
import gzip
import json
import os
import sys

import numpy as np
import pandas as pd

import data_loaders as dl

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  OK   " if ok else "  FALLA") + f"  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)


def section(title: str) -> None:
    print()
    print(title)


# ---------------------------------------------------------------------------
# A) invariantes baratos
# ---------------------------------------------------------------------------
def test_sube_filtro() -> None:
    section("A1. Filtro de grafías de línea SUBE")
    # AMBA: variantes con prefijo y con la palabra LINEA
    for code in [
        "CABA_LINEA_001", "CABA_LINEA_025", "CABA_LINEA_ 42",
        "BSAS_LINEA_148", "BSAS_LINEA303", "BS_AS_LINEA_326", "BS_ASLINEA_327",
        "LINEA_BSAS_503", "LINEA 1", "LINEA 410", "LINEA 501 A", "LINEA_504B",
        "LINEA_506_AMBA", "LINEA_540_BSAS", "LINEA_506F_BSAS",
    ]:
        check(f"acepta {code}", dl._is_amba_sube_code(code))
    # NO AMBA: colisiones de número con CABA, o sin dígitos
    for code in [
        "LINEA RZ-1", "LINEA RZ-11", "RZ-1", "1", "2A", "2B",
        "LINEA OESTE", "NORTE MUNICIPAL", "",
    ]:
        check(f"rechaza {code or '(vacío)'}", not dl._is_amba_sube_code(code))
    # el patrón vectorizado y la versión por fila tienen que coincidir
    mismatches = [
        c for c in
        ["CABA_LINEA_001", "BSAS_LINEA303", "LINEA 410", "LINEA_540_BSAS",
         "LINEA RZ-3", "1", "LINEA OESTE"]
        if bool(dl.SUBE_LINEA_RE.match(c)) != dl._is_amba_sube_code(c)
    ]
    check("regex vectorizada == _is_amba_sube_code", not mismatches, str(mismatches))


def test_lineas_amba_con_demanda() -> None:
    section("A2. Líneas AMBA con recorrido que deben tener demanda SUBE")
    if not os.path.exists(dl.SUBE_MONTHLY_FILE):
        check("agregado SUBE presente", False, "falta data/sube_usos_mensuales.csv")
        return
    sube = pd.read_csv(dl.SUBE_MONTHLY_FILE, dtype={"linea": str})
    con_dato = set(sube["linea"])
    rutas = dl.load_routes_df()
    # líneas municipales/provinciales del AMBA que el filtro anterior descartaba
    esperadas = ["326", "410", "429", "521", "526", "527", "540", "542",
                 "548", "550", "551", "552", "553", "630"]
    faltan = [L for L in esperadas if L not in con_dato]
    check("agregado SUBE cubre las 14 líneas que se perdían", not faltan, str(faltan))
    huerfanas = sorted(set(rutas["linea"]) - con_dato)
    check("pocas líneas sin demanda", len(huerfanas) <= 12, f"{len(huerfanas)}: {huerfanas}")


def test_sube_daily_dtype() -> None:
    section("A3. Tipos del bundle")
    if not dl.bundle_available():
        check("bundle disponible", False, "data_bundle/bundle_meta.json ausente o con otro schema_version")
        return
    d = dl.load_sube_daily("check")
    check("load_sube_daily().fecha es datetime", pd.api.types.is_datetime64_any_dtype(d["fecha"]),
          str(d["fecha"].dtype))
    m = dl.load_sube_transactions("check")
    check("load_sube_transactions().fecha es datetime", pd.api.types.is_datetime64_any_dtype(m["fecha"]),
          str(m["fecha"].dtype))
    mol = dl.load_molinetes("check")
    check("load_molinetes().fecha es datetime", pd.api.types.is_datetime64_any_dtype(mol["fecha"]),
          str(mol["fecha"].dtype))
    r = dl.load_routes_df()
    check("routes.parquet longitud_m es float", pd.api.types.is_numeric_dtype(r["longitud_m"]),
          str(r["longitud_m"].dtype))
    check("routes.parquet son listas de Python", isinstance(r["coords"].iloc[0], list),
          type(r["coords"].iloc[0]).__name__)


def test_grid_matches() -> None:
    section("A4. _grid_matches barre todas las celdas vecinas")
    # Dos puntos de red a ~250 m al norte y al sur del punto consulta: caen en
    # anillos opuestos. Con el `break` en el loop de `di` sólo se encontraba uno.
    cell = dl.NET_CELL_M
    lat0, lon0 = -34.60, -58.40
    lat_m = 111_320.0
    lon_m = lat_m * np.cos(np.radians(lat0))
    d = 250.0
    net_lat = np.array([lat0 - d / lat_m, lat0 + d / lat_m])
    net_lon = np.array([lon0, lon0])
    grid, meta = dl.build_point_grid(net_lat, net_lon)
    hits, query_hit = dl._grid_matches(grid, meta, net_lat, net_lon,
                                       np.array([lat0]), np.array([lon0]), 300.0)
    check("encuentra los 2 puntos a 250 m", len(hits) == 2, f"encontrados={len(hits)}")
    check("marca el punto consulta como cubierto", bool(query_hit[0]))

    # invariante de alcance: la grilla no puede perder cobertura frente a un
    # barrido denso sobre la red real
    lat, lon, _ = dl.bus_network(dl._data_token(dl.ROUTES_SOURCE_FILES))
    grid, meta = dl.build_point_grid(lat, lon)
    ren = dl.load_renabap_points()
    _, q_bug = dl._grid_matches(grid, meta, lat, lon, ren["lat"], ren["lon"], dl.RENABAP_RADIUS_M)
    cubierta = ren["id"][q_bug].nunique()
    check("cobertura RE-NABAP > 500 barrios a 300 m", cubierta > 500, f"{cubierta} barrios")


# ---------------------------------------------------------------------------
# B) paridad bundle <-> crudo
# ---------------------------------------------------------------------------
def _df_equal(a: pd.DataFrame, b: pd.DataFrame, keys: list[str], sums: list[str]) -> tuple[bool, str]:
    faltan = [c for c in keys + sums if c not in a.columns or c not in b.columns]
    if faltan:
        return False, f"columnas faltantes: {faltan} (A={list(a.columns)}, B={list(b.columns)})"
    if len(a) != len(b):
        return False, f"filas {len(a)} vs {len(b)}"
    ka = set(map(tuple, a[keys].astype(str).to_numpy()))
    kb = set(map(tuple, b[keys].astype(str).to_numpy()))
    if ka != kb:
        return False, f"{len(ka - kb)} claves solo en A, {len(kb - ka)} solo en B"
    for col in sums:
        sa, sb = a[col].sum(), b[col].sum()
        if abs(float(sa) - float(sb)) > max(1e-6, abs(float(sa)) * 1e-9):
            return False, f"{col}: {sa} vs {sb}"
    return True, f"{len(a)} filas"


def _lines_equal(a: pd.DataFrame, b: pd.DataFrame, keycol: str) -> tuple[bool, str]:
    """Para líneas: compara identidad por nombre + geometría normalizada a JSON.

    No se puede comparar `coords` con astype(str): el bundle devuelve listas y el
    rebuild tuples, así que el repr difiere aunque la geometría sea idéntica.
    """
    faltan = [c for c in [keycol, "coords"] if c not in a.columns or c not in b.columns]
    if faltan:
        return False, f"columnas faltantes: {faltan} (A={list(a.columns)}, B={list(b.columns)})"
    if len(a) != len(b):
        return False, f"filas {len(a)} vs {len(b)}"

    def norm(df):
        return sorted(
            zip(
                df[keycol].astype(str),
                (json.dumps(c) for c in df["coords"]),
            )
        )

    na, nb = norm(a), norm(b)
    if na != nb:
        solo_a = [x[0] for x in na if x not in nb][:5]
        return False, f"geometría distinta (p.ej. {solo_a})"
    return True, f"{len(a)} líneas"


def test_paridad() -> None:
    section("B. Paridad bundle <-> fuentes crudas")
    if not dl.bundle_available():
        check("bundle disponible", False, "corrá build_data_bundle.py primero")
        return

    # --- recorridos: el invariante que caza la pérdida de recorridos RMBA ---
    routes_fc = dl.load_geojson(dl.ROUTES_FILE, dl.ROUTES_URL)
    fuentes = dl._load_amba_sources()
    base = dl.build_routes_table(routes_fc)
    base["jurisdiccion"] = "CABA"
    covered = set(base["linea"])
    esperados_rmba = sum(
        1
        for fc, _j in fuentes
        for f in fc["features"]
        if dl._norm_rmba_linea(f["properties"].get("LINEA")) not in covered
        and dl._norm_rmba_linea(f["properties"].get("LINEA")) is not None
    )
    esperado = len(base) + esperados_rmba
    b_routes = dl._read_parquet_bundle(dl.BUNDLE_ROUTES_FILE)
    check("routes: un feature por recorrido RMBA no cubierto por BA Data",
          len(b_routes) == esperado, f"{len(b_routes)} vs {esperado} (BA Data {len(base)})")
    ok, det = _df_equal(
        b_routes[b_routes["jurisdiccion"] == "CABA"].reset_index(drop=True), base,
        ["linea", "recorrido", "sentido", "jurisdiccion"], ["longitud_m"],
    )
    check("routes: subconjunto CABA del bundle = rebuild", ok, det)
    km = b_routes.groupby("jurisdiccion")["longitud_m"].sum() / 1000.0
    check("routes: km de AMBA > 40.000", km.sum() > 40000,
          " ".join(f"{k}={v:,.0f}km" for k, v in km.items()))

    # --- paradas ---
    b_stops = dl._read_parquet_bundle(dl.BUNDLE_STOPS_FILE)
    stops = dl.build_stops_table(dl.load_geojson(dl.STOPS_FILE, dl.STOPS_URL))
    ok, det = _df_equal(b_stops, stops, ["linea", "lat", "lon"], [])
    check("stops: paridad con rebuild", ok, det)

    # --- agregados SUBE (comparados contra los CSV de data/, sin rebuild) ---
    if os.path.exists(dl.SUBE_MONTHLY_FILE):
        m = pd.read_csv(dl.SUBE_MONTHLY_FILE, dtype={"linea": str})
        b_m = dl._read_parquet_bundle(dl.BUNDLE_SUBE_MENSUAL_FILE)
        ok, det = _df_equal(b_m, m, ["linea", "fecha"], ["transacciones"])
        check("sube_mensual: paridad", ok, det)
        meses = pd.to_datetime(b_m["fecha"]).dt.to_period("M")
        check("sube_mensual: 24 meses completos", meses.nunique() == 24,
              f"{meses.min()}..{meses.max()} ({meses.nunique()})")
    if os.path.exists(dl.SUBE_DAILY_FILE):
        d = pd.read_csv(dl.SUBE_DAILY_FILE, dtype={"linea": str})
        b_d = dl._read_parquet_bundle(dl.BUNDLE_SUBE_DIARIO_FILE)
        ok, det = _df_equal(b_d, d, ["linea", "fecha", "tipo_dia"], ["transacciones"])
        check("sube_diario: paridad", ok, det)

    # --- molinetes ---
    if os.path.exists(dl.MOLINETES_AGG_FILE):
        mol = pd.read_csv(dl.MOLINETES_AGG_FILE, dtype={"linea": str, "estacion": str})
        b_mol = dl._read_parquet_bundle(dl.BUNDLE_MOLINETES_FILE)
        ok, det = _df_equal(b_mol, mol, ["linea", "fecha", "hora", "estacion"], ["viajes"])
        check("molinetes: paridad", ok, det)

    # --- subte / ferrocarril ---
    for name, bundle_path, path, url, builder, keycol in [
        ("subte_lineas", dl.BUNDLE_SUBTE_LINES_FILE, dl.SUBTE_LINEAS_FILE,
         dl.SUBTE_LINEAS_URL, dl.build_subte_lines_df, "label"),
        ("subte_estaciones", dl.BUNDLE_SUBTE_STATIONS_FILE, dl.SUBTE_ESTACIONES_FILE,
         dl.SUBTE_ESTACIONES_URL, dl.build_subte_stations_df, ["estacion", "linea"]),
        ("ffcc_lineas", dl.BUNDLE_FFCC_LINES_FILE, dl.FFCC_LINEAS_FILE,
         dl.FFCC_LINEAS_URL, dl.build_ffcc_lines_df, "linea"),
        ("ffcc_estaciones", dl.BUNDLE_FFCC_STATIONS_FILE, dl.FFCC_ESTACIONES_FILE,
         dl.FFCC_ESTACIONES_URL, dl.build_ffcc_stations_df, ["nombre"]),
    ]:
        b = dl._read_parquet_bundle(bundle_path)
        rebuilt = builder(dl.load_geojson(path, url))
        igual = _lines_equal if isinstance(keycol, str) else _df_equal
        ok, det = igual(b, rebuilt, keycol) if igual is _lines_equal else igual(b, rebuilt, keycol, [])
        check(f"{name}: paridad", ok, det)

    # --- geojson comprimidos ---
    with open(dl.BUNDLE_META_FILE, encoding="utf-8") as f:
        meta = json.load(f)
    faltantes = [n for n in meta["files"] if not os.path.exists(os.path.join(dl.BUNDLE_DIR, n))]
    check("bundle_meta lista archivos que existen", not faltantes, str(faltantes))
    desfasaje = [n for n, mb in meta["files"].items()
                  if abs(os.path.getsize(os.path.join(dl.BUNDLE_DIR, n)) / 1e6 - mb) > 0.01]
    check("bundle_meta: tamaños declarados correctos", not desfasaje, str(desfasaje))
    with gzip.open(dl.BUNDLE_COMUNAS_FILE, "rt", encoding="utf-8-sig") as f:
        comunas = json.load(f)
    check("comunas: 15 features", len(comunas["features"]) == 15, str(len(comunas["features"])))
    with gzip.open(dl.BUNDLE_RENABAP_FILE, "rt", encoding="utf-8-sig") as f:
        ren = json.load(f)
    check("renabap: > 1000 barrios AMBA", len(ren["features"]) > 1000, str(len(ren["features"])))


def main() -> int:
    print("Chequeo del bundle:", dl.BUNDLE_DIR)
    print("schema_version esperado:", dl.BUNDLE_SCHEMA_VERSION)
    test_sube_filtro()
    test_lineas_amba_con_demanda()
    test_sube_daily_dtype()
    test_grid_matches()
    test_paridad()

    print()
    if FAILURES:
        print(f"FALLARON {len(FAILURES)} chequeos:")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("Todos los chequeos OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
