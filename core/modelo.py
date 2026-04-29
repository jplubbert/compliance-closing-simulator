"""Dataclasses del simulador."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class CasoIOC:
    id_caso: str
    rut_usuario: str
    fecha_aviso: date
    fecha_reclamo: date
    monto_total_impugnado: int
    operacion_objeto: str
    fecha_denuncia: date | None = None
    producto_afectado: str | None = None
    estado_denuncia: str | None = None
    fecha_entrega_respaldo: date | None = None


CODIGOS_OPERACION_ATM_AVANCE = {"04", "05"}


@dataclass
class Grupo:
    id_grupo: str
    rut_usuario: str
    casos: list[CasoIOC]

    @property
    def fecha_reclamo(self) -> date:
        return min(c.fecha_reclamo for c in self.casos)

    @property
    def fecha_aviso(self) -> date:
        return min(c.fecha_aviso for c in self.casos)

    @property
    def monto_total_impugnado(self) -> int:
        return sum(c.monto_total_impugnado for c in self.casos)

    @property
    def operacion_objeto(self) -> str:
        for c in self.casos:
            if c.operacion_objeto in CODIGOS_OPERACION_ATM_AVANCE:
                return c.operacion_objeto
        return self.casos[0].operacion_objeto

    @property
    def estado_denuncia(self) -> str | None:
        for c in self.casos:
            if c.estado_denuncia:
                return c.estado_denuncia
        return None

    @property
    def fecha_entrega_respaldo(self) -> date | None:
        respaldos = [c.fecha_entrega_respaldo for c in self.casos if c.fecha_entrega_respaldo]
        return min(respaldos) if respaldos else None

    @property
    def ids_casos(self) -> list[str]:
        return [c.id_caso for c in self.casos]


@dataclass
class Deadline:
    numero_pago: int
    monto_aplicable: int
    fecha_limite: date
    campo_e24: int
    fundamento_legal: dict[str, Any]
    estado: str = "por_vencer"
    dias_habiles_calculados: int | None = None
    feriados_considerados: list[str] = field(default_factory=list)
