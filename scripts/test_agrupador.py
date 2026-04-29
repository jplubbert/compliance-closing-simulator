"""Tests del agrupador (sin DB ni RAG)."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agrupador import agrupar, filtrar_y_descartar
from core.modelo import CasoIOC


HOY = date(2025, 6, 1)


def _caso(
    *,
    id_caso: str,
    rut: str,
    fecha_reclamo: date,
    fecha_denuncia: date | None = None,
    monto: int = 1_000_000,
    operacion: str = "01",
) -> CasoIOC:
    return CasoIOC(
        id_caso=id_caso,
        rut_usuario=rut,
        fecha_aviso=fecha_reclamo,
        fecha_reclamo=fecha_reclamo,
        monto_total_impugnado=monto,
        operacion_objeto=operacion,
        fecha_denuncia=fecha_denuncia,
    )


def test_dos_casos_mismo_rut_pago_no_ejecutado_se_agrupan() -> None:
    rut = "12345678 9"
    casos = [
        _caso(id_caso="c1", rut=rut, fecha_reclamo=HOY - timedelta(days=5), fecha_denuncia=HOY - timedelta(days=2)),
        _caso(id_caso="c2", rut=rut, fecha_reclamo=HOY - timedelta(days=3), fecha_denuncia=HOY - timedelta(days=1)),
    ]
    activos, _ = filtrar_y_descartar(casos, {}, set(), HOY)
    grupos, individuales = agrupar(activos, {})
    assert len(grupos) == 1, f"esperaba 1 grupo, obtuvo {len(grupos)}"
    assert len(individuales) == 0, f"esperaba 0 individuales, obtuvo {len(individuales)}"
    assert grupos[0].monto_total_impugnado == 2_000_000
    print("OK: dos casos mismo RUT con pago_1 NO ejecutado se agrupan")


def test_dos_casos_mismo_rut_pago_1_ejecutado_no_se_agrupan() -> None:
    rut = "11111111 1"
    casos = [
        _caso(id_caso="a1", rut=rut, fecha_reclamo=HOY - timedelta(days=15), fecha_denuncia=HOY - timedelta(days=14)),
        _caso(id_caso="a2", rut=rut, fecha_reclamo=HOY - timedelta(days=3),  fecha_denuncia=HOY - timedelta(days=2)),
    ]
    pagos = {"a1": {1}}
    activos, _ = filtrar_y_descartar(casos, pagos, set(), HOY)
    grupos, individuales = agrupar(activos, pagos)
    assert len(grupos) == 0, f"esperaba 0 grupos, obtuvo {len(grupos)}"
    assert len(individuales) == 2, f"esperaba 2 individuales, obtuvo {len(individuales)}"
    print("OK: caso con pago_1 ejecutado no se agrupa con pendiente del mismo RUT")


def test_caso_sin_denuncia_dia_31_corrido_descartado() -> None:
    casos = [
        _caso(id_caso="d1", rut="22222222 2", fecha_reclamo=HOY - timedelta(days=31), fecha_denuncia=None),
    ]
    activos, descartados = filtrar_y_descartar(casos, {}, set(), HOY)
    assert len(activos) == 0
    assert len(descartados) == 1 and descartados[0].id_caso == "d1"
    print("OK: caso sin denuncia día 31 corrido es descartado")


def test_tres_casos_distintos_rut_individuales() -> None:
    casos = [
        _caso(id_caso=f"x{i}", rut=f"3000000{i} 0", fecha_reclamo=HOY - timedelta(days=i), fecha_denuncia=HOY)
        for i in range(1, 4)
    ]
    activos, _ = filtrar_y_descartar(casos, {}, set(), HOY)
    grupos, individuales = agrupar(activos, {})
    assert len(grupos) == 0
    assert len(individuales) == 3
    print("OK: tres casos con RUT distintos quedan como individuales")


def main() -> None:
    test_dos_casos_mismo_rut_pago_no_ejecutado_se_agrupan()
    test_dos_casos_mismo_rut_pago_1_ejecutado_no_se_agrupan()
    test_caso_sin_denuncia_dia_31_corrido_descartado()
    test_tres_casos_distintos_rut_individuales()
    print("\ntodos los tests del agrupador pasaron.")


if __name__ == "__main__":
    main()
