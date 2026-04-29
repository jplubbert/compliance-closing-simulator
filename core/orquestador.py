"""Orquestador: llama al predictor del RAG y normaliza al schema Deadline."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import httpx
from dotenv import load_dotenv

from core.modelo import CasoIOC, Deadline, Grupo

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

RAG_BASE_URL = os.environ.get("RAG_BASE_URL", "http://127.0.0.1:8001")
RAG_TIMEOUT_S = 15.0

PredictorFn = Callable[[dict[str, Any]], dict[str, Any]]

_DEADLINE_IDS_PAGO = {
    "primera_restitucion": (1, 26),
    "segunda_restitucion": (2, 28),
}


def _payload_caso(caso: CasoIOC) -> dict[str, Any]:
    return {
        "id_caso": caso.id_caso,
        "rut_usuario": caso.rut_usuario,
        "fecha_aviso": str(caso.fecha_aviso),
        "fecha_reclamo": str(caso.fecha_reclamo),
        "monto_total_impugnado": caso.monto_total_impugnado,
        "operacion_objeto": caso.operacion_objeto,
        "estado_denuncia": caso.estado_denuncia,
        "fecha_entrega_respaldo": (
            str(caso.fecha_entrega_respaldo) if caso.fecha_entrega_respaldo else None
        ),
    }


def _payload_grupo(grupo: Grupo) -> dict[str, Any]:
    return {
        "id_caso": grupo.id_grupo,
        "rut_usuario": grupo.rut_usuario,
        "fecha_aviso": str(grupo.fecha_aviso),
        "fecha_reclamo": str(grupo.fecha_reclamo),
        "monto_total_impugnado": grupo.monto_total_impugnado,
        "operacion_objeto": grupo.operacion_objeto,
        "estado_denuncia": grupo.estado_denuncia,
        "fecha_entrega_respaldo": (
            str(grupo.fecha_entrega_respaldo) if grupo.fecha_entrega_respaldo else None
        ),
    }


def _llamar_rag_http(payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{RAG_BASE_URL}/predecir-cronograma"
    resp = httpx.post(url, json=payload, timeout=RAG_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


def _parse_fecha(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _normalizar_deadlines(rag_response: dict[str, Any]) -> list[Deadline]:
    deadlines: list[Deadline] = []
    for fc in rag_response.get("fechas_criticas", []):
        meta = _DEADLINE_IDS_PAGO.get(fc.get("id"))
        if meta is None:
            continue
        numero_pago, campo_e24 = meta
        deadlines.append(
            Deadline(
                numero_pago=numero_pago,
                monto_aplicable=int(fc.get("monto_aplicable", 0)),
                fecha_limite=_parse_fecha(fc["fecha_limite"]),
                campo_e24=fc.get("campo_e24", campo_e24),
                fundamento_legal=fc.get("fundamento_legal") or {},
                dias_habiles_calculados=fc.get("dias_habiles_calculados"),
                feriados_considerados=list(fc.get("feriados_considerados") or []),
            )
        )
    return deadlines


def predecir_para_caso(
    caso: CasoIOC, predictor: PredictorFn = _llamar_rag_http
) -> list[Deadline]:
    return _normalizar_deadlines(predictor(_payload_caso(caso)))


def predecir_para_grupo(
    grupo: Grupo, predictor: PredictorFn = _llamar_rag_http
) -> list[Deadline]:
    return _normalizar_deadlines(predictor(_payload_grupo(grupo)))
