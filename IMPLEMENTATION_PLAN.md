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
| Admin UI | SQLAdmin for admin CRUD views | Already implemented; Phase 7 extends it for events/DLQ/outbox. |

## 3. Decisions Still Needed

| # | Decision | Options | Chosen |
|---|---|---|---|
| 1 | Outbox cleanup window | Hours / days | 7 days retained, then archived (not yet implemented). |
| 2 | DLQ retention | Days / forever | 30 days, then archived to cold storage (not yet implemented). |
| 3 | Idempotency backend | Redis / PostgreSQL | PostgreSQL (`processed_events` table created, guard not yet implemented). |
| 4 | Metrics backend | Prometheus / Datadog / CloudWatch | Prometheus + Grafana (not yet implemented). |
| 5 | Tracing | OpenTelemetry / Jaeger / none | OpenTelemetry with optional Jaeger (not yet implemented). |
| 6 | Admin UI framework | SQLAdmin | SQLAdmin (extend existing admin layer in Phase 7). |
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

- SQLAdmin `ModelView` classes for `EventStoreModel` and `DeadLetterEventModel`.
- **Deferred to Phase 7.**

**Estimated effort:** 1–2 days.

---

### Phase 3: Dead-Letter Queue Inspection & Replay ✅ Implemented and verified (2026-07-23)

**Goal:** Make NATS DLQ actionable.

> **History:** this phase was previously marked complete but was **non-functional at
> runtime**. Five defects were found and fixed on 2026-07-23; the section below
> describes the code as it now stands. See §9.3 for the full root-cause analysis.

#### 3.1 Subject layout ✅

The DLQ subject space is **disjoint** from the events space. JetStream refuses to
create two streams whose subjects overlap (`err_code 10065`), so the original
`events.*.dlq` design could never work underneath `events.>`.

| Stream | Subjects | Retention |
|---|---|---|
| `EVENTS` | `events.>` | WORK_QUEUE |
| `EVENTS_DLQ` | `dlq.>` | LIMITS |

`events.ordering.order_created` dead-letters to `dlq.ordering.order_created`.
`_dlq_subject_for_subject()` / `_origin_subject_for_dlq_subject()` map between the
two, so the origin subject is always recoverable for replay.

#### 3.2 Explicit DLQ routing ✅

JetStream has **no server-side dead-letter routing** — once `max_deliver` is reached
it simply stops redelivering, and under WORK_QUEUE retention the unacked message
would sit in the stream forever, invisible. The application does the routing:

- `_handle_delivery_failure()` reads `msg.metadata.num_delivered`; below the limit it
  naks for another attempt, at the limit it dead-letters.
- `_dead_letter()` publishes the payload to the DLQ subject with headers
  (`Nats-Last-Error`, `X-Origin-Subject`, `X-Delivery-Count`), then acks the original
  **only after** the DLQ copy is durable. If the DLQ publish fails the message stays
  unacked and recoverable.
- `_route_poison_message()` sends undeserializable payloads straight to the DLQ
  without burning retries — deserialization is deterministic, so redelivery would
  fail identically.

#### 3.3 Persist DLQ events in PostgreSQL ✅

- `start_dlq_consuming()` pull-consumes `dlq.>` and persists each message to
  `DeadLetterEventModel`.
- The origin subject comes from the `X-Origin-Subject` header, falling back to
  mapping the DLQ subject back. It no longer requires the event class to still be
  importable, so renamed/deleted events remain replayable.
- Undecodable payloads are persisted verbatim with
  `event_class_path = "<unparsable>"` and the bytes preserved as
  `payload.raw_base64` (plus a readable `raw_preview`) rather than being discarded.
- A failed database write is retried with exponential backoff
  (`NATS_DLQ_CONSUMER_MAX_DELIVER`, default 5), then logged `CRITICAL`; the message
  survives in the LIMITS-retention DLQ stream for manual recovery.

#### 3.4 Admin API ✅

- `GET /api/v1/admin/dead-letter-events`
- `GET /api/v1/admin/dead-letter-events/{id}`
- `POST /api/v1/admin/dead-letter-events/{id}/replay`
- `POST /api/v1/admin/dead-letter-events/{id}/resolve`

