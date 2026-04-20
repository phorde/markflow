# Event Contracts

This document defines the v1 Redis Streams topology and delivery semantics.

## Stream Topology

- `mf.dispatch.v1`
  - Producer: API
  - Consumer group: Worker
  - Purpose: dispatch command intent
- `mf.progress.v1`
  - Producer: Worker
  - Consumer group: API
  - Purpose: execution progress observations
- `mf.result.v1`
  - Producer: Worker
  - Consumer group: API
  - Purpose: terminal or near-terminal execution results

## Required Event Envelope Fields

All stream payloads must include the following envelope fields:

- `event_id`
- `event_type`
- `schema_version`
- `job_id`
- `page_number` (nullable for job-level events)
- `attempt`
- `emitted_at` (RFC 3339 date-time)
- `correlation_id`
- `causation_id`

## Idempotency and ACK Semantics

- Delivery model is at-least-once.
- Consumers must be idempotent using `event_id` as primary deduplication key.
- API must ACK progress/result messages only after canonical reducer commit succeeds.
- Worker must ACK dispatch messages only after job acceptance and first progress emission attempt.
- Replayed events must not corrupt final state.

## Schema Authority

- Machine-readable schemas are versioned under `services/api/contracts/events/` and `services/worker/contracts/events/`.
- v1 event schemas are validated in unit tests and are CI-gated.
