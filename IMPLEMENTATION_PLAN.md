# Fast-Kit Messaging & Observability Production Hardening Plan

> **Overrides:** This document overrides the event-bus, background-job, and observability sections of the previous `IMPLEMENTATION_PLAN.md`. All other phases (auth, modules, file uploads, payment, shipping, etc.) remain valid unless they conflict with this plan.
>
> **Scope:** Bring fast-kit's NATS JetStream messaging layer to production parity with django-init's outbox + audit + dead-letter capabilities, while preserving fast-kit's single-layer operational model.

---

## 1. Goal

Make fast-kit's event bus, workers, and scheduler production-ready by adding:

1. Transactional atomicity between DB writes and event publication (outbox pattern).
2. Audit log / event store for every published event.
3. Dead-letter inspection and manual replay tooling.
4. Correlation ID propagation from HTTP request through handlers.
5. Idempotency / exactly-once handling.
6. Metrics, structured logging, and tracing.
7. Admin / operational UI for streams, consumers, DLQ, and event replay.
8. Hardened worker and scheduler processes.
9. NATS connection resilience.
10. Schema validation and event versioning.

---

## 2. Decisions Already Made

| Decision | Choice | Rationale |
|---|---|---|
| Event transport | NATS JetStream | Already implemented; one layer for events + tasks + scheduling. |
| DB | PostgreSQL | Existing choice; outbox and event store live here. |
| ORM | SQLAlchemy async | Existing choice. |
| Worker model | Separate container running `app/worker.py` | Already implemented. |
| Scheduler model | Separate container running `app/scheduler.py` | Already implemented. |
| Admin UI | Headless (API-first) with optional React-Admin/Refine later | No Django admin in FastAPI. |

## 3. Decisions Still Needed

| # | Decision | Options | Chosen |
|---|---|---|---|
| 1 | Outbox cleanup window | Hours / days | 7 days retained, then archived (not yet implemented). |
| 2 | DLQ retention | Days / forever | 30 days, then archived to cold storage (not yet implemented). |
| 3 | Idempotency backend | Redis / PostgreSQL | PostgreSQL (`processed_events` table created, guard not yet implemented). |
| 4 | Metrics backend | Prometheus / Datadog / CloudWatch | Prometheus + Grafana (not yet implemented). |
| 5 | Tracing | OpenTelemetry / Jaeger / none | OpenTelemetry with optional Jaeger (not yet implemented). |
| 6 | Admin UI framework | React-Admin / Refine / custom | React-Admin (not yet implemented). |
| 7 | Schema registry | Pydantic models only / Avro / JSON Schema | Pydantic models + registry (not yet implemented). |

---

## 4. Phase Plan

### Phase 1: Outbox Pattern (Highest Priority) ✅ Implemented

**Goal:** Guarantee that business writes and event publication are atomic.

**Implemented:**

#### 1.1 Add `event_outbox` SQLAlchemy models

**New files:**
- `app/modules/event_outbox/infrastructure/persistence/models.py`
  - `EventOutboxModel`
  - `EventStoreModel`
  - `DeadLetterEventModel`
  - `ProcessedEventModel` (for idempotency)
- `app/modules/event_outbox/infrastructure/persistence/repository.py`
- `app/modules/event_outbox/domain/interfaces.py`

**Fields:**

```python
class EventOutboxModel(BaseModelMixin, Base):
    id: Mapped[UUID]
    event_class_path: Mapped[str]
    payload: Mapped[dict]
    subject: Mapped[str]
    created_at, published_at, attempts

class EventStoreModel(BaseModelMixin, Base):
    id: Mapped[UUID]
    event_type: Mapped[str]
    event_class_path: Mapped[str]
    aggregate_id: Mapped[str | None]
    payload: Mapped[dict]
    correlation_id: Mapped[str]
    published_at

class DeadLetterEventModel(BaseModelMixin, Base):
    id: Mapped[UUID]
    event_class_path: Mapped[str]
    payload: Mapped[dict]
    error_message: Mapped[str]
    attempts: Mapped[int]
    created_at, resolved_at

class ProcessedEventModel(Base):
    idempotency_key: Mapped[str] (primary key)
    processed_at
```

