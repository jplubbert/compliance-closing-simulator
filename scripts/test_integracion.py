"""Test de integración: requiere RAG en :8001 y simulador en :8002.

Pasos:
  1. Pega a /health del simulador.
  2. POST a /generar-queue del simulador (que internamente pega al RAG).
  3. Imprime totales + primeros 10 items con fundamento legal real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

SIM_URL = "http://127.0.0.1:8002"


def main() -> None:
    health = httpx.get(f"{SIM_URL}/health", timeout=5.0)
    health.raise_for_status()
    print(f"health: {health.json()}")

    resp = httpx.post(f"{SIM_URL}/generar-queue", json={}, timeout=600.0)
    resp.raise_for_status()
    data = resp.json()
    print(f"\nfecha_corte: {data['fecha_corte']}")
    print(f"totales: {data['totales']}")
    print(f"queue size: {len(data['queue'])}")
    print(f"\nPrimeros 10 items de la queue:")
    for i, item in enumerate(data["queue"][:10], start=1):
        print(f"\n[{i}] id={item['id_item']} tipo={item['tipo']} rut={item['rut']}")
        print(f"    casos_incluidos: {item['casos_incluidos']}")
        for d in item["deadlines"]:
            fund = d.get("fundamento_legal") or {}
            extracto = (fund.get("extracto") or fund.get("texto") or "")[:80]
            sim = fund.get("similitud") or fund.get("score")
            print(
                f"    pago {d['numero_pago']}: {d['fecha_limite']} "
                f"[{d['estado']}] CLP {d['monto_aplicable']:,} "
                f"campo_e24={d['campo_e24']} sim={sim}"
            )
            if extracto:
                print(f"      extracto: {extracto}...")


if __name__ == "__main__":
    main()
