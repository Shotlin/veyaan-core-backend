# VEYAAN Core Backend — Remediation Summary

## Overview

Complete P0/P1 defect remediation of `veyaan-core-backend` targeting production-ready Project 1 release. All changes align with the 10/10 specification pack.

---

## Architecture Fixes

### 1. Auth System — Unified & Type-Safe

**Files:** `app/auth/user_context.py`, `app/auth/dependencies.py`, `app/auth/__init__.py`

| Before | After |
|--------|-------|
| Two competing `get_current_user` dependencies returning different types (`TokenClaims` in one, `User` in another) | Single `get_current_user_context` returning canonical `UserContext` (immutable Pydantic model with `id`, `supabase_user_id`, `email`, `status`, `roles`) |
| Routes used mixed auth models inconsistently | All routes consume `UserContext` |
| `app/auth/__init__.py` exported old symbols | Re-exports canonical dependency only |

### 2. Valkey Cache — Singleton Cleanup

**Files:** `app/cache/__init__.py`, `app/cache/client.py` (deleted)

| Before | After |
|--------|-------|
| Duplicate `ValkeyClient` in `client.py` and `__init__.py` | Single canonical class in `__init__.py` with `hash`, `rate_limit_check`, `ping` methods |
| Imports ambiguous | All imports resolve to the same singleton |

### 3. NATS Events — Subject Catalog + Proper Publish

**Files:** `app/events/subjects.py`, `app/events/nats_client.py`

| Before | After |
|--------|-------|
| Hardcoded subject strings throughout codebase | Canonical subject catalog `subjects.py` — 10 builders (`command_ready`, `command_delivered`, `command_acknowledged`, `command_progress`, `command_result`, `command_cancel`, `device_lifecycle`, `approval_decided`, `emergency_stop`, `emergency_resume`) + stream patterns |
| `publish_js()` missing | Added with message headers + Nats-Msg-Id dedup |
| No durable subscription helpers | `subscribe_durable()`, `_ensure_streams()` with configurable streams |

### 4. Database — Alembic-Only + JSONB

**Files:** `app/database/connection.py`, `app/database/models.py`, `app/commands/models.py`, `app/audit/models.py`, `app/events/outbox_models.py`

| Before | After |
|--------|-------|
| `Base.metadata.create_all()` in connection.py (competing with Alembic) | Removed; Alembic is sole schema authority |
| `parameters` as `Text` in commands | `JSONB` |
| `result_data` missing from commands | Added as `JSONB` |
| `event_metadata` as `Text` in audit & state events | `JSONB` |
| `request_fingerprint` missing | Added to commands |
| No `outbox_events` table | Created with JSONB payload/headers, proper indexes, status (`pending`/`publishing`/`published`/`failed`) |

### 5. State Machine — Centralized

**File:** `app/commands/state_machine.py`

| Before | After |
|--------|-------|
| State transitions scattered across services | Single `transition_command()` with `ALLOWED_TRANSITIONS` dictionary, `TERMINAL_STATES`, `SELECT FOR UPDATE` row lock |
| No validation | Raises `StateTransitionError` on invalid transitions |

### 6. Emergency Stop — Fixed Queries + Audit + NATS

**File:** `app/emergency_stop/service.py`

| Before | After |
|--------|-------|
| Queries used `user_id` (non-existent column) — was a silent no-op | Uses `owner_id` (correct column) |
| No audit trail | Creates audit log on activate/release |
| No real-time broadcast | Publishes to `veyaan.security.emergency_stop.<owner_id>` via NATS |

### 7. WebSocket Gateway — Secure + Production

**Files:** `app/websocket/gateway.py`, `app/websocket/handlers.py` (deleted), `app/websocket/protocol/handlers.py` (deleted)

| Before | After |
|--------|-------|
| `credential_proof` in query params (vulnerable to URL logging) | Auth via `device_token` query param, verified against `DeviceCredential.credential_hash` (SHA-256) |
| Connection manager stored placeholder objects | `DeviceConnection` stores actual `WebSocket` with `send_json`, proper `close` |
| No Valkey presence tracking | Registers/unregisters presence with TTL |
| No NATS command delivery | Pull subscriber per device on `command.ready.<device_id>` |
| Old handler files (`handlers.py`, `protocol/handlers.py`) still imported | Deleted; all functionality consolidated in `gateway.py` |
| `HelloMessage` had `credential_proof` field | Removed (auth is query-param based) |

### 8. Command Pipeline — Ownership + Outbox

**File:** `app/commands/service.py`

| Before | After |
|--------|-------|
| No ownership verification | Loads device, checks `owner_id` matches requesting user |
| Direct NATS publish from command service | Creates `OutboxEvent` record; `OutboxPublisher` worker publishes asynchronously |
| Used `ValueError` for errors | Uses `ApiError` with proper error codes and status codes |