#### 1.2 Refactor `NatsEventBus`

**File:** `app/core/nats_bus.py`

- Added `publish_durable(event, session: AsyncSession)`.
- `publish_durable` writes to `EventOutboxModel` using the provided session.
- Added `relay_pending_outbox(session)` which publishes pending rows to NATS and records them in `EventStoreModel`.
- Added `durable_unit_of_work(event_bus)` context manager in `app/core/database.py`:

```python
async with durable_unit_of_work(event_bus) as session:
    # business writes + publish_durable
    # commit happens here, then outbox relay via a separate session
```

#### 1.3 Update use cases

**Files:**
- `app/modules/ordering/use_cases/create_order.py`
- `app/modules/ordering/use_cases/transition_job_status.py`

- Use cases accept an optional `session: AsyncSession | None`.
- When `session` is provided, they call `event_bus.publish_durable(event, session)`.
- When `session` is `None` (unit tests / legacy), they fall back to `event_bus.publish(event)`.

**API dependencies:**
- `app/modules/ordering/api/dependencies.py` now provides a durable session via `get_durable_session`, a FastAPI dependency context manager.
- Write endpoints (`create_order`, `transition_job_status`) use the durable session.
- Read endpoints keep using `get_db`.

#### 1.4 Relay mechanism

**Chosen:** Option A (inline after commit) via `durable_unit_of_work`.

- The relay runs in a separate session after the business transaction commits.
- If NATS is unreachable, the row stays pending and its `attempts` counter is incremented; the HTTP request still succeeds.
- A future background poller (Option B) can be added for high-throughput scenarios without changing the outbox schema.

#### 1.5 Migration

**File:** `alembic/versions/0008_add_event_outbox.py`

Created tables: `event_outbox`, `event_store`, `dead_letter_events`, `processed_events`.

#### 1.6 Tests

- `app/modules/event_outbox/tests/test_outbox_repository.py`
- `app/modules/event_outbox/tests/test_nats_outbox.py`
- `app/core/tests/test_durable_unit_of_work.py`
- `app/modules/ordering/tests/test_create_order_durable.py`
- `app/modules/ordering/tests/test_transition_job_status_durable.py`
- `app/core/tests/test_event_bus.py` extended for `InMemoryEventBus.publish_durable`.

**Estimated effort:** 2–3 days.

---

### Phase 2: Event Store (Audit + Replay) ✅ Implemented

**Goal:** Every published event is logged immutably.

**Implemented:**

#### 2.1 Write path ✅

- `NatsEventBus.publish()` and `publish_durable()` append to `EventStoreModel`.
- Aggregate ID is extracted from the event payload; correlation ID is reserved for Phase 4.

#### 2.2 Read API ✅

**New files:**
- `app/modules/event_outbox/api/router.py`
- `app/modules/event_outbox/api/schemas.py`
- `app/modules/event_outbox/api/dependencies.py`

Endpoints:
- `GET /api/v1/admin/events` — list events (filter by type, aggregate_id).
- `GET /api/v1/admin/events/{event_id}` — single event.
- `POST /api/v1/admin/events/{event_id}/replay` — re-publish event to NATS.

#### 2.3 Admin UI (optional but recommended) ❌

- React-Admin resource for `EventStore` and `DeadLetterEvent`.
- **Deferred to Phase 7.**

**Estimated effort:** 1–2 days.

---

### Phase 3: Dead-Letter Queue Inspection & Replay ✅ Implemented

**Goal:** Make NATS DLQ actionable.

**Implemented:**

#### 3.1 Persist DLQ events in PostgreSQL ✅

- Added `NatsEventBus.start_dlq_consuming()` pull consumer that reads `events.*.dlq` and persists each message to `DeadLetterEventModel`.
- `NatsEventBus._handle_message` keeps using `msg.nak()` so NATS routes exhausted deliveries to the DLQ stream.

