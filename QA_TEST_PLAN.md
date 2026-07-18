# VEYAAN Core Backend - QA Test Plan

## 1. Overview

This document defines the comprehensive testing strategy for the VEYAAN Core Backend (Project 1). It covers all testing layers required to validate the implementation against the Master Specification.

### 1.1 Scope
- **In Scope**: All API endpoints, WebSocket protocol, database migrations, NATS integration, Valkey cache, Supabase Auth integration, Docker deployment
- **Out of Scope**: LLM inference, Hermes reasoning, voice/gesture recognition, Creative Studio, browser automation, financial/trading features

### 1.2 Testing Philosophy
- **Shift-left**: Unit tests with development, integration tests in CI
- **Risk-based**: Focus on security, reliability, data integrity
- **Automation-first**: Manual testing only for exploratory/UX
- **Observability-driven**: Structured logs, metrics, traces in all tests

### 1.3 Technology Stack for Testing
| Layer | Tool | Purpose |
|-------|------|---------|
| Unit/Integration | pytest + pytest-asyncio | Python service tests |
| API Contract | playwright (TypeScript) | REST/WebSocket E2E |
| Load/Stress | k6 | Performance/soak testing |
| Security | custom + OWASP ZAP | Auth, rate limit, injection |
| Contract | pact / schemathesis | API schema validation |

---

## 2. Test Strategy by Layer

### 2.1 Unit Tests (Target: 80% coverage)
| Module | Coverage Target | Key Areas |
|--------|----------------|-----------|
| Auth | 90% | JWT verification, user mapping, token refresh |
| Devices | 85% | Pairing, credentials, revocation, presence |
| Commands | 90% | Registry, validation, idempotency, state machine |
| Approvals | 90% | Nonce, expiry, replay protection, command resume |
| Emergency Stop | 95% | Activation, release, broadcast, command blocking |
| Audit | 80% | Log creation, query, redaction |
| WebSocket | 85% | Protocol, auth, message routing, heartbeat |

### 2.2 Integration Tests
| Area | Scenarios |
|------|-----------|
| Neon PostgreSQL | User mapping, device CRUD, command transactions, outbox pattern |
| NATS JetStream | Publish/consume, durability, redelivery, consumer groups |
| Valkey | Presence, rate limiting, locks, cache TTL |
| Supabase Auth | JWT verification, JWKS rotation, token expiry |
| WebSocket | Auth, heartbeat, command delivery, ack/result |

### 2.3 Contract Tests
- OpenAPI schema validation for all REST endpoints
- WebSocket message schema validation (JSON Schema)
- NATS subject schema validation

### 2.4 End-to-End Tests
| ID | Scenario | Priority |
|----|----------|----------|
| E2E-001 | Low-risk command (system.ping) | P0 |
| E2E-002 | Approval command (app.open_test) | P0 |
| E2E-003 | Rejection flow | P0 |
| E2E-004 | Emergency stop activation/release | P0 |
| E2E-005 | Idempotency (duplicate key) | P0 |
| E2E-006 | NATS restart resilience | P1 |
| E2E-007 | Backend restart state recovery | P1 |
| E2E-008 | Device revocation blocks WebSocket | P0 |

---

## 3. Test Cases by Feature

### 3.1 Positive API Test Cases

#### Authentication
| ID | Endpoint | Scenario | Expected |
|----|----------|----------|----------|
| AUTH-001 | GET /v1/auth/me | Valid token → 200, user profile |
| AUTH-002 | GET /v1/auth/verify | Valid token → 200, {valid: true} |
| AUTH-003 | Invalid token | 401, INVALID_TOKEN |
| AUTH-004 | Expired token | 401, EXPIRED_TOKEN |

#### Devices
| ID | Endpoint | Scenario | Expected |
|----|----------|----------|----------|
| DEV-001 | POST /v1/devices/pair | Valid data → 201, pairing_code, expires_at |
| DEV-002 | POST /v1/devices/pair/{id}/confirm | Owner confirms → 200, device_id, credential |
| DEV-003 | GET /v1/devices | Owner → 200, device list with presence |
| DEV-004 | DELETE /v1/devices/{id} | Owner → 200, revoked, WS closed |
| DEV-005 | Pairing expiry | 10 min → 400 PAIRING_EXPIRED |
| DEV-006 | Duplicate pair | 409 CONFLICT |

