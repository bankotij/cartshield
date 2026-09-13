# Checkout failure laboratory

## Current evidence

Idempotency, saga records and simulated providers exist.

## Next product increment — planned

Run concurrent duplicate requests and worker restarts against isolated Postgres/Redis; export a recovery timeline.

## Acceptance gate

Prove one committed checkout across duplicate delivery, payload conflict and worker restart; retain the trace.

A release also needs reproducible checks, useful empty/error states, keyboard/mobile review where applicable, and an inspectable example with appropriate data. Planned work above is not shipped functionality.