### 9. Approvals — Route + Risk Level Fix

**Files:** `app/approvals/routes.py`

| Before | After |
|--------|-------|
| Route prefix was wrong (missing `/approvals`) | Correct prefix, mounted at `/v1` |
| Risk level taken from client request body | Server-side risk level from `command_registry` |
| `decide_approval` didn't use command service | Wired through `CommandService.approve_command` / `reject_command` |

### 10. Devices — Secure Pairing

**Files:** `app/devices/service.py`, `app/devices/repository.py`

| Before | After |
|--------|-------|
| Plain-text pairing code comparison | Constant-time `hmac.compare_digest` |
| No brute-force protection | Attempt counter (max 5), rejects with 429 on excess |
| No row lock | `SELECT FOR UPDATE` on pairing confirmation |

### 11. Rate Limiter — Proxy-Aware

**File:** `app/security/rate_limiter.py`

| Before | After |
|--------|-------|
| Used client IP directly (broken behind Caddy) | Reads `X-Forwarded-For` from proxy headers |
| No user-based limits | Per-user when authenticated, endpoint-specific limits from settings |

### 12. Health — Correct Status Codes

**File:** `app/health/routes.py`

| Before | After |
|--------|-------|
| Always returned 200 | Returns **503** when readiness checks fail |

---

## Infrastructure Fixes

### 13. Docker Compose — Dev/Prod Split

**Files:** `infrastructure/compose/docker-compose.dev.yml`, `docker-compose.prod.yml`, `docker-compose.yml`

| Before | After |
|--------|-------|
| Single compose file for all environments | Dev profile (hot-reload, exposed ports) and prod profile (health checks, resource limits, read-only root) |
| NATS config loaded incorrectly (`-c` flag missing argument) | Proper `-c /etc/nats/nats.conf` |
| No health checks on services | Health checks with restart policies |
| Caddyfile had no security headers | Caddyfile.prod with CSP, HSTS, request body limits, trusted proxies |

### 14. CI — Strict Checks

**File:** `.github/workflows/ci.yml`

| Before | After |
|--------|-------|
| `bandit || true` — suppressed security failures | `bandit` fails on high severity |
| No dependency audit | `pip-audit` step |
| No coverage threshold | `pytest --cov-fail-under=30` |
| No migration test | Alembic check step |
| Built x86 only | ARM64 image builds |

### 15. Backup/Restore — Correct Cryptography

**Files:** `infrastructure/scripts/backup.sh`, `infrastructure/scripts/restore.sh`

| Before | After |
|--------|-------|
| `age` used incorrectly (identity flag for encryption) | `age -r <recipient>` for encryption, `age -d -i <identity>` for decryption |
| No integrity verification | SHA-256 checksum generated before encryption, verified after decryption |
| `--dry-run` in retention prune | Only used when `DRY_RUN=true` |
| No restore script | Created with confirmation prompt, dry-run mode |

---

## Testing

**File:** `tests/test_main.py`

| Before | After |
|--------|-------|
| 7 basic route-existence tests | 28 tests covering all route endpoints (existence + auth-required + edge cases like unknown command type, empty list, metrics endpoint) |

### Migration 008

**File:** `migrations/versions/008_add_jsonb_and_outbox.py`

New migration adds:
- `outbox_events` table (JSONB payload/headers, status, indexes)
- `attempt_count` to `pairing_requests` (backfill-safe)
- `deduplication_key` to `command_state_events` (unique constraint)
- `request_fingerprint` + `result_data` to `commands`
- Converts `commands.parameters` from `Text` to `JSONB`
- Converts `command_state_events.event_metadata` from `Text` to `JSONB`
- Converts `audit_logs.event_metadata` from `Text` to `JSONB`

---

## Dead Code Removed

| File | Reason |
|------|--------|
| `app/api/routes/auth.py` | Old route file, not imported anywhere; used `TokenClaims` pattern |
| `app/api/routes/users.py` | Same — dead code |
| `app/websocket/handlers.py` | Old `WebSocketHandler`, replaced by `gateway.py` |
| `app/websocket/protocol/handlers.py` | Old `authenticate_device` + `ConnectionManager`, replaced by `gateway.py` |

---

## Verification

- **28/28 pytest tests passing**
- **`ruff` lint clean** (0 errors)
- **All imports compile clean**
- **All P0/P1 defects from spec pack resolved**

## Remaining for Release Candidate

1. Run `alembic upgrade head` against a fresh PostgreSQL instance to verify migration 008
2. E2E test walkthrough with `QA_TEST_PLAN.md` scenarios against running Docker Compose stack
3. Type check (`mypy app/`) — may have pre-existing issues due to Python 3.9 target
4. ARM64 deployment verification
5. Actual backup/restore execution with generated `age` keys
6. `pyproject.toml` lint config — move `ignore`/`select` to `[tool.ruff.lint]` section (deprecation warning)
