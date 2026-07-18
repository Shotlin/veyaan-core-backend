# VEYAAN Core Backend — Baseline Assessment Report (Phase 0)

This report details the baseline state of the `veyaan-core-backend` repository on the current branch before any modifications.

---

## 1. Git Environment & Baseline Metadata

- **Current Commit**: `1db9742f9e4bd33b934b07fb8d3568873133f8fc69980419df`
- **Branch**: `main`
- **Repository Remote**: `https://github.com/Shotlin/veyaan-core-backend.git`

---

## 2. Repository Tree

Below is the file structure of the workspace (excluding `.git`, `.venv`, and `__pycache__` directories):

```
.
├── Dockerfile
├── Dockerfile.gateway
├── Dockerfile.worker
├── QA_TEST_PLAN.md
├── README.md
├── REMEDIATION_SUMMARY.md
├── alembic.ini
├── app
│   ├── __init__.py
│   ├── api
│   │   ├── dependencies.py
│   │   ├── domain_errors.py
│   │   ├── errors.py
│   │   ├── middleware
│   │   │   ├── __init__.py
│   │   │   ├── error_handling.py
│   │   │   ├── request_id.py
│   │   │   └── tracing.py
│   │   └── responses.py
│   ├── approvals
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── audit
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── auth
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   ├── models.py
│   │   ├── routes.py
│   │   ├── supabase.py
│   │   └── user_context.py
│   ├── cache
│   │   └── __init__.py
│   ├── commands
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── registry.py
│   │   ├── repository.py
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── state_machine.py
│   ├── config.py
│   ├── database
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── session.py
│   ├── devices
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── emergency_stop
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── events
│   │   ├── __init__.py
│   │   ├── nats_client.py
│   │   ├── outbox.py
│   │   ├── outbox_models.py
│   │   └── subjects.py
│   ├── health
│   │   ├── __init__.py
│   │   ├── checks.py
│   │   └── routes.py
│   ├── main.py
│   ├── notifications
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── observability
│   │   ├── __init__.py
│   │   ├── logging.py
│   │   └── metrics.py
│   ├── protocols
│   │   ├── __init__.py
│   │   └── repositories.py
│   ├── security
│   │   ├── __init__.py
│   │   └── rate_limiter.py
│   ├── storage
│   │   ├── __init__.py
│   │   └── r2_client.py
│   ├── users
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── routes.py
│   │   └── service.py
│   └── utils
│       ├── __init__.py
│       └── clock.py
├── docker-compose.yml
├── docs
│   ├── reports
│   │   └── baseline_report.md
│   └── runbooks
│       ├── backup_restore.md
│       ├── gateway_restart.md
│       └── nats_recovery.md
├── infrastructure
│   ├── caddy
│   │   ├── Caddyfile
│   │   └── Caddyfile.prod
│   ├── compose
│   │   ├── docker-compose.dev.yml
│   │   └── docker-compose.prod.yml
│   ├── monitoring
│   │   ├── alerts.yml
│   │   └── prometheus.yml
│   ├── nats
│   │   └── jetstream.conf
│   └── scripts
│       ├── backup.sh
│       ├── bootstrap.sh
│       ├── harden.sh
│       └── restore.sh
├── migrations
│   ├── env.py
│   └── versions
│       ├── 001_initial_users.py
│       ├── 002_add_device_tables.py
│       ├── 003_add_command_tables.py
│       ├── 004_add_approvals_table.py
│       ├── 005_add_emergency_stops_table.py
│       ├── 006_add_audit_logs_table.py
│       ├── 007_add_state_transition_constraints.py
│       ├── 008_add_jsonb_and_outbox.py
│       └── 009_add_notifications.py
├── pyproject.toml
├── pytest.ini
├── requirements-dev.txt
├── requirements.txt
├── tests
│   ├── conftest.py
│   ├── contract
│   │   ├── __init__.py
│   │   └── test_websocket_protocol.py
│   ├── integration
│   │   ├── __init__.py
│   │   ├── test_approval_e2e.py
│   │   ├── test_command_pipeline.py
│   │   ├── test_cross_owner.py
│   │   ├── test_device_pairing.py
│   │   └── test_emergency_stop_e2e.py
│   ├── test_main.py
│   └── unit
│       ├── __init__.py
│       ├── test_approval_service.py
│       ├── test_auth_dependencies.py
│       ├── test_clock.py
│       ├── test_command_idempotency.py
│       ├── test_emergency_stop_service.py
│       └── test_state_machine.py
└── uv.lock
```

