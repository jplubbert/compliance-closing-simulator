# compliance-closing-simulator

Operational orchestrator that closes the regtech feedback loop: reads pending fraud cases from an IOC database, groups them by RUT under Chilean banking rules, queries [regtech-rag-chile](https://github.com/jplubbert/regtech-rag-chile) for legal deadlines, and emits a prioritized payment queue consumed by [deadline-chaser](https://github.com/jplubbert/deadline-chaser).

## Overview

A Chilean bank's LSC (Liquidación, Seguimiento y Control) team faces a daily question that nobody owns end-to-end:

> *"Of all the fraud cases currently open, which ones do we owe a payment on today, which ones must be justified, and which ones are still in a tentative window?"*

The answer is buried in three places. The IOC database has the cases. Ley 20.009 + the CMF E24 instructions have the rules. The team's spreadsheet has the executions. Reconciling them manually is what turns a quarterly report into a month of overtime.

This service does the reconciliation:

1. Reads the IOC table for pending cases.
2. Groups same-RUT cases that haven't been paid yet (consolidating amount and inheriting the most aggressive deadline).
3. Discards cases that missed the 30-corrido-day denuncia window (Art. 4 inc. 4).
4. Queries the regtech-rag-chile predictor for every remaining case/group → gets back legal deadlines with citations.
5. Classifies each deadline (`executed` / `overdue` / `urgent` / `upcoming` / `tentative`) and prioritizes the queue.
6. Exposes the queue over HTTP for downstream consumers (chasers, dashboards, audits).

The output is the queue LSC has to act on **today**, with every payment date pointing back to the specific paragraph of regulation that produced it.

Audience: LSC operators, compliance officers, and the AI agents that follow up with them.

## Architecture

```
                ┌─────────────────────────────────┐
                │   deadline-chaser (agent)       │
                │   pulls the queue, emails LSC   │
                └────────────┬────────────────────┘
                             │ HTTP
                             ▼
            ┌────────────────────────────────────┐
            │   FastAPI  (scripts/api.py)        │
            │   :8002                            │
            │   POST /generar-queue              │
            │   GET  /health                     │
            └─────────────┬──────────────────────┘
                          │
        ┌─────────────────▼──────────────────┐
        │   queue_builder                    │
        │   - state classification           │
        │   - business-day urgency window    │
        │   - priority sort                  │
        └─────────────────┬──────────────────┘
                          │
        ┌─────────────────▼──────────────────┐
        │   orquestador                      │
        │   - per case/group HTTP call       │
        │   - normalizes Deadline schema     │
        │   - DI for predictor (mockable)    │
        └─────────┬─────────────────┬────────┘
                  │                 │
                  │                 │ HTTP :8001
                  ▼                 ▼
        ┌─────────────────┐   ┌─────────────────────────┐
        │   agrupador     │   │  regtech-rag-chile      │
        │                 │   │  /predecir-cronograma   │
        │  - filter       │   │                         │
        │  - 30-day       │   │  - business-day arith   │
        │    denuncia     │   │  - UF resolver          │
        │    discard      │   │  - threshold split      │
        │  - same-RUT     │   │  - legal citations      │
        │    consolidate  │   │                         │
        └────────┬────────┘   └─────────────────────────┘
                 │
        ┌────────▼────────────────────────┐
        │   DuckDB (file-based)           │
        │                                 │
        │   casos_ioc                     │
        │   ejecuciones_pago              │
        └─────────────────────────────────┘
```

## Key features

- **Same-RUT consolidation** under the LSC grouping rule: claims from the same person whose first payment hasn't been executed are merged into a single deadline with the consolidated amount and the oldest `fecha_reclamo` as the clock anchor.
- **Denuncia window enforcement** (Art. 4 inc. 4 Ley 20.009): cases without `fecha_denuncia` past the 30-corrido-day window are surfaced as `descartado`, not silently kept.
- **Single source of truth for the law**: no business-day math, no UF threshold math, no citations are reimplemented here — every deadline is what regtech-rag-chile returns. If the regulation changes, only one repo updates.
- **Five-state queue classification**: `executed`, `overdue`, `urgent` (≤3 business days), `upcoming`, `tentative` (denuncia still inside the 30-day window). The chaser uses the state to decide email tone and frequency.
- **Dependency-injected orchestrator** so the unit tests can mock the predictor instead of requiring the regtech API to be running.
- **FastAPI surface** consumed by deadline-chaser, but also useful as a daily compliance-officer dashboard or as input to a regulatory-report generator.

## Tech stack

- Python 3.11+
- [DuckDB](https://duckdb.org/) (file-based, no server) for the synthetic IOC database
- FastAPI + Uvicorn for the HTTP layer
- [`httpx`](https://www.python-httpx.org/) for the regtech-rag-chile calls
- [`holidays-cl`](https://pypi.org/project/holidays/) for the urgency window (business-day diff)
- Pydantic + dataclasses for the schema

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/jplubbert/compliance-closing-simulator
cd compliance-closing-simulator
python -m venv venv
source venv/Scripts/activate          # Windows: venv\Scripts\activate.bat
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit RAG_BASE_URL if regtech-rag-chile is not at http://127.0.0.1:8001

# 3. Initialize the synthetic database
python scripts/setup_db.py
python scripts/seed_datos.py          # 200 synthetic cases with realistic distribution

# 4. (In another terminal) start regtech-rag-chile on :8001
#    See https://github.com/jplubbert/regtech-rag-chile

# 5. Serve the simulator
uvicorn scripts.api:app --port 8002 --host 127.0.0.1

# 6. Generate today's queue
curl -X POST http://127.0.0.1:8002/generar-queue \
  -H "Content-Type: application/json" \
  -d '{}'
```

## Project structure

```
compliance-closing-simulator/
├── core/
│   ├── modelo.py            CasoIOC, Grupo, Deadline dataclasses
│   ├── db.py                DuckDB connection
│   ├── utils.py             Chilean RUT generator (módulo 11)
│   ├── agrupador.py         Filter pending + denuncia discard + same-RUT grouping
│   ├── orquestador.py       Per-case calls to regtech-rag-chile predictor
│   └── queue_builder.py     State classification + priority sorting
├── scripts/
│   ├── setup_db.py          DuckDB schema bootstrap
│   ├── seed_datos.py        200 synthetic cases (mixed ATM, grouped, discarded, split)
│   ├── api.py               FastAPI surface
│   ├── test_agrupador.py    Grouping + discard rules (no DB, no RAG)
│   ├── test_orquestador.py  End-to-end with mocked predictor
│   └── test_integracion.py  Real flow with regtech-rag-chile on :8001
├── data/
│   └── casos_ioc.duckdb     (gitignored, regenerated by seed_datos.py)
├── requirements.txt
└── README.md
```

## Sample queue

Output of `POST /generar-queue` against the synthetic seed (200 cases, generated 2026-04-28):

```json
{
  "fecha_corte": "2026-04-28",
  "totales": {
    "vencidos": 115,
    "urgentes": 21,
    "por_vencer": 33,
    "tentativos": 0,
    "ejecutados": 10,
    "descartados": 20
  },
  "queue": [
    {
      "id_item": "caso_488cb2c330",
      "tipo": "individual",
      "rut": "59355025-7",
      "casos_incluidos": ["caso_488cb2c330"],
      "deadlines": [
        {
          "numero_pago": 1,
          "monto_aplicable": 1277525,
          "fecha_limite": "2026-03-13",
          "campo_e24": 26,
          "estado": "vencido",
          "fundamento_legal": {
            "ley_referencia": "Ley 20.009 Art. 5 inc. 1",
            "extracto": "Siempre que el monto reclamado sea igual o inferior al umbral...",
            "similitud": 0.69
          }
        }
      ]
    }
  ]
}
```

Every `fecha_limite` and every `fundamento_legal` is what regtech-rag-chile returned; this service only orchestrates and classifies.

## Integration with the rest of the platform

```
IOC database (synthetic DuckDB)
    │
    ▼
compliance-closing-simulator
    │  groups by RUT, applies denuncia window
    │
    ▼  HTTP
regtech-rag-chile  ── returns deadlines + legal citations
    │
    ▼
prioritized queue (this service's output)
    │
    ▼  HTTP
deadline-chaser  ── emails LSC, escalates, learns from replies
```

The three services compose over FastAPI. Each one is independently useful (the simulator on its own is a daily LSC dashboard; regtech-rag-chile on its own is a compliance Q&A surface; the chaser on its own is a generic regulatory follow-up agent), but they are designed to plug into each other and replace what used to be a manual quarterly process.

## Honest framing

This is **not** a multi-agent system. The original v0 of this project was framed as "multi-agent reconciliation with anomaly detection" and that framing was wrong. What this actually is:

- **Deterministic orchestration** (Python, no LLMs): grouping rules, denuncia-window enforcement, state classification, priority sort.
- **A trusted external knowledge base** (regtech-rag-chile): the only place where regulation is interpreted.
- **An agentic follow-up layer** (deadline-chaser): the only LLM-driven component, scoped to email composition and stateful follow-up.

Mixing those layers (e.g. asking an LLM to "decide what to pay today") would replace an auditable system with an unauditable one. The whole point of regulatory compliance is that every decision must be explainable to the regulator. So the LLM stays out of the decision and inside the conversation.

## Future work

- **Async batch to regtech-rag-chile**: today the orchestrator calls the predictor sequentially, which makes a 200-case queue take ~7 minutes. Switching to `httpx.AsyncClient` with a concurrency cap should bring it to ~30 seconds.
- **Tentative cases visible in the seed**: the current synthetic distribution leaves the `tentativo` state at 0. Adding a 6th category (no denuncia and < 30 corrido days) would make the five queue states observable end-to-end.
- **Pluggable IOC reader**: today DuckDB is hardcoded as the source of cases. Abstracting `read_pending_cases()` would let the same orchestrator run against a real bank's data warehouse without touching the rest of the pipeline.
- **Persistence of executions**: `ejecuciones_pago` is read-only seed data. Wiring `POST /registrar-pago` would close the loop and let the chaser update state on confirmed replies.
- **Multi-tenant queues**: today every case is in the same pool. A `cliente_id` partition would let the same service back several banks.

## License

MIT.
