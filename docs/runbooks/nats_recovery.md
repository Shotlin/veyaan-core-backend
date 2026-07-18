# Runbook: NATS Restart & Recovery

**Service**: `veyaan-nats`  
**Criticality**: Critical — all event-driven command delivery depends on NATS JetStream

---

## Symptoms

- Commands stuck in QUEUED state for extended periods
- Gateway logs showing `nats_subscription_error` or `connection closed`
- Outbox publisher logs showing `Failed to publish outbox event`
- Health checks failing: `nats.status = not_ready`

---

## Impact

- No new commands can be delivered to devices (outbox publish fails)
- Existing in-flight command results (ack/progress/result) cannot be published
- **No data is lost**: Commands remain in Neon DB, outbox events remain in `outbox_events` table

---

## Steps

### 1. Confirm NATS is Down

```bash
# Check container status
docker compose ps nats

# Check NATS monitoring endpoint
curl http://localhost:8222/healthz

# Check NATS logs
docker compose logs nats --tail=50
```

### 2. Restart NATS

```bash
docker compose restart nats

# Wait for health check
docker compose ps nats
```

### 3. Verify JetStream Streams Recovered

```bash
# List streams — should show VEYAAN_COMMANDS, VEYAAN_DEVICE_EVENTS, etc.
docker compose exec nats nats stream ls

# Check stream health
docker compose exec nats nats stream report

# Check durable consumers
docker compose exec nats nats consumer report VEYAAN_COMMANDS
```

### 4. Trigger Outbox Re-publish

After NATS restarts, the outbox publisher will automatically pick up pending events
on its next poll cycle (every 5 seconds). Verify this happens:

```bash
# Watch outbox publisher logs
docker compose logs outbox-publisher -f

# Check pending events in DB
# Expected: count decreases as events are published
```

```sql
SELECT status, count(*) 
FROM outbox_events 
GROUP BY status;
```

### 5. Verify Command Delivery Resumes

```bash
# Check commands moving from QUEUED → DELIVERED
# Expected: QUEUED count decreases, DELIVERED count increases
```

```sql
SELECT state, count(*) FROM commands GROUP BY state;
```

---

## NATS Data Recovery

JetStream data is persisted to the `nats_data` Docker volume. Data survives container restarts.

If the volume is lost (rare), pending outbox events in Neon will be re-published when NATS comes back. Commands in QUEUED state will be re-sent by the outbox publisher.

**There is no gap** — the transactional outbox is the durable source of truth.

---

## Stream Configuration

If streams need to be recreated (e.g. after volume loss), the NATS client recreates them automatically on startup. Check `app/events/nats_client.py` for the stream configuration.

```bash
# Force stream recreation by restarting the API
docker compose restart api

# Confirm streams exist
docker compose exec nats nats stream ls
```

---

## Escalation

Escalate if:
- NATS fails to restart after 3 attempts
- JetStream streams are missing after restart
- Pending events > 500 (large backlog forming)
