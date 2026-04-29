"""Conexión a DuckDB local (file-based)."""

import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

DB_PATH = Path(os.environ.get("DUCKDB_PATH", _ROOT / "data" / "casos_ioc.duckdb"))


def get_connection() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))
