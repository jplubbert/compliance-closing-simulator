"""Genera 200 casos sintéticos con la distribución requerida."""

from __future__ import annotations

import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_connection
from core.utils import generar_rut_valido

random.seed(42)

TOTAL = 200
HOY = date.today()

CODIGOS_NO_ATM = ["01", "02", "03"]
CODIGOS_ATM = ["04", "05"]
PRODUCTOS = ["1010", "1020", "2010", "2020", "3010"]
ESTADOS_DENUNCIA = ["1", "2", None]

UF_APROX_CLP = 38_500
UMBRAL_UF = 35
UMBRAL_CLP = UF_APROX_CLP * UMBRAL_UF


def _fecha_aleatoria_ultimos(n_dias: int) -> date:
    return HOY - timedelta(days=random.randint(1, n_dias))


def _monto_bajo_umbral() -> int:
    return random.randint(50_000, UMBRAL_CLP - 50_000)


def _monto_sobre_umbral() -> int:
    return random.randint(UMBRAL_CLP + 100_000, UMBRAL_CLP * 4)


def _operacion(es_atm: bool) -> str:
    return random.choice(CODIGOS_ATM if es_atm else CODIGOS_NO_ATM)


def _build_caso(
    *,
    rut: str,
    fecha_reclamo: date,
    es_atm: bool = False,
    monto: int | None = None,
    con_denuncia: bool = True,
    con_respaldo: bool = False,
) -> dict:
    fecha_aviso = fecha_reclamo - timedelta(days=random.randint(0, 2))
    fecha_denuncia = (
        fecha_reclamo + timedelta(days=random.randint(1, 10)) if con_denuncia else None
    )
    fecha_respaldo = (
        fecha_reclamo + timedelta(days=random.randint(15, 25)) if con_respaldo else None
    )
    return {
        "id_caso": f"caso_{uuid.uuid4().hex[:10]}",
        "rut_usuario": rut,
        "fecha_aviso": fecha_aviso,
        "fecha_reclamo": fecha_reclamo,
        "fecha_denuncia": fecha_denuncia,
        "monto_total_impugnado": monto if monto is not None else _monto_bajo_umbral(),
        "producto_afectado": random.choice(PRODUCTOS),
        "operacion_objeto": _operacion(es_atm),
        "estado_denuncia": random.choice(ESTADOS_DENUNCIA),
        "fecha_entrega_respaldo": fecha_respaldo,
    }


def generar() -> tuple[list[dict], list[dict]]:
    casos: list[dict] = []
    ejecuciones: list[dict] = []

    n_individuales = 110  # 55%
    n_pares = 20          # 20% = 40 casos
    n_sin_denuncia = 20   # 10% (descartados: > 30 días sin denuncia)
    n_sobre_umbral = 10   # 5%
    n_pago_1 = 10         # 5%
    n_tentativos = 10     # 5% (sin denuncia, todavía dentro del plazo de 30 días)

    # 55% individuales sin agrupar (mix ATM y no-ATM)
    for _ in range(n_individuales):
        es_atm = random.random() < 0.35
        casos.append(
            _build_caso(
                rut=generar_rut_valido(),
                fecha_reclamo=_fecha_aleatoria_ultimos(60),
                es_atm=es_atm,
            )
        )

    # 20% en pares con mismo RUT y ventana <30 días corridos
    for _ in range(n_pares):
        rut = generar_rut_valido()
        f_base = _fecha_aleatoria_ultimos(50)
        f_segundo = f_base + timedelta(days=random.randint(1, 25))
        if f_segundo > HOY:
            f_segundo = HOY
        casos.append(_build_caso(rut=rut, fecha_reclamo=f_base))
        casos.append(_build_caso(rut=rut, fecha_reclamo=f_segundo))

    # 10% sin denuncia y >30 días corridos
    for _ in range(n_sin_denuncia):
        f_reclamo = HOY - timedelta(days=random.randint(31, 60))
        casos.append(
            _build_caso(
                rut=generar_rut_valido(),
                fecha_reclamo=f_reclamo,
                con_denuncia=False,
            )
        )

    # 5% sobre umbral (split en 2 pagos)
    for _ in range(n_sobre_umbral):
        casos.append(
            _build_caso(
                rut=generar_rut_valido(),
                fecha_reclamo=_fecha_aleatoria_ultimos(60),
                monto=_monto_sobre_umbral(),
            )
        )

    # 5% sin denuncia y todavía dentro del plazo de 30 días (tentativos)
    for _ in range(n_tentativos):
        f_reclamo = HOY - timedelta(days=random.randint(5, 25))
        casos.append(
            _build_caso(
                rut=generar_rut_valido(),
                fecha_reclamo=f_reclamo,
                con_denuncia=False,
            )
        )

    # 5% con pago_1 ya ejecutado
    for _ in range(n_pago_1):
        caso = _build_caso(
            rut=generar_rut_valido(),
            fecha_reclamo=_fecha_aleatoria_ultimos(40),
        )
        casos.append(caso)
        ejecuciones.append(
            {
                "id_ejecucion": f"ejec_{uuid.uuid4().hex[:10]}",
                "id_caso": caso["id_caso"],
                "id_grupo": None,
                "numero_pago": 1,
                "monto_pagado": caso["monto_total_impugnado"],
                "fecha_ejecucion": caso["fecha_reclamo"]
                + timedelta(days=random.randint(3, 9)),
                "justificacion": None,
            }
        )

    return casos, ejecuciones