---

## 3. Import & Startup Failures

Two severe import/startup issues exist in the baseline codebase:

### Issue A: Python Version PEP 604 Syntax Incompatibility
When executed with **Python 3.9** (e.g. system default `/usr/bin/python3`), importing `app/utils/clock.py` fails:
```
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```
*Cause*: Python 3.9 does not support PEP 604 union syntax (e.g. `fixed_time: datetime | None = None`) without `from __future__ import annotations`. The project specifies `requires-python = ">=3.12"` in `pyproject.toml`, but system environment variables might route executions to legacy Python interpreters.

### Issue B: Missing Third-Party Dependency
When initiating Alembic (`alembic current` / `alembic upgrade`), the startup fails with:
```
ModuleNotFoundError: No module named 'strenum'
```
*Cause*: `app/api/errors.py` imports `StrEnum` from `strenum`:
```python
from strenum import StrEnum
```
However, `strenum` is not defined under `dependencies` in `pyproject.toml` nor listed in `requirements.txt`.

---

## 4. Ruff Linter & Formatter Results

### Ruff Lint Result
Ruff reports **104 errors** across the codebase. Most errors fall into:
- `I001`: Unsorted or unformatted import blocks
- `F401`: Unused imports (e.g. `unittest.mock.patch` in tests, `fastapi.HTTPException` in `test_auth_dependencies.py`)
- `F841`: Unused local variables (e.g. `result` in `test_emergency_stop_service.py:97`, `result_mock` in `test_approval_service.py:283`)

### Ruff Formatting Result
Running `ruff format --check .` reports format mismatches across multiple Python files because formatting configurations defined in `pyproject.toml` (`[tool.ruff] line-length = 100`) have not been fully adhered to.

---

## 5. MyPy Type Checker Result

Running `mypy .` fails immediately with:
```
app/api/middleware/error_handling.py: error: Source file found twice under different module names: "middleware.error_handling" and "app.api.middleware.error_handling"
```

Running type checks with explicit package bases (`mypy --explicit-package-bases .`) successfully avoids the duplicate file warning but reveals configuration limitations.

---

## 6. Pytest Collection & Execution Failure

Pytest crashes during collection and fails to execute any tests.

### Incompatibility under Python 3.12
When using `uv run` under Python 3.12.13, Pytest collection fails with:
```
AttributeError: 'Package' object has no attribute 'obj'
```
*Cause*: Incompatibility between `pytest-asyncio==0.23.3` and `pytest==8.3.3` (both pinned in `pyproject.toml`). Under Pytest 8.x, `Package` objects no longer expose the `.obj` attribute, causing the `pytest-asyncio` plugin hooks to crash.

- **Collected Tests**: 90 collected, 0 executed (collection crashed).
- **Coverage**: **0%** due to collection failure.

---

## 7. Alembic Migrations Validation

Running `alembic history` fails with a key lookup error:
```
KeyError: '008_add_jsonb_and_outbox'
```

### Analysis of the Migration Graph
- `008_add_jsonb_and_outbox.py` defines:
  ```python
  revision = '008'
  down_revision = '007'
  ```
- `009_add_notifications.py` incorrectly specifies:
  ```python
  down_revision = "008_add_jsonb_and_outbox"
  ```
Alembic looks for revision `'008_add_jsonb_and_outbox'`, but the identifier is simply `'008'`. This broken revision chain prevents Alembic from running any migration history commands or upgrades.