#### 3.5 Replay/resolve logic ✅

- Deserialize event from `DeadLetterEventModel`.
- Publish to original subject via `event_bus.publish_raw(...)`.
- Mark `resolved_at`.

#### 3.6 Tests ✅

- `app/modules/event_outbox/tests/test_nats_dlq_routing.py` — 24 unit tests.
- `app/modules/event_outbox/tests/test_nats_dlq_integration.py` — 12 tests against a
  **real** JetStream server, marked `@pytest.mark.integration` and skipped when
  unreachable (`NATS_TEST_URL`, default `nats://localhost:4222`; the `nats` service
  in `db.yml` provides one).
- `app/core/tests/test_event_serializer.py` — expanded to 20 tests covering
  malformed wire payloads.

> **Do not replace the integration tests with mocks.** Three of the five defects
> (§9.3) were invisible to mock-based tests and were only caught by driving the real
> `nats-py` client.

**Actual effort:** ~1 day (including root-cause analysis of the five defects).

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

#### 7.2 SQLAdmin views

- Register SQLAdmin `ModelView` classes under `app/admin/` for:
  - `EventStoreModel`
  - `DeadLetterEventModel`
  - `EventOutboxModel`
- Provide read-only list/detail views plus replay/resolve actions via custom links or API calls.

#### 7.3 Break-glass admin guardrails

The SQLAdmin layer is a **superuser-only break-glass tool** for fixing data/model issues, not a business workflow UI. Because it bypasses domain use cases and the event bus, enforce the following guardrails:

| Concern | Why it still matters |
|---|---|
| **One-way dependency** | Make sure modules never import `app.admin`. Use `import-linter` to enforce it. |
| **Audit log** | Superusers can break things. You need to know who changed what and when. |
| **Security hardening** | Separate admin session secret, short session lifetime, CSRF, rate limiting on login. |
| **Read-only by default** | If possible, make the break-glass admin read-only and require an explicit toggle to edit. |
| **Runbook / approval** | Document when and why someone should use it. |

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

| # | Phase | Status |
|---|---|---|
| 1 | **Phase 1** — Outbox pattern | ✅ Done |
| 2 | **Phase 2** — Event store | ✅ Done |
| 3 | **Phase 3** — DLQ inspection & replay | ✅ Done and verified 2026-07-23 |
| 4 | **§9 High-severity fixes** — ordering pagination + mutable defaults | ❌ **Next — see §10** |
| 5 | **Phase 4** — Correlation IDs (cheap, enables tracing) | ❌ Open |
| 6 | **Phase 8** — Worker/scheduler hardening (reliability) | ❌ Open |
| 7 | **Phase 9** — NATS resilience (uptime) | ❌ Open |
| 8 | **Phase 5** — Idempotency (scale safety) | ❌ Open |
| 9 | **Phase 6** — Observability (debugging at scale) | ❌ Open |
| 10 | **Phase 7** — Admin UI (operations ergonomics) | ❌ Open |
| 11 | **Phase 10** — Schema validation (maturity) | ❌ Open |

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
- [x] A failing handler actually reaches the DLQ after `max_deliver` (verified against a real JetStream server).
- [x] A malformed payload is dead-lettered, not dropped, and does not kill the consumer.
- [x] A transient database outage does not discard a dead letter.
- [ ] Correlation IDs trace a request from API -> NATS -> handler.
- [ ] Re-publishing/replaying the same event does not duplicate side effects.
- [ ] Prometheus metrics expose publish/consume/DLW/outbox counts.
- [ ] Worker and scheduler handle SIGTERM gracefully.
- [ ] NATS reconnects automatically after outage.
- [ ] Unknown event schemas are rejected to DLQ.
- [x] All new code has tests; `uv run pytest -q` passes.

---

## 9. Root Cause Analysis: Static-Analysis Findings

A recent `ruff` + `mypy` pass surfaced **60 total issues** (25 ruff, 35 mypy). Roughly **10–12 are high-priority** because they reflect real runtime or design defects rather than style noise. The root causes cluster into five buckets:

### 9.1 BaseModelMixin type annotation is wrong

**File:** `app/core/database.py`

