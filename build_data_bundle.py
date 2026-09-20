"""Genera data_bundle/: datos derivados precomputados para deploy liviano.

Reusa los builders de data_loaders.py (unica fuente de verdad) y escribe parquet
(zstd) + geojson comprimidos en data_bundle/ con un bundle_meta.json.

Uso (cuando cambian las fuentes, p.ej. SUBE/molinetes de un anio nuevo):

    venv\\Scripts\\python build_data_bundle.py

El bundle resultante se commitea al repo: Streamlit Cloud clona el repo y las
apps arrancan sin descargar los ~190-230 MB de fuentes crudas por sesion.
"""
import gzip
import json
import os
from datetime import datetime, timezone

import pandas as pd

from data_loaders import (
    BUNDLE_DIR,
    BUNDLE_META_FILE,
    BUNDLE_SCHEMA_VERSION,
    SUBE_DAILY_FILE,
    SUBE_MONTHLY_FILE,
    _build_molinetes_aggregates,
    _build_sube_aggregates,
    _load_amba_sources,
    _load_geojson_safe,
    _load_renabap_geojson,
    load_geojson,
    load_comunas,
    build_stops_table,
    build_routes_table_amba,
    build_subte_lines_df,
    build_subte_stations_df,
    build_ffcc_lines_df,
    build_ffcc_stations_df,
    FFCC_ESTACIONES_FILE,
    FFCC_ESTACIONES_URL,
    FFCC_LINEAS_FILE,
    FFCC_LINEAS_URL,
    ROUTES_FILE,
    ROUTES_URL,
    STOPS_FILE,
    STOPS_URL,
    SUBTE_ESTACIONES_FILE,
    SUBTE_ESTACIONES_URL,
    SUBTE_LINEAS_FILE,
    SUBTE_LINEAS_URL,
)

BUNDLE_ROUTES_FILE = os.path.join(BUNDLE_DIR, "routes.parquet")
BUNDLE_STOPS_FILE = os.path.join(BUNDLE_DIR, "stops.parquet")
BUNDLE_SUBE_MENSUAL_FILE = os.path.join(BUNDLE_DIR, "sube_mensual.parquet")
BUNDLE_SUBE_DIARIO_FILE = os.path.join(BUNDLE_DIR, "sube_diario.parquet")
BUNDLE_MOLINETES_FILE = os.path.join(BUNDLE_DIR, "molinetes.parquet")
BUNDLE_SUBTE_LINES_FILE = os.path.join(BUNDLE_DIR, "subte_lines.parquet")
BUNDLE_SUBTE_STATIONS_FILE = os.path.join(BUNDLE_DIR, "subte_stations.parquet")
BUNDLE_FFCC_LINES_FILE = os.path.join(BUNDLE_DIR, "ffcc_lines.parquet")
BUNDLE_FFCC_STATIONS_FILE = os.path.join(BUNDLE_DIR, "ffcc_stations.parquet")
BUNDLE_COMUNAS_FILE = os.path.join(BUNDLE_DIR, "comunas.geojson.gz")
BUNDLE_RENABAP_FILE = os.path.join(BUNDLE_DIR, "renabap_amba.geojson.gz")

PARQUET_OPTS = {"engine": "auto", "compression": "zstd", "index": False}

SUBTECC_SOURCES = {
    "subte_lineas": (SUBTE_LINEAS_FILE, SUBTE_LINEAS_URL, "líneas de subte"),
    "subte_estaciones": (SUBTE_ESTACIONES_FILE, SUBTE_ESTACIONES_URL, "estaciones de subte"),
    "ffcc_lineas": (FFCC_LINEAS_FILE, FFCC_LINEAS_URL, "líneas de ferrocarril"),
    "ffcc_estaciones": (FFCC_ESTACIONES_FILE, FFCC_ESTACIONES_URL, "estaciones de ferrocarril"),
}


def _write_df(path: str, df: pd.DataFrame, label: str) -> None:
    if df is None or df.empty:
        raise RuntimeError(f"{label}: DataFrame vacío, no se escribe el bundle")
    df.reset_index(drop=True).to_parquet(path, **PARQUET_OPTS)


def _write_gzip_geojson(path: str, fc, label: str) -> None:
    if not fc or not fc.get("features"):
        raise RuntimeError(f"{label}: GeoJSON vacío, no se escribe el bundle")
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)


