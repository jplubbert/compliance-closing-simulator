"""Tests del orquestador + queue_builder con predictor mockeado (sin RAG corriendo)."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.modelo import CasoIOC
from core.queue_builder import construir_queue


HOY = date(2025, 6, 16)


def _caso(
    *,
    id_caso: str,
    rut: str,
    dias_atras_reclamo: int,
    fecha_denuncia: date | None,
    monto: int = 1_000_000,
    operacion: str = "01",
) -> CasoIOC:
    f_reclamo = HOY - timedelta(days=dias_atras_reclamo)
    return CasoIOC(
        id_caso=id_caso,
        rut_usuario=rut,
        fecha_aviso=f_reclamo,
        fecha_reclamo=f_reclamo,
        monto_total_impugnado=monto,
        operacion_objeto=operacion,
        fecha_denuncia=fecha_denuncia,
    )


def fake_predictor(payload: dict[str, Any]) -> dict[str, Any]:
    """Devuelve un cronograma de prueba según fecha_reclamo + monto."""
    from datetime import datetime

    fecha_reclamo = datetime.strptime(payload["fecha_reclamo"], "%Y-%m-%d").date()
    monto = int(payload["monto_total_impugnado"])
    es_atm = payload.get("operacion_objeto") in {"04", "05"}
    plazo = 15 if es_atm else 10
    umbral_clp = 35 * 38_500

    fechas: list[dict[str, Any]] = []
    monto_pago1 = min(monto, umbral_clp)
    monto_pago2 = max(0, monto - umbral_clp)
    fundamento = {"texto": "Ley 20.009 Art 5 inc 1", "similitud": 0.91, "extracto": "..."}

    fechas.append({
        "id": "primera_restitucion",
        "evento": "Primera restitución",
        "monto_aplicable": monto_pago1,
        "fecha_limite": str(fecha_reclamo + timedelta(days=plazo)),
        "dias_habiles_calculados": plazo,
        "feriados_considerados": [],
        "fundamento_legal": fundamento,
        "campo_e24": 26,
        "estado_actual": "pendiente",
    })
    if monto_pago2 > 0:
        fechas.append({
            "id": "segunda_restitucion",
            "evento": "Segunda restitución",
            "monto_aplicable": monto_pago2,
            "fecha_limite": str(fecha_reclamo + timedelta(days=plazo + 7)),
            "dias_habiles_calculados": plazo + 7,
            "feriados_considerados": [],
            "fundamento_legal": fundamento,
            "campo_e24": 28,
            "estado_actual": "pendiente",
        })

    return {"fechas_criticas": fechas}


def test_construye_queue_y_clasifica_estados() -> None:
    casos = [
        # Vencido: reclamo hace 30 días, no-ATM (plazo 10), denuncia OK
        _caso(id_caso="v1", rut="40000001 0", dias_atras_reclamo=30, fecha_denuncia=HOY - timedelta(days=25)),
        # Urgente: reclamo hace 9 días, plazo 10 → vence en 1 día
        _caso(id_caso="u1", rut="40000002 0", dias_atras_reclamo=9, fecha_denuncia=HOY - timedelta(days=8)),
        # Por vencer: reclamo de hoy, plazo 10
        _caso(id_caso="pv1", rut="40000003 0", dias_atras_reclamo=0, fecha_denuncia=HOY),
        # Tentativo: sin denuncia, dentro de los 30 días
        _caso(id_caso="t1", rut="40000004 0", dias_atras_reclamo=10, fecha_denuncia=None),
        # Ejecutado: reclamo hace 5 días, pago_1 ya ejecutado
        _caso(id_caso="e1", rut="40000005 0", dias_atras_reclamo=5, fecha_denuncia=HOY - timedelta(days=4)),
    ]

    resultado = construir_queue(
        casos,
        pagos_ejecutados_por_caso={"e1": {1}},
        descartados_caso_ids=set(),
        hoy=HOY,
        predictor_fn=fake_predictor,
    )

    totales = resultado["totales"]
    assert totales["vencidos"] >= 1, f"esperaba ≥1 vencido, totales={totales}"
    assert totales["urgentes"] >= 1, f"esperaba ≥1 urgente, totales={totales}"
    assert totales["por_vencer"] >= 1, f"esperaba ≥1 por_vencer, totales={totales}"
    assert totales["tentativos"] >= 1, f"esperaba ≥1 tentativo, totales={totales}"
    assert totales["ejecutados"] >= 1, f"esperaba ≥1 ejecutado, totales={totales}"

    estados_orden = [item["deadlines"][0]["estado"] for item in resultado["queue"]]
    orden_esperado = {"vencido": 0, "urgente": 1, "por_vencer": 2, "tentativo": 3}
    indices = [orden_esperado[e] for e in estados_orden]
    assert indices == sorted(indices), f"queue desordenada: {estados_orden}"

    print("OK: queue construida con totales y orden correctos")
    print(f"  Totales: {totales}")
    print(f"  Estados en orden: {estados_orden}")


def test_split_2_pagos_si_supera_umbral() -> None:
    casos = [
        _caso(
            id_caso="big1",
            rut="50000001 0",
            dias_atras_reclamo=2,
            fecha_denuncia=HOY,
            monto=35 * 38_500 * 2,
        )
    ]
    resultado = construir_queue(
        casos,
        pagos_ejecutados_por_caso={},
        descartados_caso_ids=set(),
        hoy=HOY,
        predictor_fn=fake_predictor,
    )
    item = resultado["queue"][0]
    assert len(item["deadlines"]) == 2, f"esperaba 2 deadlines, obtuvo {len(item['deadlines'])}"
    assert {d["numero_pago"] for d in item["deadlines"]} == {1, 2}
    print("OK: caso sobre umbral genera 2 deadlines (split)")


def main() -> None:
    test_construye_queue_y_clasifica_estados()
    test_split_2_pagos_si_supera_umbral()
    print("\ntodos los tests del orquestador/queue pasaron.")


if __name__ == "__main__":
    main()