`BaseModelMixin` declares:

```python
created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), ...)
updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), ...)
deleted_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), ...)
```

`Mapped[DateTime]` refers to the SQLAlchemy **column type class**, not the Python `datetime` value type. Every model inheriting this mixin therefore appears to expose `DateTime` objects instead of `datetime` instances, which cascades into mypy errors in mappers that pass `model.created_at` / `model.updated_at` to domain entities typed as `datetime | None`.

**Impact:**
- Type-checker noise in `app/modules/notification/infrastructure/persistence/mapper.py` and `app/modules/ordering/infrastructure/persistence/mapper.py`.
- No runtime crash today because SQLAlchemy does return `datetime` objects, but the type contract is misleading and blocks strict typing.

**Fix direction:** change `Mapped[DateTime]` to `Mapped[datetime]` in `BaseModelMixin`.

### 9.2 Ordering module uses the wrong pagination contract

**Files:**
- `app/modules/ordering/use_cases/list_orders.py`
- `app/modules/ordering/api/router.py`
- `app/modules/ordering/domain/interfaces.py`
- `app/modules/ordering/infrastructure/persistence/repository.py`

The shared pagination types in `app/core/pagination.py` use **`offset`/`limit`**:

```python
@dataclass(frozen=True)
class PaginationParams:
    offset: int = 0
    limit: int = DEFAULT_PAGE_SIZE

@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    total: int
    offset: int
    limit: int
```

But the ordering module builds and reads `Page` objects using **`page`/`page_size`**:

```python
return Page(
    items=[...],
    total=total,
    page=pagination.page,
    page_size=pagination.page_size,
)
```

`PaginationParams` also lacks `page`/`page_size` attributes. Additionally, the ordering module uses `pagination: PaginationParams = PaginationParams()` as a mutable default in several places.

**Impact:**
- `GET /api/v1/orders` will raise `TypeError: Page.__init__() got an unexpected keyword argument 'page'` as soon as it is called.
- The mutable default can leak request-scoped pagination state between callers if the object is ever mutated.

**Fix direction:** align ordering pagination with the rest of the codebase (`offset`/`limit`) and replace the mutable default with `None` or a sentinel.

### 9.3 The DLQ was non-functional — five stacked defects ✅ ALL FIXED (2026-07-23)

**File:** `app/core/nats_bus.py` (plus `app/core/event_serializer.py`)

The original finding ("`ConsumerConfig` has no `dead_letter` parameter") was correct
but was only **one of five** independent defects. Fixing it alone would still have
left the DLQ permanently empty. Each was confirmed empirically against a live
NATS 2.11 JetStream server, not by reading alone.

| # | Defect | Symptom | Fix |
|---|---|---|---|
| 1 | `EVENTS_DLQ` claimed `events.*.dlq`, overlapping `events.>` | `err_code 10065`, swallowed by a blanket `except BadRequestError` logged at DEBUG. **The DLQ stream never existed.** | DLQ moved to its own `dlq.>` prefix; `_ensure_stream()` now distinguishes 10065/10058 and re-raises |
| 2 | `ConsumerConfig(dead_letter=…)` is not a field | `TypeError` before `pull_subscribe` — escaped the `BadRequestError` handler, propagated through `asyncio.gather` and **killed the whole worker at startup**. No events consumed at all. | Parameter removed |
| 3 | `durable` passed only inside `ConsumerConfig` | `err_code 10017 'consumer name in subject does not match durable name'`. nats-py overwrites `config.name` with a random NUID when `durable=` is omitted, so the API subject and request body disagree. **Consumer creation still failed after fixing #2.** | Pass `durable=` to `pull_subscribe`; also makes re-subscription idempotent across worker restarts |
| 4 | `start_consuming` awaited each `_start_consumer` sequentially | `_start_consumer` never returns (infinite fetch loop), so only the **first** registered event type ever got a consumer | Split into `_create_consumer` + `_consume_loop`, gathered concurrently |
| 5 | Nothing ever published to the DLQ subject | `msg.nak()` relied on non-existent server-side routing. After `max_deliver` NATS just stops; the message sat unacked in a WORK_QUEUE stream forever and `dead_letter_events` stayed empty | Explicit routing in `_handle_delivery_failure()` / `_dead_letter()` (see §3.2) |