#### 3.2 Admin API ✅

- `GET /api/v1/admin/dead-letter-events`
- `GET /api/v1/admin/dead-letter-events/{id}`
- `POST /api/v1/admin/dead-letter-events/{id}/replay`
- `POST /api/v1/admin/dead-letter-events/{id}/resolve`

#### 3.3 Replay/resolve logic ✅

- Deserialize event from `DeadLetterEventModel`.
- Publish to original subject via `event_bus.publish_raw(...)`.
- Mark `resolved_at`.

**Estimated effort:** 1–2 days.

---

### Phase 4: Correlation ID Propagation

**Goal:** Trace a request across services and handlers.

#### 4.1 Middleware

**File:** `app/core/middleware/correlation.py`

- Read `X-Correlation-ID` header or generate UUID.
- Store in `contextvars` or Starlette `request.state`.

#### 4.2 Pass to events

- `_get_correlation_id()` reads from context var.
- Include correlation ID in NATS message headers.

#### 4.3 Worker context

- Worker reads NATS message header and sets context var before invoking handlers.

**Estimated effort:** 0.5–1 day.

---

### Phase 5: Idempotency / Exactly-Once Handling

**Goal:** Prevent duplicate handling on redelivery or replay.

#### 5.1 Add idempotency key to events

- Add `idempotency_key: str` to all domain events (base class or mixin).
- Key = `event_type:aggregate_id:uuid` or deterministic hash.

#### 5.2 Handler guard

- Decorator `idempotent(handler)`:
  - Checks `ProcessedEventModel`.
  - If not processed, runs handler and records key.
  - If processed, logs skip.

#### 5.3 Redis alternative

- If latency matters, cache processed keys in Redis with TTL.
- PostgreSQL as source of truth.

**Estimated effort:** 1–2 days.

---

### Phase 6: Observability

**Goal:** Visibility into publish/consume latency, errors, and DLQ size.

#### 6.1 Prometheus metrics

**File:** `app/core/metrics.py`

```python
EVENTS_PUBLISHED_TOTAL = Counter("events_published_total", "...", ["event_type"])
EVENTS_CONSUMED_TOTAL = Counter("events_consumed_total", "...", ["event_type"])
EVENTS_DLQ_TOTAL = Counter("events_dlq_total", "...", ["event_type"])
EVENT_HANDLER_DURATION = Histogram("event_handler_duration_seconds", "...", ["event_type"])
OUTBOX_PENDING_GAUGE = Gauge("outbox_pending_events", "...")
```

#### 6.2 Structured logging

- Use `structlog` or standard logging with JSON formatter.
- Include correlation ID, event type, aggregate ID in every log.

#### 6.3 Tracing

- OpenTelemetry middleware for FastAPI.
- Span around `publish()` and handler execution.
- Propagate trace context in NATS headers.

#### 6.4 Health checks

- Extend `/health` to report NATS connection status and DLQ size.

**Estimated effort:** 2–3 days.

---

### Phase 7: Admin / Operational UI

**Goal:** Operations staff can inspect and manage events without code.

#### 7.1 API endpoints

All under `/api/v1/admin/`:
- Events list/detail/replay
- Dead-letter list/replay/resolve
- Outbox pending count
- Stream/consumer status (read from NATS monitoring API)

#### 7.2 React-Admin (or Refine)

- Resources: `events`, `dead-letter-events`, `outbox`.
- Custom actions: Replay, Resolve.

**Estimated effort:** 3–5 days.

---

### Phase 8: Worker & Scheduler Hardening

**Goal:** Reliable background processing.

#### 8.1 Graceful shutdown

**Files:** `app/worker.py`, `app/scheduler.py`

- Handle `SIGTERM` / `SIGINT`.
- Stop fetching new messages, finish in-flight messages, then close NATS.

#### 8.2 Health endpoints

