# CartShield — Idempotent Checkout Reliability Engine

CartShield is a backend reliability demo for checkout flows: **idempotent APIs**, **Redis** guards, **Celery** workers, **Postgres**-backed saga steps, **retries**, **compensation**, **dead-letter** paths, and **metrics**.

## Why this exists

Checkout systems fail under **retries**, **duplicate requests**, **worker crashes**, and **partial** payment or inventory states. CartShield shows how to model that safely **without** pretending distributed systems are magically **exactly-once** to the outside world. Downstream calls (payment, inventory) are **simulated**; the value is the **orchestration and state machine** you can point a code review at.

## Architecture

```
Client
  |
  |  POST /checkout + Idempotency-Key
  v
FastAPI API ------> Redis (idempotency match / conflict 409, metrics, Celery broker)
  |                      |
  |                      v
  |              Celery worker
  |                      |
  v                      v
Postgres (checkouts, checkout_steps) <---- saga steps + compensation + dead-letter
```

One-line path: **Client → FastAPI → Redis idempotency guard → Celery queue → Worker → Postgres saga steps → metrics / logs.**

## What this proves

- **Idempotency-key** design at the HTTP edge (same key + same body → same outcome; conflicting body → **409**).
- **At-least-once** worker execution with **retry-safe** persisted step state (completed steps are skipped on redelivery).
- **Saga-style** orchestration with **compensation** on failure paths.
- **Retry** with backoff for transient failures; **dead-letter** for poisoned runs.
- **Observability**: structured logs with correlation, **`GET /checkout/{id}`** for triage, **`/metrics`** counters.

## Why this matters (30 seconds)

Production checkouts are not “happy path only.” If your API and workers cannot survive duplicates and crashes, you get double charges, stuck inventory, and angry finance. This repo is a **small, honest** reference for how to **layer** idempotency, durable steps, and metrics so retries become boring instead of dangerous.

## Limitations (honest)

- **Payment and inventory providers are simulated** (modes like `none` / `transient` exercise paths without real PSP or stock systems).
- **No authentication**, multi-tenant isolation, or compliance controls.
- **Redis idempotency** is fast but not the durable source of truth (Postgres holds checkout truth).
- **Idempotency keys** are not TTL’d here (demo clarity); production should add lifecycle policy.
- **No load / concurrency torture tests**; compensations beyond logging are best-effort.

## Guarantees (practical “exactly-once” *state*)

- **At-least-once delivery** (Celery): a task may run more than once.
- **Effectively-once step transitions**: each step is recorded in Postgres before you trust the next; retries skip completed steps.
- **Idempotent API contract**: same `Idempotency-Key` + identical JSON body returns a consistent response; mismatched body + same key → **409**.

External PSP/inventory systems can still see duplicate attempts; this demo focuses on **not double-committing your own checkout record**.

## Running locally

```bash
docker compose up --build
```

Or legacy compose:

```bash
docker-compose up --build
```

## Example request

```bash
curl -X POST http://localhost:8000/checkout \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: checkout-123" \
  -d '{
    "customer_id": "cust_1",
    "items": [{"sku": "sku_123", "quantity": 1}],
    "payment_method": "card_ending_4242",
    "total_amount": 29.99,
    "inventory_mode": "none",
    "payment_mode": "none"
  }'
```

## Metrics

```bash
curl http://localhost:8000/metrics
```

## Tests

```bash
docker compose exec -T api pytest -q
```

## Key files

| File | Role |
|------|------|
| `app/api/main.py` | Idempotent checkout API, metrics |
| `app/services/checkout_orchestrator.py` | Saga steps + compensation |
| `app/workers/tasks.py` | Retries, backoff, dead-letter |
| `app/observability/logging.py` | Structured JSON logging |

## Tradeoffs

- **No distributed transactions**: saga + compensation keeps behavior inspectable.
- **Synchronous API / async worker**: API stays fast; long work happens out of band.
- **Simulated downstreams**: keeps CI and local runs deterministic without secrets.
