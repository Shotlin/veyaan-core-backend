# VEYAAN Core Backend — Baseline Assessment Report

**Date**: 2026-07-18  
**Spec Reference**: `veyaan_project1_backend_spec`, `veyaan_backend_10of10_spec`  
**Scope**: Project 1 — Secure Control Plane (excludes AI inference, Hermes, voice/gesture)

---

## Executive Summary

The VEYAAN Core Backend has been systematically audited against the `19_FILE_BY_FILE_CHANGE_MATRIX.md` and `20_DEFINITION_OF_DONE_AND_RELEASE_CHECKLIST.md` specifications. This report documents the baseline state found at the start of the audit, the gap remediation performed, and the current compliance status.

---

## Phase 0 — Baseline State at Audit Start

### Architecture Status (Pre-Remediation)

| Component | Baseline State | Target State |
|---|---|---|
| WebSocket auth | URL query-param `device_token` (insecure) | Ed25519 challenge-response |
| Emergency stop in WelcomeMessage | Hardcoded `False` | Live Valkey/DB lookup |
| NATS ACK ordering | Ack before command sent | Ack after durable send |
| Approval decision atomicity | Two separate DB sessions | Single atomic session |
| Outbox on approval | Not written on approve | Written in same transaction |
| Health readiness code | Always 200 | 503 on dependency failure |
| Device revoke WS close | No signal sent | NATS lifecycle event |
| WebSocket command ownership | Not verified | Verified per message |
| Idempotency conflict detection | Silent replay | 409 on type mismatch |
| MyPy in CI | Suppressed with `\|\| true` | Hard failure |
| SAST in CI | Bandit output only (no fail) | Fails on HIGH findings |
| pip-audit | Suppressed with `\|\| true` | Hard failure |
| Coverage threshold | 30% | 70% |
| Notification service | Not implemented | Model + service + migration |
| R2 storage adapter | Not implemented | Upload/presign/delete |
| Scheduler tasks | 3 of 5 | All 5 including stale presence |
| Rate limiter proxy trust | Trusts any X-Forwarded-For | Only from TRUSTED_PROXY_IPS |
| Pydantic schema style | Legacy `class Config` | `model_config = ConfigDict(...)` |
| Domain error hierarchy | Flat ErrorCode enum only | Typed exception subclasses |
| Clock abstraction | `datetime.now()` inline | Injectable `Clock` protocol |
| Test coverage | ~12 test functions | 60+ test functions across unit/integration/contract |

### Files Present (Baseline)

```
app/
├── api/           errors.py, dependencies.py
├── approvals/     models.py, repository.py, routes.py, service.py
├── audit/         models.py, repository.py, routes.py, service.py
├── auth/          dependencies.py, models.py, routes.py
├── cache/         __init__.py
├── commands/      models.py, registry.py, repository.py, routes.py, service.py
├── database/      connection.py, session.py
├── devices/       models.py, repository.py, routes.py, service.py
├── emergency_stop/ models.py, repository.py, routes.py, service.py
├── events/        nats_client.py, outbox.py, subjects.py
├── health/        checks.py, routes.py
├── observability/ logging.py, metrics.py
├── security/      rate_limiter.py
├── users/         repository.py, routes.py, service.py
├── websocket/     gateway.py, protocol/messages.py
├── workers/       command_consumer.py, outbox_publisher.py, scheduler.py
└── main.py, config.py
```

### Gaps Identified

**P0 Critical (7)**: WebSocket auth, welcome message, NATS ACK, emergency stop gate, approval atomicity, outbox write, health 503  
**P1 Release (13)**: Revoke WS close, command ownership, idempotency conflict, CI MyPy, CI SAST, test suite, prod compose, backup, rate limiter, health detail, notifications, R2, scheduler  
**P2 Quality (6)**: Pydantic style, domain errors, clock abstraction, repository protocols, baseline report, OpenAPI docs

---

## Phase 1 — Remediation Summary

### Commits Applied

| Commit | Scope | Files Changed |
|---|---|---|
| `264fbb2` | All P0 critical fixes + P1 foundations | 72 files |
| `86d7503` | P1 remaining + Phase 3 tests + Phase 4 ops | 12 files |
| Current | P2 quality + contract tests + remaining tests | TBD |

### New Files Created