def main() -> None:
    os.makedirs(BUNDLE_DIR, exist_ok=True)
    report = []

    print("Construyendo stops (paradas de colectivo)...")
    stops = build_stops_table(load_geojson(STOPS_FILE, STOPS_URL))
    _write_df(BUNDLE_STOPS_FILE, stops, "paradas")
    report.append(("stops.parquet", len(stops), os.path.getsize(BUNDLE_STOPS_FILE) / 1e6))

    print("Construyendo routes (recorridos AMBA completos)...")
    routes = build_routes_table_amba(load_geojson(ROUTES_FILE, ROUTES_URL), _load_amba_sources())
    _write_df(BUNDLE_ROUTES_FILE, routes, "recorridos")
    report.append(("routes.parquet", len(routes), os.path.getsize(BUNDLE_ROUTES_FILE) / 1e6))

    print("Construyendo agregados SUBE (24m mensual + 12m diario)...")
    _build_sube_aggregates()
    if not (os.path.exists(SUBE_MONTHLY_FILE) and os.path.exists(SUBE_DAILY_FILE)):
        raise RuntimeError("No se generaron los agregados SUBE (faltan los CSV crudos en data/?)")
    sube_mensual = pd.read_csv(SUBE_MONTHLY_FILE, dtype={"linea": str})
    sube_diario = pd.read_csv(SUBE_DAILY_FILE, dtype={"linea": str})
    _write_df(BUNDLE_SUBE_MENSUAL_FILE, sube_mensual, "SUBE mensual")
    _write_df(BUNDLE_SUBE_DIARIO_FILE, sube_diario, "SUBE diario")
    report.append(("sube_mensual.parquet", len(sube_mensual), os.path.getsize(BUNDLE_SUBE_MENSUAL_FILE) / 1e6))
    report.append(("sube_diario.parquet", len(sube_diario), os.path.getsize(BUNDLE_SUBE_DIARIO_FILE) / 1e6))

    print("Construyendo agregados de molinetes (SBASE)...")
    mol = _build_molinetes_aggregates()
    if mol.empty:
        raise RuntimeError("No se generaron los agregados de molinetes (faltan los zips en data/molinetes/?)")
    _write_df(BUNDLE_MOLINETES_FILE, mol, "molinetes")
    report.append(("molinetes.parquet", len(mol), os.path.getsize(BUNDLE_MOLINETES_FILE) / 1e6))

    print("Subte / ferrocarril (líneas y estaciones)...")
    builders = {
        "subte_lineas": build_subte_lines_df,
        "subte_estaciones": build_subte_stations_df,
        "ffcc_lineas": build_ffcc_lines_df,
        "ffcc_estaciones": build_ffcc_stations_df,
    }
    targets = {
        "subte_lineas": BUNDLE_SUBTE_LINES_FILE,
        "subte_estaciones": BUNDLE_SUBTE_STATIONS_FILE,
        "ffcc_lineas": BUNDLE_FFCC_LINES_FILE,
        "ffcc_estaciones": BUNDLE_FFCC_STATIONS_FILE,
    }
    for key in SUBTECC_SOURCES:
        path, url, desc = SUBTECC_SOURCES[key]
        fc = _load_geojson_safe(path, url, desc)
        if fc is None:
            raise RuntimeError(f"No se pudo cargar {desc}")
        df = builders[key](fc)
        out = targets[key]
        _write_df(out, df, desc)
        report.append((os.path.basename(out), len(df), os.path.getsize(out) / 1e6))

    print("Comunas y RE-NABAP (geojson comprimidos)...")
    comunas = load_comunas()
    _write_gzip_geojson(BUNDLE_COMUNAS_FILE, comunas, "comunas")
    ren = _load_renabap_geojson()
    if ren is None:
        raise RuntimeError("No se pudo cargar renabap_amba.geojson")
    _write_gzip_geojson(BUNDLE_RENABAP_FILE, ren, "RE-NABAP")
    report.append(("comunas.geojson.gz", len(comunas["features"]), os.path.getsize(BUNDLE_COMUNAS_FILE) / 1e6))
    report.append(("renabap_amba.geojson.gz", len(ren["features"]), os.path.getsize(BUNDLE_RENABAP_FILE) / 1e6))

    files_meta = {
        os.path.basename(p): os.path.getsize(p) / 1e6
        for p in (
            BUNDLE_ROUTES_FILE, BUNDLE_STOPS_FILE,
            BUNDLE_SUBE_MENSUAL_FILE, BUNDLE_SUBE_DIARIO_FILE,
            BUNDLE_MOLINETES_FILE,
            BUNDLE_SUBTE_LINES_FILE, BUNDLE_SUBTE_STATIONS_FILE,
            BUNDLE_FFCC_LINES_FILE, BUNDLE_FFCC_STATIONS_FILE,
            BUNDLE_COMUNAS_FILE, BUNDLE_RENABAP_FILE,
        )
    }
    meta = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": {k: round(v, 3) for k, v in files_meta.items()},
    }
    with open(BUNDLE_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print()
    print(f"Bundle generado en {BUNDLE_DIR}")
    for name, nrows, mb in sorted(report):
        print(f"  {name:<24} {nrows:>6} filas   {mb:6.2f} MB")
    total = sum(files_meta.values())
    print(f"\nTotal: {total:.1f} MB (vs ~420 MB de fuentes crudas)")


if __name__ == "__main__":
    main()