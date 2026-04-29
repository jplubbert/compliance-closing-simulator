"""Agrupación de casos por RUT."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta

from core.modelo import CasoIOC, Grupo

DIAS_DENUNCIA_LIMITE = 30


def filtrar_y_descartar(
    casos: list[CasoIOC],
    pagos_ejecutados_por_caso: dict[str, set[int]],
    descartados_caso_ids: set[str],
    hoy: date,
) -> tuple[list[CasoIOC], list[CasoIOC]]:
    """Devuelve (activos, descartados_sin_denuncia).

    Aplica:
      - Skip de casos con id en descartados_caso_ids (estado_caso = descartado).
      - Skip de casos con pago_1 ya ejecutado *y* pago_2 ya ejecutado (no aplica
        a casos individuales con solo pago_1 ejecutado, esos siguen activos
        pero NO se agrupan).
      - Descarte por falta de denuncia (Ley 20.009 Art 4 inc 4): sin
        fecha_denuncia y >30 días corridos desde fecha_reclamo.
    """
    activos: list[CasoIOC] = []
    descartados: list[CasoIOC] = []
    for caso in casos:
        if caso.id_caso in descartados_caso_ids:
            continue
        if caso.fecha_denuncia is None:
            dias_desde_reclamo = (hoy - caso.fecha_reclamo).days
            if dias_desde_reclamo > DIAS_DENUNCIA_LIMITE:
                descartados.append(caso)
                continue
        activos.append(caso)
    return activos, descartados


def agrupar(
    casos_activos: list[CasoIOC],
    pagos_ejecutados_por_caso: dict[str, set[int]],
) -> tuple[list[Grupo], list[CasoIOC]]:
    """Devuelve (grupos, casos_individuales).

    Reglas:
      - Casos del mismo RUT con pago_1 NO ejecutado se agrupan.
      - Casos con pago_1 ya ejecutado se mantienen como individuales (aunque
        compartan RUT con otro caso pendiente).
      - RUTs con un solo caso pendiente quedan como individuales.
    """
    por_rut: dict[str, list[CasoIOC]] = defaultdict(list)
    individuales_por_pago_avanzado: list[CasoIOC] = []

    for caso in casos_activos:
        if 1 in pagos_ejecutados_por_caso.get(caso.id_caso, set()):
            individuales_por_pago_avanzado.append(caso)
        else:
            por_rut[caso.rut_usuario].append(caso)

    grupos: list[Grupo] = []
    individuales: list[CasoIOC] = list(individuales_por_pago_avanzado)
    for rut, casos_rut in por_rut.items():
        if len(casos_rut) >= 2:
            grupos.append(
                Grupo(
                    id_grupo=f"grp_{uuid.uuid4().hex[:8]}",
                    rut_usuario=rut,
                    casos=casos_rut,
                )
            )
        else:
            individuales.extend(casos_rut)

    return grupos, individuales