#### Commands
| ID | Endpoint | Scenario | Expected |
|----|----------|----------|----------|
| CMD-001 | POST /v1/commands (system.ping) | 201, command_id, task_id, state=queued |
| CMD-002 | POST /v1/commands (app.open_test) | 201, state=awaiting_approval |
| CMD-003 | POST /v1/commands (system.emergency_stop_test) | 201, state=awaiting_approval |
| CMD-003 | GET /v1/commands/{id} | 200, full command with state history |
| CMD-004 | POST /v1/commands/{id}/cancel | 200, cancelled=true |
| CMD-005 | Idempotency | Same key → same command_id |
| CMD-006 | Emergency stop active | 400 EMERGENCY_STOP_ACTIVE |

#### Approvals
| ID | Endpoint | Scenario | Expected |
|----|----------|----------|----------|
| APR-001 | GET /v1/approvals | 200, pending approvals |
| APR-002 | POST /v1/approvals/{id}/approve | Valid nonce → 200, status=approved |
| APR-003 | POST /v1/approvals/{id}/reject | Valid nonce → 200, status=rejected |
| APR-004 | Expired approval | 400, APPROVAL_EXPIRED |
| APR-005 | Replay nonce | 400, INVALID_DECISION_NONCE |

#### Emergency Stop
| ID | Endpoint | Scenario | Expected |
|----|----------|----------|----------|
| EST-001 | POST /v1/emergency-stop/activate | 201, active=true, published to NATS |
| EST-002 | POST /v1/emergency-stop/release | 200, active=false |
| EST-003 | Command during active stop | 400, EMERGENCY_STOP_ACTIVE |

#### Audit
| ID | Endpoint | Scenario | Expected |
|----|----------|----------|----------|
| AUD-001 | GET /v1/audit/logs | 200, paginated |
| AUD-002 | Filters (category/action/device/date) | 200, filtered |

---

### 3.2 Negative API Test Cases

| ID | Scenario | Expected |
|----|----------|----------|
| NEG-AUTH-001 | Expired JWT | 401, EXPIRED_TOKEN |
| NEG-AUTH-002 | Malformed JWT | 401, INVALID_TOKEN |
| NEG-AUTH-003 | Wrong issuer/audience | 401, INVALID_TOKEN |
| NEG-AUTH-004 | Missing Authorization header | 401, INVALID_TOKEN |
| NEG-VAL-001 | Missing required fields | 422, VALIDATION_ERROR |
| NEG-VAL-002 | Invalid UUID | 422, VALIDATION_ERROR |
| NEG-VAL-003 | Unknown command type | 400, INVALID_COMMAND_TYPE |
| NEG-VAL-004 | Invalid risk level | 422, VALIDATION_ERROR |
| NEG-VAL-005 | Expired command submission | 400, COMMAND_EXPIRED |
| NEG-AUTHZ-001 | Access another user's device | 403, FORBIDDEN |
| NEG-AUTHZ-002 | Decide another user's approval | 403, FORBIDDEN |
| NEG-AUTHZ-003 | Cancel another user's command | 403, FORBIDDEN |
| NEG-BIZ-001 | Approve already approved | 400, APPROVAL_ALREADY_DECIDED |
| NEG-BIZ-002 | Replay approval nonce | 400, INVALID_DECISION_NONCE |
| NEG-BIZ-003 | Decide expired approval | 400, APPROVAL_EXPIRED |
| NEG-BIZ-004 | Cancel completed command | 400, COMMAND_NOT_CANCELLABLE |
| NEG-BIZ-005 | Command during emergency stop | 400, EMERGENCY_STOP_ACTIVE |
| NEG-BIZ-006 | Idempotency conflict | 409, IDEMPOTENCY_CONFLICT |
| NEG-DEV-001 | Pair already paired device | 409, CONFLICT |
| NEG-DEV-002 | Confirm expired pairing | 400, PAIRING_EXPIRED |
| NEG-DEV-003 | Invalid pairing code | 400, PAIRING_INVALID |
| NEG-DEV-004 | Revoked device WS connect | 4002 close code |
| NEG-RATE-001 | Exceed auth rate limit | 429, RATE_LIMITED |
| NEG-RATE-002 | Exceed command rate limit | 429, RATE_LIMITED |