---

## 8. Docker Build Result (ARM64)

Docker image compilation on ARM64 successfully completed for all three components:

1. **API Image (`Dockerfile`)**: Successfully built (`veyaan-api:latest`)
2. **WebSocket Gateway Image (`Dockerfile.gateway`)**: Successfully built (`veyaan-gateway:latest`)
3. **Background Worker Image (`Dockerfile.worker`)**: Successfully built (`veyaan-worker:latest`)

---

## 9. Compose Configuration Validation

- **Development Stack (`docker-compose.yml`)**: Validated successfully.
- **Production Stack (`infrastructure/compose/docker-compose.prod.yml`)**: **Invalid**.
  - *Error*: `service "scheduler" depends on undefined service "neon": invalid compose project`
  - *Details*: The production stack has dependencies mapped to the `neon` container service (e.g. `depends_on: neon: condition: service_healthy`), but the `neon` service itself is omitted from the services block (as Neon PostgreSQL runs as an external serverless cloud platform in production).

---

## 10. Security Scan Result (Bandit)

Bandit reports **8 security issues** (7 Low, 1 Medium):

| Issue Code | Description | Severity | File / Line |
|---|---|---|---|
| **B105** | Hardcoded password string `INVALID_TOKEN` / `INVALID_CREDENTIAL` (false positive) | Low | `app/audit/schemas.py:43` |
| **B110** | Try, Except, Pass detected | Low | `app/websocket/gateway.py:58` |
| **B104** | Hardcoded bind to all interfaces (`0.0.0.0`) | Medium | `app/websocket/gateway.py:497` |
| **B110** | Try, Except, Pass detected | Low | `app/audit/service.py:12` |
| **B110** | Try, Except, Pass detected | Low | `app/users/service.py:12` |
| **B110** | Try, Except, Pass detected | Low | `app/workers/command_consumer.py:132` |
| **B110** | Try, Except, Pass detected | Low | `app/workers/outbox_publisher.py:79` |
| **B110** | Try, Except, Pass detected | Low | `app/workers/scheduler.py:172` |

---

## 11. Code Review Findings

### A. List of `pass` and Placeholders
Empty `pass` statements are used to stub unimplemented methods or bypass exceptions:
1. `app/database/connection.py:8` — Stub database closing hook.
2. `app/websocket/gateway.py:58` — Silently swallows WebSocket close exceptions.
3. `app/audit/service.py:12` — Empty audit log initialization.
4. `app/users/service.py:12` — Empty user service initialization.
5. `app/workers/command_consumer.py:132` — Empty background listener task loops.
6. `app/workers/outbox_publisher.py:79` — Empty publisher task loops.
7. `app/workers/scheduler.py:172` / `280` — Stubs for scheduled cron runner routines.
8. `app/commands/service.py:22` — Empty command handler setup.
9. `app/emergency_stop/service.py:18` — Empty emergency stop helper.
10. `app/approvals/service.py:32` — Empty approval workflow handler.
11. `app/devices/service.py:24` — Empty pairing flow helper.

### B. Duplicate Singletons & Client Configurations
- Valkey client imports remain standardized, but the NATS client connection does not share a single interface between the API router scope and worker scopes.

---

## 12. Mapping to Remediation Issues

The findings map directly to the P0, P1, and P2 issue catalog:

| Baseline Finding | Spec Issue Reference | Classification |
|---|---|---|
| Insecure token URL auth | **GAP-P0-1** | P0 Critical |
| Unverified command device ownership | **GAP-P1-2** | P1 Release |
| Missing `strenum` dependency | **GAP-P0-7** | P0 Critical |
| KeyError in migration chain | **GAP-P1-13** | P1 Release |
| Invalid Compose `neon` service reference | **GAP-P1-7** | P1 Release |
| Pytest Asyncio collection crash | **GAP-P1-6** | P1 Release |
| PEP 604 type syntax error on Python 3.9 | **GAP-P2-2** | P2 Quality |
