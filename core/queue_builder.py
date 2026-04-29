"""Construye la queue priorizada de pagos."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Any, Callable

import holidays

from core.agrupador import DIAS_DENUNCIA_LIMITE, agrupar, filtrar_y_descartar
from core.modelo import CasoIOC, Deadline, Grupo
from core.orquestador import (
    PredictorFn,
    predecir_para_caso,
    predecir_para_grupo,
)

URGENTE_DIAS_HABILES = 3

_ESTADO_ORDEN = {"vencido": 0, "urgente": 1, "por_vencer": 2, "tentativo": 3}


def _feriados_chile(year_min: int, year_max: int) -> set[date]:
    return set(holidays.country_holidays("CL", years=range(year_min, year_max + 2)))


def _es_dia_habil(d: date, feriados: set[date]) -> bool:
    return d.weekday() < 5 and d not in feriados


def _dias_habiles_entre(desde: date, hasta: date, feriados: set[date]) -> int:
    """Días hábiles entre `desde` (exclusivo) y `hasta` (inclusivo). Si hasta < desde devuelve negativo."""
    if hasta == desde:
        return 0
    paso = 1 if hasta > desde else -1
    cursor = desde
    cuenta = 0
    while cursor != hasta:
        cursor += timedelta(days=paso)
        if _es_dia_habil(cursor, feriados):
            cuenta += paso
    return cuenta


def _clasificar_estado(
    deadline: Deadline,
    *,
    hoy: date,
    fecha_reclamo: date,
    tiene_denuncia: bool,
    fue_ejecutado: bool,
    feriados: set[date],
) -> str:
    if fue_ejecutado:
        return "ejecutado"
    if not tiene_denuncia and (hoy - fecha_reclamo).days <= DIAS_DENUNCIA_LIMITE:
        return "tentativo"
    if hoy > deadline.fecha_limite:
        return "vencido"
    dias = _dias_habiles_entre(hoy, deadline.fecha_limite, feriados)
    if 0 <= dias <= URGENTE_DIAS_HABILES:
        return "urgente"
    return "por_vencer"


def _serializar_deadline(deadline: Deadline) -> dict[str, Any]:
    d = asdict(deadline)
    d["fecha_limite"] = str(deadline.fecha_limite)
    return d


def _ejec_para_item(
    pagos_caso: dict[str, set[int]], ids_casos: list[str]
) -> set[int]:
    pagos: set[int] = set()
    for cid in ids_casos:
        pagos |= pagos_caso.get(cid, set())
    return pagos


def _orden_key(item: dict[str, Any]) -> tuple[int, str, str]:
    deadlines = item.get("deadlines", [])
    estados = [d["estado"] for d in deadlines]
    if not estados:
        return (99, "9999-99-99", item.get("id_item", ""))
    estado_dominante = min(estados, key=lambda e: _ESTADO_ORDEN.get(e, 99))
    fechas_relev = [
        d["fecha_limite"] for d in deadlines if d["estado"] == estado_dominante
    ]
    fecha_pivot = min(fechas_relev) if fechas_relev else "9999-99-99"
    return (_ESTADO_ORDEN.get(estado_dominante, 99), fecha_pivot, item.get("id_item", ""))


def construir_queue(
    casos: list[CasoIOC],
    *,
    pagos_ejecutados_por_caso: dict[str, set[int]],
    descartados_caso_ids: set[str],
    hoy: date,
    predictor_caso: Callable[[CasoIOC], list[Deadline]] | None = None,
    predictor_grupo: Callable[[Grupo], list[Deadline]] | None = None,
    predictor_fn: PredictorFn | None = None,
) -> dict[str, Any]:
    """Pipeline completo síncrono: filtra, agrupa, llama predictor, clasifica y ordena."""
    pred_caso = predictor_caso or (
        (lambda c: predecir_para_caso(c, predictor_fn))
        if predictor_fn
        else predecir_para_caso
    )
    pred_grupo = predictor_grupo or (
        (lambda g: predecir_para_grupo(g, predictor_fn))
        if predictor_fn
        else predecir_para_grupo
    )

    activos, descartados = filtrar_y_descartar(
        casos,
        pagos_ejecutados_por_caso,
        descartados_caso_ids,
        hoy,
    )
    grupos, individuales = agrupar(activos, pagos_ejecutados_por_caso)

    deadlines_por_id: dict[str, list[Deadline]] = {}
    for grupo in grupos:
        deadlines_por_id[grupo.id_grupo] = pred_grupo(grupo)
    for caso in individuales:
        deadlines_por_id[caso.id_caso] = pred_caso(caso)

    return ensamblar_queue(
        grupos=grupos,
        individuales=individuales,
        descartados=descartados,
        deadlines_por_id=deadlines_por_id,
        pagos_ejecutados_por_caso=pagos_ejecutados_por_caso,
        hoy=hoy,
    )


def ensamblar_queue(
    *,
    grupos: list[Grupo],
    individuales: list[CasoIOC],
    descartados: list[CasoIOC],
    deadlines_por_id: dict[str, list[Deadline]],
    pagos_ejecutados_por_caso: dict[str, set[int]],
    hoy: date,
) -> dict[str, Any]:
    """Clasifica deadlines, ordena y produce la queue final.

    Pensado para ejecutarse una vez `deadlines_por_id` ya fue resuelto (vía RAG
    sincrónico, batch async, mock, etc.). Las claves del dict son `grupo.id_grupo`
    para grupos y `caso.id_caso` para individuales.
    """
    feriados = _feriados_chile(hoy.year - 1, hoy.year + 1)

    items: list[dict[str, Any]] = []

    for grupo in grupos:
        deadlines = deadlines_por_id.get(grupo.id_grupo, [])
        pagos_ejec = _ejec_para_item(pagos_ejecutados_por_caso, grupo.ids_casos)
        items.append(
            _construir_item(
                id_item=grupo.id_grupo,
                tipo="grupo",
                rut=grupo.rut_usuario,
                ids_casos=grupo.ids_casos,
                fecha_reclamo=grupo.fecha_reclamo,
                tiene_denuncia=any(c.fecha_denuncia for c in grupo.casos),
                deadlines=deadlines,
                pagos_ejec=pagos_ejec,
                hoy=hoy,
                feriados=feriados,
            )
        )

    for caso in individuales:
        deadlines = deadlines_por_id.get(caso.id_caso, [])
        pagos_ejec = pagos_ejecutados_por_caso.get(caso.id_caso, set())
        items.append(
            _construir_item(
                id_item=caso.id_caso,
                tipo="individual",
                rut=caso.rut_usuario,
                ids_casos=[caso.id_caso],
                fecha_reclamo=caso.fecha_reclamo,
                tiene_denuncia=caso.fecha_denuncia is not None,
                deadlines=deadlines,
                pagos_ejec=pagos_ejec,
                hoy=hoy,
                feriados=feriados,
            )
        )

    activos_queue = [
        i for i in items
        if any(d["estado"] not in {"ejecutado"} for d in i["deadlines"])
        and i["deadlines"]
    ]
    activos_queue.sort(key=_orden_key)

    ejecutados_items = [
        i for i in items
        if i["deadlines"] and all(d["estado"] == "ejecutado" for d in i["deadlines"])
    ]

    totales = {
        "vencidos":   sum(1 for i in activos_queue for d in i["deadlines"] if d["estado"] == "vencido"),
        "urgentes":   sum(1 for i in activos_queue for d in i["deadlines"] if d["estado"] == "urgente"),
        "por_vencer": sum(1 for i in activos_queue for d in i["deadlines"] if d["estado"] == "por_vencer"),
        "tentativos": sum(1 for i in activos_queue for d in i["deadlines"] if d["estado"] == "tentativo"),
        "ejecutados": sum(1 for i in items for d in i["deadlines"] if d["estado"] == "ejecutado"),
        "descartados": len(descartados),
    }

    return {
        "fecha_corte": str(hoy),
        "totales": totales,
        "queue": activos_queue,
        "ejecutados": ejecutados_items,
        "descartados": [
            {"id_caso": c.id_caso, "rut": c.rut_usuario, "motivo": "sin_denuncia_30d"}
            for c in descartados
        ],
    }


def _construir_item(
    *,
    id_item: str,
    tipo: str,
    rut: str,
    ids_casos: list[str],
    fecha_reclamo: date,
    tiene_denuncia: bool,
    deadlines: list[Deadline],
    pagos_ejec: set[int],
    hoy: date,
    feriados: set[date],
) -> dict[str, Any]:
    deadlines_out: list[dict[str, Any]] = []
    for d in deadlines:
        estado = _clasificar_estado(
            d,
            hoy=hoy,
            fecha_reclamo=fecha_reclamo,
            tiene_denuncia=tiene_denuncia,
            fue_ejecutado=d.numero_pago in pagos_ejec,
            feriados=feriados,
        )
        d.estado = estado
        deadlines_out.append(_serializar_deadline(d))
    return {
        "id_item": id_item,
        "tipo": tipo,
        "rut": rut,
        "casos_incluidos": ids_casos,
        "deadlines": deadlines_out,
    }
