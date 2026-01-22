# CartShield

## 1. Project Overview

CartShield demonstrates a reliability-oriented checkout flow with idempotent APIs, durable state, and retry-safe orchestration. It focuses on correctness and failure recovery for a single checkout pipeline.

What it does **not** solve:
- End-to-end payment authorization or real inventory management
- Multi-tenant isolation, RBAC, or compliance controls
- High-scale throughput optimization or global distribution

## 2. Architecture & Data Flow

**Components**
- **FastAPI API**: accepts checkout requests, enforces idempotency, and dispatches work
- **Celery worker**: executes a saga with retries and compensation
- **Postgres**: source of truth for checkout and step state
- **Redis**: idempotency tracking, metrics counters, and Celery broker

**ASCII diagram**

```
Client
  |
  v
FastAPI (POST /checkout) --- Redis (idempotency, metrics)
  |                                |
  v                                v
Postgres <--- Celery worker <--- Redis (broker)
  ^
  |
Saga steps: reserve -> charge -> create -> confirm
```

**Primary execution path**
1. Client calls `POST /checkout` with `Idempotency-Key`.
2. API checks Redis for key/payload hash match and returns 409 on conflict.
3. Checkout record is created (if missing) in Postgres and a Celery task is enqueued.
4. Worker runs each step, persisting step status and skipping completed steps on retry.
5. On success, checkout is marked `succeeded`; on failure, compensation runs and a dead-letter entry is recorded.

## 3. Design Principles

1. **Postgres as the source of truth**  
   Checkout and step state are persisted on every transition (`checkouts`, `checkout_steps`).

2. **Idempotency at the edge, determinism in state**  
   Redis guards input consistency while persisted state ensures deterministic responses.

3. **Retry-safe orchestration**  
   Each step is tracked independently and skipped if already completed.

4. **Failure clarity over silent recovery**  
   Failures are logged, metrics are updated, and poisoned checkouts are dead-lettered.

## 4. Critical Workflows

**Checkout orchestration**
1. Worker loads checkout and marks it `in_progress`.
2. For each step, the worker records step status before and after execution.
3. On transient or timeout errors, the task is retried with exponential backoff.
4. On permanent failure, compensating actions run in reverse order.
5. Checkout ends as `succeeded`, `failed`, or `dead_lettered`.

State is persisted in Postgres at each step boundary so retries can be safely re-run.

## 5. Failure Modes & Guarantees

**Realistic failures**
- Inventory or payment timeout
- Transient upstream errors
- Permanent upstream failures
- Worker crash mid-step

**System behavior**
- **Transient errors**: retried with exponential backoff up to a max limit.
- **Permanent errors**: no retries; compensation runs and checkout is dead-lettered.
- **Worker crash**: task redelivery (at-least-once), but completed steps are skipped.

**Guarantees**
- **At-least-once delivery** (Celery): a task may execute more than once.
- **Effectively-once state changes**: step status is persisted; completed steps are skipped.
- **Idempotent API**: same key + same payload returns the same checkout.

## 6. Testing Strategy

**What is tested**
- Idempotency behavior (same payload vs conflict)
- End-to-end success flow with metrics increment
- Permanent failure path and dead-letter status

**What is not tested**
- True downstream network failures (dependencies are simulated)
- Concurrency stress or large-scale performance
- Compensating action failures beyond best-effort logging

Rationale: tests target correctness of idempotency and orchestration boundaries without overfitting to simulated services.

## 7. Tradeoffs & Alternatives

- **No distributed transactions**: replaced with saga + compensation for clarity.
- **Redis-backed idempotency**: fast but not a durable source of truth.
- **No GET-by-id in original spec**: added for debugging and testability.

## 8. Operational Considerations

- **Logging**: JSON logs include correlation IDs from the idempotency key.
- **Metrics**: `/metrics` exposes success/retry/failure counters.
- **Debugging**: `GET /checkout/{id}` returns current status for triage.
- **Known risks**: idempotency keys have no TTL; compensations are best-effort.

## 9. Running Locally

```
docker-compose up --build
```

**Example checkout**
```
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

**Run tests**
```
docker-compose exec -T api pytest -q
```

## 10. Scope & Limitations

- Single checkout pipeline, no multi-order or split-payment flows
- Simulated downstream systems only
- No authentication, authorization, or PII handling
- Minimal operational hardening (no TTL or archival policies)
# CartShield

Production-grade checkout reliability demo focused on idempotency, saga-style orchestration, and failure recovery.

## Architecture

```
             +-----------------------+
             |     FastAPI API       |
             |  POST /checkout       |
             +-----------+-----------+
                         |
                         | Idempotency-Key
                         v
                +----------------+
                |     Redis      |
                | idempotency +  |
                | metrics + broker|
                +-------+--------+
                        |
                        v
                +---------------+        +----------------+
                |   Celery      |        |  Postgres      |
                |   Worker      |<-----> | checkout state |
                +-------+-------+        +----------------+
                        |
                        v
           +----------------------------+
           | Simulated Dependencies     |
           | inventory / payment        |
           +----------------------------+
```

## Guarantees (Practical Exactly-Once)

- **At-least-once delivery**: Celery may run a task more than once.
- **Effectively-once processing**: Each step writes its state to Postgres, and retries skip completed steps.
- **Idempotent API**: Same `Idempotency-Key` + identical payload returns the same response; conflicting payloads return a deterministic 409.

This is “practical exactly-once” because external calls can still be repeated, but the system prevents double-commit of checkout state.

## Failure Scenarios and Recovery

- **Timeouts / transient errors**: Worker retries with exponential backoff.
- **Permanent failures**: Saga triggers compensating actions.
- **Poisoned checkouts**: After max retries, checkout is moved to a dead-letter queue.
- **Compensation**: Inventory reservation and payment charge are compensated when downstream steps fail.

## Tradeoffs and Design Decisions

- **Postgres as source of truth**: Checkout state and step state are persisted for replay safety.
- **Redis for edge idempotency**: Faster lock-and-compare on `Idempotency-Key`.
- **Synchronous API / async worker**: API stays responsive; worker handles retries and compensation.
- **Simple JSON logs**: Structured logs with correlation IDs for tracing across API/worker.

## Running Locally

```
docker compose up --build
```

### Example Request

```
curl -X POST http://localhost:8000/checkout \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: checkout-123" \
  -d '{
    "customer_id": "cust_1",
    "items": [{"sku": "sku_123", "quantity": 1}],
    "payment_method": "card_ending_4242",
    "total_amount": 29.99,
    "inventory_mode": "none",
    "payment_mode": "transient"
  }'
```

### Metrics

```
curl http://localhost:8000/metrics
```

Returns:

```
{
  "success_count": 3,
  "retry_count": 2,
  "failure_count": 1
}
```

## Code Walkthrough (Key Files)

- `app/api/main.py`: Idempotent checkout API and metrics endpoint
- `app/services/checkout_orchestrator.py`: Saga steps + compensation
- `app/workers/tasks.py`: Retries, backoff, dead-letter queue
- `app/observability/logging.py`: Structured JSON logging

## Notes on Real-World Failures

- Compensations can fail; production systems often run compensations in separate queues and alert on stuck refunds/releases.
- Distributed transactions are avoided; we rely on persisted state and deterministic retries.
- Idempotency keys should have TTLs or lifecycle policies in production; this demo keeps them indefinitely for clarity.
