# VEYAAN Core Backend

Core backend infrastructure for VEYAAN Project 1 - secure device command pipeline.

## Technology Stack

- **API Framework**: FastAPI with Python 3.12
- **Database**: Neon PostgreSQL (source of truth)
- **Authentication**: Supabase Auth (identity provider)
- **Event Bus**: NATS JetStream (durable event delivery)
- **Cache/Locks**: Valkey (Redis-compatible)
- **Device Communication**: Secure WebSocket
- **Reverse Proxy**: Caddy (TLS termination)
- **Deployment**: Docker Compose on Ubuntu ARM64
- **Target Server**: Oracle Ampere A1 (2 OCPUs, 12 GB RAM)

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Supabase project (for authentication)
- Neon PostgreSQL database (or use local Docker)
- NATS JetStream
- Valkey (Redis-compatible)

### Local Development

1. Copy environment file:
```bash
cp .env.example .env
```

2. Update `.env` with your configuration:
   - `SUPABASE_URL` and `SUPABASE_JWKS_URL` from your Supabase project
   - `DATABASE_URL` for Neon or local PostgreSQL
   - `NATS_URL` for NATS JetStream
   - `VALKEY_URL` for Valkey/Redis

3. Start services:
```bash
docker-compose up -d
```

4. Run database migrations:
```bash
alembic upgrade head
```

5. API will be available at `http://localhost:8000`
   - Health check: `http://localhost:8000/health/live`
   - API docs: `http://localhost:8000/docs`

### Project Structure

```
veyaan-core-backend/
├── app/
│   ├── api/              # API routes, middleware, responses
│   ├── auth/             # Supabase JWT verification
│   ├── users/            # User management
│   ├── devices/          # Device registration & pairing
│   ├── commands/         # Command registry & execution
│   ├── approvals/        # Approval workflow
│   ├── tasks/            # Task state tracking
│   ├── emergency_stop/   # Emergency stop system
│   ├── audit/            # Audit logging
│   ├── websocket/        # Device WebSocket gateway
│   ├── events/           # NATS event publishing/consuming
│   ├── database/         # Database connection & sessions
│   ├── cache/            # Valkey client
│   ├── storage/          # Cloudflare R2 adapter
│   ├── security/         # Authorization, rate limiting
│   ├── observability/    # Logging, metrics, tracing
│   ├── health/           # Health checks
│   └── workers/          # Background workers
├── migrations/           # Alembic database migrations
├── tests/                # Unit, integration, e2e tests
├── infrastructure/       # Docker, Caddy, NATS, monitoring configs
├── docs/                 # Documentation
├── .env.example          # Environment variables template
├── docker-compose.yml    # Local development stack
├── Dockerfile            # API service image
├── Dockerfile.gateway    # WebSocket gateway image
├── Dockerfile.worker     # Background worker image
└── requirements.txt      # Python dependencies
```

## Implementation Phases

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for detailed phase breakdown.

### Phase 0: Environment Preparation
- Repository setup
- Docker Compose stack
- CI pipeline

### Phase 1: Core API Foundation
- FastAPI app with middleware
- Supabase JWT authentication
- Health endpoints
- User mapping

### Phase 2: Device Registration
- Pairing request flow
- Device credentials
- Device list & revocation

### Phase 3: WebSocket Gateway
- Secure device connections
- Heartbeat & presence
- Protocol versioning

### Phase 4: NATS & Command Pipeline
- NATS JetStream setup
- Command registry (test commands)
- Outbox pattern for durability
- Command delivery & results

### Phase 5: Approval System
- Approval creation & decision
- Replay protection
- Command resumption

### Phase 6: Emergency Stop
- Persistent stop state
- Cache for fast checks
- Device notification

### Phase 7: Audit & Observability
- Structured logging
- Audit history API
- Prometheus metrics

### Phase 8: Backup & Hardening
- Automated backups to R2
- Restore procedures
- Security hardening

## API Endpoints

### Health
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe
- `GET /health/detail` - Detailed health (auth required)

### Authentication
- `GET /v1/auth/me` - Current user profile
- `GET /v1/auth/verify` - Token verification

### Users
- `GET /v1/users/profile` - User profile

## Test Commands (Project 1)

Only these test commands are implemented in Project 1:

| Command | Risk | Approval | Description |
|---------|------|----------|-------------|
| `system.ping` | Low | None | Ping device |
| `device.get_status` | Low | None | Get device status |
| `app.open_test` | Medium | Optional | Open test app |
| `system.take_test_screenshot` | Medium | Optional | Take screenshot |
| `system.emergency_stop_test` | High | Required | Test emergency stop |

## WebSocket Protocol

### Connection
```
wss://ws.veyaan.local/v1/ws?device_id={id}&credential={proof}&protocol=v1&app_version=1.0.0
```

### Messages

**Server → Device (Welcome)**
```json
{
  "type": "welcome",
  "connection_id": "uuid",
  "server_time": "2024-01-01T00:00:00Z",
  "heartbeat_interval": 30,
  "protocol_version": "v1",
  "emergency_stop_active": false
}
```

**Device → Server (Heartbeat)**
```json
{
  "type": "heartbeat",
  "device_time": "2024-01-01T00:00:00Z",
  "state": "online",
  "active_command_count": 0,
  "app_version": "1.0.0"
}
```

**Server → Device (Command)**
```json
{
  "type": "command",
  "command_id": "uuid",
  "command_type": "system.ping",
  "parameters": {},
  "expires_at": "2024-01-01T00:05:00Z",
  "risk_metadata": {"level": "low"},
  "trace_id": "uuid"
}
```

**Device → Server (Acknowledgement)**
```json
{
  "type": "acknowledge",
  "command_id": "uuid",
  "accepted": true,
  "rejection_reason": null,
  "device_timestamp": "2024-01-01T00:00:01Z"
}
```

**Device → Server (Result)**
```json
{
  "type": "result",
  "command_id": "uuid",
  "success": true,
  "result_data": {"pong": true},
  "error_code": null,
  "started_at": "2024-01-01T00:00:01Z",
  "finished_at": "2024-01-01T00:00:02Z"
}
```

## Deployment

### Production Deployment

1. Bootstrap the server:
```bash
sudo ./infrastructure/scripts/bootstrap.sh
```

2. Clone repository to `/opt/veyaan`

3. Create production `.env` file in `/opt/veyaan/env/`

4. Start services:
```bash
docker compose -f /opt/veyaan/docker-compose.yml up -d
```

5. Configure Tailscale for admin access:
```bash
tailscale up
```

### Backup & Restore

**Backup:**
```bash
./infrastructure/scripts/backup.sh
```

**Restore:**
```bash
./infrastructure/scripts/restore.sh 2024/01/15
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test categories
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

## Security

- All secrets stored in environment variables (never in code)
- JWT tokens validated with Supabase JWKS
- Device credentials stored as hashes only
- Rate limiting on all state-changing endpoints
- Audit logging for all security events
- Emergency stop blocks all command execution
- TLS enforced via Caddy reverse proxy

## Monitoring

- Prometheus metrics at `/metrics`
- Structured JSON logging with redaction
- Health checks for all dependencies
- Grafana dashboards for key metrics

## License

Proprietary - VEYAAN Project