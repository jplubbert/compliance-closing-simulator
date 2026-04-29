"""Inicializa el schema DuckDB del simulador."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import DB_PATH, get_connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS casos_ioc (
    id_caso TEXT PRIMARY KEY,
    rut_usuario TEXT NOT NULL,
    fecha_aviso DATE NOT NULL,
    fecha_reclamo DATE NOT NULL,
    fecha_denuncia DATE,
    monto_total_impugnado BIGINT NOT NULL,
    producto_afectado TEXT,
    operacion_objeto TEXT NOT NULL,
    estado_denuncia TEXT,
    fecha_entrega_respaldo DATE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ejecuciones_pago (
    id_ejecucion TEXT PRIMARY KEY,
    id_caso TEXT,
    id_grupo TEXT,
    numero_pago INTEGER,
    monto_pagado BIGINT,
    fecha_ejecucion DATE,
    justificacion TEXT
);

CREATE INDEX IF NOT EXISTS casos_rut_idx ON casos_ioc (rut_usuario);
CREATE INDEX IF NOT EXISTS casos_fecha_reclamo_idx ON casos_ioc (fecha_reclamo);
CREATE INDEX IF NOT EXISTS ejec_caso_idx ON ejecuciones_pago (id_caso);
"""


def main() -> None:
    with get_connection() as conn:
        conn.execute(SCHEMA)
        casos = conn.execute("SELECT count(*) FROM casos_ioc").fetchone()[0]
        ejec = conn.execute("SELECT count(*) FROM ejecuciones_pago").fetchone()[0]
    print(f"DB lista en {DB_PATH}")
    print(f"  casos_ioc:        {casos} filas")
    print(f"  ejecuciones_pago: {ejec} filas")


if __name__ == "__main__":
    main()