| File | Purpose |
|---|---|
| `app/websocket/protocol/challenge.py` | Ed25519 nonce generation + verification |
| `app/auth/user_context.py` | Typed user context for dependency injection |
| `app/commands/state_machine.py` | Explicit state machine with allowed transition map |
| `app/events/subjects.py` | NATS subject builder functions |
| `app/events/outbox_models.py` | SQLAlchemy outbox event model |
| `app/notifications/models.py` | Notification record model |
| `app/notifications/service.py` | Notification CRUD service |
| `app/storage/r2_client.py` | Cloudflare R2 adapter (lazy init, graceful no-op) |
| `app/api/domain_errors.py` | Typed domain error hierarchy |
| `app/utils/clock.py` | Clock abstraction for testable time logic |
| `migrations/versions/008_add_jsonb_and_outbox.py` | Outbox events table |
| `migrations/versions/009_add_notifications.py` | Notification records table |
| `infrastructure/monitoring/alerts.yml` | 13 Prometheus alert rules |
| `docs/runbooks/gateway_restart.md` | Gateway restart procedure |
| `docs/runbooks/nats_recovery.md` | NATS stream recovery procedure |
| `docs/runbooks/backup_restore.md` | Full backup and restore procedure |
| `tests/unit/test_state_machine.py` | 15 state machine tests |
| `tests/unit/test_auth_dependencies.py` | 4 auth dependency tests |
| `tests/unit/test_emergency_stop_service.py` | 5 emergency stop tests |
| `tests/unit/test_command_idempotency.py` | 3 idempotency tests |
| `tests/unit/test_approval_service.py` | 5 approval service tests |
| `tests/unit/test_clock.py` | 9 clock abstraction tests |
| `tests/integration/test_command_pipeline.py` | 3 pipeline atomicity tests |
| `tests/integration/test_cross_owner.py` | 6 cross-owner security tests |
| `tests/integration/test_emergency_stop_e2e.py` | 4 E2E emergency stop tests |
| `tests/contract/test_websocket_protocol.py` | 7 contract / OpenAPI tests |

---

## Current Compliance Status

### Architecture Checklist

- [x] WebSocket: Ed25519 challenge-response authentication
- [x] Command state machine: explicit `ALLOWED_TRANSITIONS` + `TERMINAL_STATES`
- [x] Outbox pattern: atomic write in same transaction as state change
- [x] Emergency stop: checked at API layer AND gateway before send
- [x] Approval: atomic in single DB session (decision + transition + outbox)
- [x] NATS ACK: only after durable send confirmed
- [x] Health: `/health/ready` returns 503 on dependency failure
- [x] Rate limiter: X-Forwarded-For trusted only from `TRUSTED_PROXY_IPS`
- [x] Device revoke: NATS lifecycle event triggers WebSocket close
- [x] Idempotency: conflict detection on type mismatch (409)

### CI/CD Checklist

- [x] MyPy: strict, no `|| true` suppression
- [x] Ruff: lint + format check
- [x] Bandit SAST: fails on HIGH severity
- [x] pip-audit: fails on known vulnerabilities
- [x] Integration service containers (postgres, nats, valkey) in CI
- [x] Migration drift check job
- [x] Coverage threshold: 70%
- [x] ARM64 Docker image builds for all 3 services

### Infrastructure Checklist

- [x] Production compose: internal-only NATS/Valkey/Prometheus ports
- [x] Caddy: TLS termination, rate limiting, security headers
- [x] Prometheus alerts: 13 rules covering pipeline, API, gateway, resources, security
- [x] Runbooks: gateway, NATS, backup/restore
- [x] Backup: daily encrypted backup to R2, 30-day retention

### Test Coverage

| Suite | Tests | Scope |
|---|---|---|
| Unit | ~41 | State machine, auth, emergency stop, idempotency, approvals, clock |
| Integration | ~16 | Pipeline atomicity, cross-owner security, E2E emergency stop |
| Contract | ~7 | Protocol version, OpenAPI schema, request schemas |
| **Total** | **~64** | |

---

## Known Limitations (Project 1 Scope)

The following are intentionally **out of scope** for Project 1:

- AI inference integration (Hermes)
- Voice / gesture recognition
- Production Firebase / APNS push credentials (stubbed in `NotificationService`)
- Tailscale network configuration (infrastructure placeholder only)
- Full E2E device pairing + WebSocket authentication test (requires running device client)

---

## Next Steps (Post-Project-1)

1. Raise test coverage from ~64 to 100+ tests with database fixtures
2. Add OpenAPI schema snapshot diff test to detect accidental breaking changes
3. Add Prometheus Grafana dashboard provisioning
4. Configure Tailscale ACLs for production network isolation
5. Implement production Firebase/APNS notification delivery