---

### 3.3 WebSocket Protocol Tests

#### Connection & Authentication
| ID | Scenario | Expected |
|----|----------|----------|
| WS-001 | Valid credentials + hello | 101, welcome message |
| WS-002 | Invalid credential proof | 4004 close |
| WS-003 | Revoked device | 4002 close |
| WS-004 | Unsupported protocol version | 4000 close |
| WS-005 | Duplicate connection | Old: 4000 close, New: success |

#### Message Exchange
| ID | Scenario | Expected |
|----|----------|----------|
| WS-010 | Heartbeat | Presence updated in Valkey |
| WS-011 | Command acknowledge | NATS event published |
| WS-012 | Command progress | NATS event published |
| WS-013 | Command result | NATS event published |
| WS-014 | Status update | Valkey presence updated |

#### Protocol Compliance
| ID | Scenario | Expected |
|----|----------|----------|
| WS-020 | Unsupported message type | Error response, connection stays |
| WS-021 | Message > 1MB | 4003 close |
| WS-022 | Invalid JSON | 4003 close |
| WS-023 | Missing required fields | 4003 close |

#### Emergency Stop via WebSocket
| ID | Scenario | Expected |
|----|----------|----------|
| WS-030 | Emergency stop active | EmergencyStopMessage received |
| WS-031 | Emergency stop released | ResumeMessage received |

---

### 3.4 Stress/Load Test Scenarios

| ID | Scenario | Target | Success Criteria |
|----|----------|--------|------------------|
| LOAD-001 | 100 concurrent device connections | 100 devices | All connect < 5s, no drops |
| LOAD-002 | 1000 commands/minute | 1000 cmd/min | P99 latency < 500ms |
| LOAD-003 | 100 concurrent approvals | 100 concurrent | All processed < 2s |
| LOAD-005 | Emergency stop during load | 1000 cmd queued | All blocked, none delivered |
| LOAD-006 | Sustained load (30 min) | 500 cmd/min | No memory leaks, stable latency |
| LOAD-007 | Device reconnection storm | 100 reconnects | All reconnect < 10s |

---

## 4. Test Infrastructure

### 4.1 Directory Structure
```
qa/
├── playwright/
│   ├── fixtures/
│   │   ├── auth.ts
│   │   ├── devices.ts
│   │   └── ws.ts
│   ├── tests/
│   │   ├── api/
│   │   │   ├── auth.spec.ts
│   │   │   ├── devices.spec.ts
│   │   │   ├── commands.spec.ts
│   │   │   ├── approvals.spec.ts
│   │   │   ├── emergency_stop.spec.ts
│   │   │   └── audit.spec.ts
│   │   ├── websocket/
│   │   │   ├── connection.spec.ts
│   │   │   ├── messages.spec.ts
│   │   │   └── emergency_stop.spec.ts
│   │   ├── stress/
│   │   │   ├── load.test.ts
│   │   │   └── stress.test.ts
│   │   └── security/
│   │       ├── auth.spec.ts
│   │       └── rate_limit.spec.ts
│   ├── utils/
│   │   ├── api-client.ts
│   │   ├── ws-client.ts
│   │   ├── test-data.ts
│   │   └── supabase-helper.ts
│   ├── playwright.config.ts
│   └── package.json
├── load/
│   ├── k6/
│   │   ├── scenarios.js
│   │   └── thresholds.js
│   └── locust/
        └── locustfile.py
├── reports/
└── scripts/
    ├── run-tests.sh
    ├── run-load.sh
    └── generate-report.py
```

### 4.2 CI/CD Integration
```yaml
# .github/workflows/qa.yml
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: veyaan
          POSTGRES_PASSWORD: dev_password
          POSTGRES_DB: veyaan_test
      nats:
        image: nats:2.10-alpine
        ports: [4222, 8222]
      valkey:
        image: valkey/valkey:8-alpine
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd qa/playwright && npm ci && npx playwright install
      - run: cd qa/playwright && npm run test
```