- Add `/health` to worker and scheduler (optional FastAPI apps or simple socket checks).

#### 8.3 Scheduler persistence

- Use a `scheduler_state` table or Redis key to track last run time.
- On restart, catch up missed intervals if business-critical.

#### 8.4 Worker scaling

- Ensure consumer durables are singleton-ish or idempotent.
- Support multiple worker containers sharing the same durable consumer group.

**Estimated effort:** 1–2 days.

---

### Phase 9: NATS Connection Resilience

**Goal:** Survive NATS restarts and network blips.

#### 9.1 Reconnect config

```python
await nats.connect(
    servers=NATS_URL,
    allow_reconnect=True,
    reconnect_time_wait=2,
    max_reconnect_attempts=60,
    connect_timeout=10,
    ping_interval=20,
    max_outstanding_pings=5,
)
```

#### 9.2 Circuit breaker

- If NATS is unavailable, queue events in `EventOutbox` and retry.
- `/health` fails when NATS is unreachable for too long.

**Estimated effort:** 0.5–1 day.

---

### Phase 10: Schema Validation & Event Versioning

**Goal:** Catch incompatible event changes early.

#### 10.1 Event registry

**File:** `app/core/event_registry.py`

- Map `event_type` -> Pydantic model class.
- Validate payload before publish and on consume.

#### 10.2 Versioning

- Add `version: int` to events.
- Consumers can register handlers per version.
- Reject unknown versions to DLQ.

**Estimated effort:** 2–3 days.

---

## 5. Implementation Order

Recommended sequence:

1. **Phase 1** — Outbox pattern (correctness is highest value).
2. **Phase 2** — Event store (auditability).
3. **Phase 4** — Correlation IDs (cheap, enables tracing).
4. **Phase 8** — Worker/scheduler hardening (reliability).
5. **Phase 9** — NATS resilience (uptime).
6. **Phase 3** — DLQ inspection & replay (operability).
7. **Phase 5** — Idempotency (scale safety).
8. **Phase 6** — Observability (debugging at scale).
9. **Phase 7** — Admin UI (operations ergonomics).
10. **Phase 10** — Schema validation (maturity).

---

## 6. Estimated Total Effort

| Phase | Effort |
|---|---|
| 1. Outbox pattern | 2–3 days |
| 2. Event store | 1–2 days |
| 3. DLQ replay | 1–2 days |
| 4. Correlation IDs | 0.5–1 day |
| 5. Idempotency | 1–2 days |
| 6. Observability | 2–3 days |
| 7. Admin UI | 3–5 days |
| 8. Worker/scheduler hardening | 1–2 days |
| 9. NATS resilience | 0.5–1 day |
| 10. Schema validation | 2–3 days |
| **Total** | **~14–24 days** |

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Outbox relay latency | Use inline relay for API path; monitor `outbox_pending_events`. |
| NATS DLQ fills up | Archive to PostgreSQL DLQ table; alert on DLQ size. |
| Idempotency key collisions | Use UUID + aggregate_id + event_type. |
| Worker double-consumption | Durable NATS consumers + idempotent handlers. |
| Schema drift | CI test that deserializes sample events against registry. |
| Admin UI not built | Use NATS CLI + API endpoints as fallback. |

---

## 8. Success Criteria

- [x] `publish_durable()` is atomic with business DB writes.
- [x] Events published durably are recorded in `EventStore` after relay.
- [x] Every event is queryable in `EventStore` via admin API.
- [x] Failed events are visible in `DeadLetterEvent` and replayable/resolveable via admin API.
- [ ] Correlation IDs trace a request from API -> NATS -> handler.
- [ ] Re-publishing/replaying the same event does not duplicate side effects.
- [ ] Prometheus metrics expose publish/consume/DLW/outbox counts.
- [ ] Worker and scheduler handle SIGTERM gracefully.
- [ ] NATS reconnects automatically after outage.
- [ ] Unknown event schemas are rejected to DLQ.
- [x] All new code has tests; `uv run pytest -q` passes.