**Why the tests were green throughout:** `test_nats_outbox.py` mocks the JetStream
context, and no test exercised `start_consuming` / `_start_consumer` at all. Defects
1, 2 and 3 are invisible to mock-based tests by construction.

### 9.3b Serializer let raw exceptions kill the consumer ✅ FIXED (2026-07-23)

**File:** `app/core/event_serializer.py`

Found while testing the DLQ path. `_handle_message` catches
`(EventSerializationError, KeyError, json.JSONDecodeError)`, but the serializer
raised other types that escaped, propagating out of `_consume_loop` — **one
malformed message would halt all event processing**.

| Input | Escaped as | Where |
|---|---|---|
| `b"\xff\xfe"` | `UnicodeDecodeError` | `from_json` |
| `b"[1,2]"` | `TypeError` | `from_json` |
| `{"event_class":"Foo"}` (no dot) | `ValueError` | `deserialize` |
| `{"event_class":123}` | `AttributeError` | `deserialize` |
| `{"event_class":""}` | `ValueError` | `deserialize` |

The `deserialize` cases are the more dangerous: they are valid JSON and clear
`from_json` entirely. Both functions now raise `EventSerializationError` for every
malformed input, which callers already route to the DLQ. Additionally, a payload
that is undeserializable is **dead-lettered rather than acked and dropped** — the
previous behaviour was silent data loss in both `_handle_message` and
`_persist_dlq_message`.

### 9.4 NATS JetStream context is accessed without null checks

**File:** `app/core/nats_bus.py`

`self._js: nats.js.JetStreamContext | None` is only validated inside `start_consuming()`. `_ensure_streams()` (line 118, 131) and `_start_consumer()` (line 312) dereference `self._js` without checking for `None`. The mypy errors `Item "None" of "JetStreamContext | None" has no attribute ...` are real null-safety gaps.

**Impact:**
- If `connect()` fails or these methods are called out of order, the worker crashes with `AttributeError` instead of a meaningful error.

**Fix direction:** centralise the null check (e.g., a `_require_js()` helper) and raise `RuntimeError("NATS JetStream not connected")` consistently.

### 9.5 JobStateMachine uses mutable class attributes

**File:** `app/modules/ordering/domain/state_machine.py`

```python
class JobStateMachine:
    TRANSITIONS = {...}
    FILE_EDITABLE_STATUSES = {PENDING, HOLD}
```

Both are mutable `dict`/`set` objects stored as class attributes.

**Impact:**
- Any code that mutates `TRANSITIONS` or `FILE_EDITABLE_STATUSES` (deliberately or accidentally) changes behaviour for all future callers across the process.

**Fix direction:** annotate them with `ClassVar[Mapping[...]]` / `ClassVar[frozenset[...]]` or freeze the collections (`MappingProxyType`, `frozenset`).

### 9.6 Summary table

| Root cause | Affected files | Severity | Runtime risk | Status |
|---|---|---|---|---|
| DLQ non-functional (5 defects, §9.3) | `app/core/nats_bus.py` | **High** | Worker would not start; DLQ permanently empty | ✅ Fixed 2026-07-23 |
| Serializer leaked raw exceptions (§9.3b) | `app/core/event_serializer.py` | **High** | One malformed message halts all event processing | ✅ Fixed 2026-07-23 |
| Ordering pagination uses `page`/`page_size` | `app/modules/ordering/use_cases/list_orders.py`, `api/router.py`, `domain/interfaces.py`, `infrastructure/persistence/repository.py` | **High** | `TypeError` on `GET /orders` | ❌ Open |
| Mutable `PaginationParams()` default | ordering interfaces/repository/use case | **High** | Shared mutable state across requests | ❌ Open |
| `BaseModelMixin` typed as `Mapped[DateTime]` | `app/core/database.py`, notification/ordering mappers | Medium | Type confusion, blocks strict typing | ❌ Open |
| `self._js` accessed without null checks | `app/core/nats_bus.py` | Medium | `AttributeError` if NATS not connected | ⚠️ Partly — new methods guard; `_ensure_streams` still unguarded |
| Mutable class attrs in `JobStateMachine` | `app/modules/ordering/domain/state_machine.py` | Medium | Global state corruption | ❌ Open |

