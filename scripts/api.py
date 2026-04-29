"""HTTP API del simulador LSC.

Endpoints:
  GET  /health
  POST /generar-queue   body = {"hoy": "YYYY-MM-DD"} (opcional)

Levantar:
  uvicorn scripts.api:app --port 8002 --host 127.0.0.1
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import defaultdict

from fastapi import FastAPI, HTTPException

from core.agrupador import agrupar, filtrar_y_descartar
from core.db import get_connection
from core.modelo import CasoIOC
from core.orquestador import payload_caso, payload_grupo, predecir_batch
from core.queue_builder import ensamblar_queue


app = FastAPI(
    title="lsc-cierre-simulator API",
    description="Genera la queue priorizada de pagos LSC.",
    version="0.1.0",
)


def _cargar_estado() -> tuple[list[CasoIOC], dict[str, set[int]]]:
    with get_connection() as conn:
        casos_raw = conn.execute(
            """
            SELECT id_caso, rut_usuario, fecha_aviso, fecha_reclamo,
                   fecha_denuncia, monto_total_impugnado, producto_afectado,
                   operacion_objeto, estado_denuncia, fecha_entrega_respaldo
            FROM casos_ioc
            """
        ).fetchall()
        ejec_raw = conn.execute(
            "SELECT id_caso, numero_pago FROM ejecuciones_pago WHERE id_caso IS NOT NULL"
        ).fetchall()
    casos = [
        CasoIOC(
            id_caso=row[0],
            rut_usuario=row[1],
            fecha_aviso=row[2],
            fecha_reclamo=row[3],
            fecha_denuncia=row[4],
            monto_total_impugnado=int(row[5]),
            producto_afectado=row[6],
            operacion_objeto=row[7],
            estado_denuncia=row[8],
            fecha_entrega_respaldo=row[9],
        )
        for row in casos_raw
    ]
    pagos_por_caso: dict[str, set[int]] = defaultdict(set)
    for id_caso, numero_pago in ejec_raw:
        pagos_por_caso[id_caso].add(int(numero_pago))
    return casos, dict(pagos_por_caso)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "lsc-cierre-simulator"}


@app.post("/generar-queue")
async def generar_queue(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    hoy_str = payload.get("hoy")
    try:
        hoy = (
            datetime.strptime(hoy_str, "%Y-%m-%d").date() if hoy_str else date.today()
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="hoy debe ser YYYY-MM-DD")

    casos, pagos = _cargar_estado()
    activos, descartados = filtrar_y_descartar(casos, pagos, set(), hoy)
    grupos, individuales = agrupar(activos, pagos)

    items_a_predecir: list[dict[str, Any]] = []
    for grupo in grupos:
        items_a_predecir.append({"key": grupo.id_grupo, "payload": payload_grupo(grupo)})
    for caso in individuales:
        items_a_predecir.append({"key": caso.id_caso, "payload": payload_caso(caso)})

    batch = await predecir_batch(items_a_predecir)
    deadlines_por_id = {entry["key"]: entry["deadlines"] for entry in batch}

    return ensamblar_queue(
        grupos=grupos,
        individuales=individuales,
        descartados=descartados,
        deadlines_por_id=deadlines_por_id,
        pagos_ejecutados_por_caso=pagos,
        hoy=hoy,
    )