---

## 5. Test Data Management

### Test Data Strategy
- **Isolation**: Each test run uses unique IDs (UUIDv4)
- **Cleanup**: Automatic cleanup after each test suite
- **Seeding**: Minimal seed data via fixtures
- **Isolation**: Separate test DB or transaction rollback per test

### Test Data Examples
```typescript
// test-data.ts
export const testUser = {
  email: `test-${uuidv4()}@veyaan.ai`,
  password: 'TestPass123!',
};

export const testDevice = {
  display_name: 'Test MacBook Pro',
  device_type: 'macbook',
  operating_system: 'macOS 14.5',
  app_version: '1.0.0',
  device_public_identity: 'test-public-key-123',
};

export const testCommands = {
  ping: { command_type: 'system.ping', parameters: {} },
  status: { command_type: 'device.get_status', parameters: {} },
  openApp: { command_type: 'app.open_test', parameters: { app_bundle_id: 'com.test.app' } },
  screenshot: { command_type: 'system.take_test_screenshot', parameters: { format: 'png' } },
  emergencyTest: { command_type: 'system.emergency_stop_test', parameters: { reason: 'test' } },
};
```

---

## 6. Execution Strategy

### 6.1 CI/CD Integration
```yaml
# .github/workflows/qa.yml
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: veyaan
          POSTGRES_PASSWORD: dev_password
          POSTGRES_DB: veyaan_test
      nats:
        image: nats:2.10-alpine
        ports: [4222, 8222]
      valkey:
        image: valkey/valkey:8-alpine
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: cd qa/playwright && npm ci && npx playwright install
      - run: cd qa/playwright && npm run test
      - uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: qa/playwright/test-results/
```

### 6.2 Local Execution
```bash
# Run all tests
cd qa/playwright && npm run test

# Run specific suite
npm run test:api
npm run test:ws
npm run test:stress

# Run with UI
npm run test:ui

# Load test
cd ../load/k6 && k6 run scenarios.js

# Generate report
python scripts/generate-report.py
```

---

## 7. Reporting & Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Test Pass Rate | 100% | < 100% = fail |
| API P99 Latency | < 500ms | > 1s = warn |
| WebSocket Connect Time | < 2s | > 5s = warn |
| Command E2E Latency | < 1s | > 3s = warn |
| Error Rate | 0% | > 1% = fail |
| Memory Growth (30min) | < 50MB | > 100MB = warn |
| CPU Usage | < 50% | > 80% = warn |

### Report Outputs
- **HTML Report**: Playwright HTML report with screenshots/traces
- **JUnit XML**: For CI integration
- **JSON Summary**: For dashboards
- **Load Test**: k6 HTML report + JSON

---

## 8. Risk Assessment & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| NATS unavailable during test | Medium | High | Mock NATS in unit tests, real NATS in CI |
| Supabase rate limits | Low | Medium | Use test project, cache tokens |
| Flaky WebSocket tests | Medium | Medium | Retry logic, explicit waits |
| Rate limit interference | Medium | Medium | Separate test keys/IPs |
| Database state leakage | Low | High | Transaction rollback per test |

---

## 9. Acceptance Criteria

| Criterion | Pass Condition |
|-----------|----------------|
| All P0 tests pass | 100% pass rate |
| Load test thresholds met | All latency/error thresholds met |
| No high/critical security findings | 0 high/critical |
| Load test stability | No crashes, memory leaks |
| Documentation complete | All test cases documented |

---

## 10. Appendix: Test Execution Checklist

- [ ] Infrastructure up (PostgreSQL, NATS, Valkey, Supabase)
- [ ] Database migrations applied
- [ ] Test data seeded
- [ ] Smoke tests pass
- [ ] Positive API tests pass
- [ ] Negative API tests pass
- [ ] WebSocket tests pass
- [ ] E2E flow tests pass
- [ ] Security tests pass
- [ ] Load tests pass thresholds
- [ ] Stress tests show resilience
- [ ] Reports generated and archived

---

*Document Version: 1.0*  
*Last Updated: 2025-01-18*  
*Owner: QA Team*