**Current baseline (2026-07-23):** `ruff` 34 errors, `mypy` 33 errors, `pytest` 267
passing (255 + 12 skipped without a NATS server). The remaining open items above
account for most of what is left.

---

## 10. Next Session — Start Here

### 10.1 State as of 2026-07-23

Branch `feature/event-store-dlq`, **all work uncommitted**. Phases 1–3 are complete
and verified. Phases 4–10 are not started.

Run this first to confirm the starting point:

```bash
NATS_TEST_URL=nats://localhost:4222 uv run pytest -q   # expect 267 passed
uv run ruff check .                                    # expect 34
uv run mypy app                                        # expect 33
```

Integration tests need the `nats` service from `db.yml` (`docker compose -f db.yml up -d nats`).
Without it they skip and the suite reports 255 passed / 12 skipped.

### 10.2 Immediate priority — the two High-severity §9 bugs

**`GET /api/v1/orders` raises `TypeError` on the first call.** The ordering module
builds `Page(page=…, page_size=…)` while `app/core/pagination.py` defines `Page` with
`offset`/`limit`. This is a live, user-facing 500.

Files to change:
- `app/modules/ordering/use_cases/list_orders.py` (builds the `Page`, line ~22)
- `app/modules/ordering/api/router.py` (reads `page.page` / `page.page_size`, line ~57)
- `app/modules/ordering/domain/interfaces.py`
- `app/modules/ordering/infrastructure/persistence/repository.py`

Same pass: replace the mutable `pagination: PaginationParams = PaginationParams()`
defaults with `None` and a sentinel. There is currently **no test** covering
`GET /api/v1/orders`; add one, or the bug can silently return.

Estimated: ~1 hour for both, and it should clear a chunk of the ruff/mypy backlog.

### 10.3 Then Phase 4 (Correlation IDs)

Cheapest remaining phase and a prerequisite for useful tracing in Phase 6. Note the
plumbing already exists: `EventStoreModel.correlation_id` is a real column, currently
written as `None` at `nats_bus.py` in `_relay_outbox_row` and `_record_event_store`.
Phase 4 fills it in.

### 10.4 New settings introduced on 2026-07-23

All documented in `example.env`:

| Setting | Default | Purpose |
|---|---|---|
| `NATS_DLQ_SUBJECT_PREFIX` | `dlq` | **Must not** sit underneath `NATS_EVENTS_SUBJECT_PREFIX` — JetStream rejects overlapping stream subjects |
| `NATS_DLQ_CONSUMER_MAX_DELIVER` | `5` | Attempts to write a dead letter to PostgreSQL. Keep > 1 |
| `NATS_DLQ_RETRY_BASE_DELAY_SECONDS` | `5.0` | Backoff base between those attempts |
| `NATS_DLQ_RETRY_MAX_DELAY_SECONDS` | `300.0` | Backoff cap |

**Deployment note:** existing environments already have an `EVENTS` stream with
`events.>`, which is unchanged, so no migration is required. `EVENTS_DLQ` will be
created on the next worker start. If a stale `EVENTS_DLQ` exists with the old
`events.*.dlq` subjects, delete it first — `_ensure_stream()` now fails loudly on
config drift instead of silently continuing.

### 10.5 Known gaps deliberately left open

- **`_ensure_streams()` still dereferences `self._js` without a null check**
  (§9.4). New methods guard; this one was left to avoid scope creep.
- **Outbox relay is inline-only.** If NATS is down, rows accumulate in `event_outbox`
  with no background poller to drain them and no alerting. Plan §1.4 calls this
  "Option B, future".
- **`catalog/`, `payment/`, `promotion/` modules contain only stale `.pyc` files** —
  the source was deleted but the package directories remain. Restore or remove.
- **Phase 7 gaps:** no SQLAdmin views for `EventStoreModel` / `DeadLetterEventModel` /
  `EventOutboxModel`; no outbox-pending-count or stream/consumer-status endpoints; no
  `import-linter` contract; no admin audit log.