def main() -> None:
    casos, ejecuciones = generar()
    with get_connection() as conn:
        conn.execute("DELETE FROM casos_ioc")
        conn.execute("DELETE FROM ejecuciones_pago")
        for c in casos:
            conn.execute(
                """
                INSERT INTO casos_ioc (
                    id_caso, rut_usuario, fecha_aviso, fecha_reclamo,
                    fecha_denuncia, monto_total_impugnado, producto_afectado,
                    operacion_objeto, estado_denuncia, fecha_entrega_respaldo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    c["id_caso"], c["rut_usuario"], c["fecha_aviso"], c["fecha_reclamo"],
                    c["fecha_denuncia"], c["monto_total_impugnado"], c["producto_afectado"],
                    c["operacion_objeto"], c["estado_denuncia"], c["fecha_entrega_respaldo"],
                ],
            )
        for e in ejecuciones:
            conn.execute(
                """
                INSERT INTO ejecuciones_pago (
                    id_ejecucion, id_caso, id_grupo, numero_pago,
                    monto_pagado, fecha_ejecucion, justificacion
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    e["id_ejecucion"], e["id_caso"], e["id_grupo"], e["numero_pago"],
                    e["monto_pagado"], e["fecha_ejecucion"], e["justificacion"],
                ],
            )

    n_atm = sum(1 for c in casos if c["operacion_objeto"] in ("04", "05"))
    n_sin_den = sum(1 for c in casos if c["fecha_denuncia"] is None)
    n_tentativos_real = sum(
        1
        for c in casos
        if c["fecha_denuncia"] is None and (HOY - c["fecha_reclamo"]).days <= 30
    )
    n_descartables = n_sin_den - n_tentativos_real
    n_sobre = sum(1 for c in casos if c["monto_total_impugnado"] > 35 * 38_500)

    print(f"Seed completo: {len(casos)} casos insertados.")
    print(f"  ATM (04/05):                    {n_atm}")
    print(f"  No-ATM:                         {len(casos) - n_atm}")
    print(f"  Sin denuncia (total):           {n_sin_den}")
    print(f"    Tentativos (<=30d):           {n_tentativos_real}")
    print(f"    Descartables (>30d):          {n_descartables}")
    print(f"  Sobre umbral 35 UF (~{35 * 38_500:,} CLP): {n_sobre}")
    print(f"  Ejecuciones de pago:            {len(ejecuciones)}")


if __name__ == "__main__":
    main()
