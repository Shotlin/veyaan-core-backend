# Runbook: Gateway Restart Recovery

**Service**: `veyaan-gateway`  
**Criticality**: High — device connectivity depends on this service

---

## Symptoms

- Device WebSocket connections are dropping or failing to reconnect
- Gateway health check failing: `curl http://localhost:8001/health/ready`
- Logs show `connection closed` or `NATS subscription error`

---

## Impact

Devices cannot receive commands while the gateway is down. Commands remain in QUEUED state in Neon and will be re-delivered when the gateway restarts. **No commands are lost** — the transactional outbox and NATS JetStream durability ensure at-least-once delivery.

---

## Steps

### 1. Confirm the Problem

```bash
# Check gateway container status
docker compose ps gateway

# Check health endpoint
curl -f http://localhost:8001/health/ready || echo "NOT READY"

# Check recent logs
docker compose logs gateway --tail=100
```

### 2. Identify Root Cause

| Log message | Likely cause |
|---|---|
| `NATS connection error` | NATS service is down or restarting |
| `Valkey connection error` | Valkey service is unavailable |
| `OOM killed` | Memory limit exceeded — check resource limits |
| `Address already in use` | Previous instance didn't exit cleanly |

### 3. Restart the Gateway

```bash
docker compose restart gateway

# Wait for health check to pass
docker compose ps gateway
curl http://localhost:8001/health/ready
```

### 4. Verify Recovery

After restart, the gateway:
- Reconnects to NATS JetStream automatically
- Reconnects to Valkey automatically
- Device connections must re-authenticate via Ed25519 challenge-response
- In-flight commands in QUEUED state will be re-delivered by the outbox publisher

```bash
# Confirm NATS durable consumers are healthy
docker compose exec nats nats consumer report VEYAAN_COMMANDS

# Confirm Valkey is healthy
docker compose exec valkey valkey-cli ping
```

### 5. Check for Undelivered Commands

If devices were offline for an extended period:

```sql
-- Commands still in QUEUED state (may need re-delivery)
SELECT id, command_type, device_id, created_at, expires_at
FROM commands
WHERE state = 'queued'
  AND (expires_at IS NULL OR expires_at > NOW())
ORDER BY created_at ASC;

-- Outbox events still pending
SELECT id, subject, attempt_count, created_at
FROM outbox_events
WHERE status = 'pending'
ORDER BY created_at ASC;
```

---

## Escalation

If the gateway fails to restart after 3 attempts or health checks continue to fail after 5 minutes, escalate to on-call engineer. Check NATS and Valkey services first.

---

## Prevention

- Set `restart: unless-stopped` in production compose (already configured)
- Monitor `veyaan_gateway_ws_connections_total` in Prometheus
- Alert on gateway pod restart count > 2 in 5 minutes
