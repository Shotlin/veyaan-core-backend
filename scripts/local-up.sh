#!/usr/bin/env bash
# local-up.sh — bring up the full VEYAAN development stack on a clean machine
#
# Prerequisites:
#   - Docker Desktop or Docker Engine running
#   - .env file present (copy from .env.docker.example)
#
# Steps:
#   1. Validate .env and compose config
#   2. Build all images
#   3. Start infrastructure (postgres, nats, valkey)
#   4. Wait for all three to be healthy
#   5. Run migrations (one-shot)
#   6. Start API, gateway, workers
#   7. Verify readiness endpoints
#   8. Print local URLs

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${BOLD}[local-up]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; exit 1; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }

# ── Preflight ─────────────────────────────────────────────────────────────────

if [[ ! -f ".env" ]]; then
  fail ".env not found. Run: cp .env.docker.example .env"
fi

log "Validating docker-compose configuration..."
docker compose --env-file .env config --quiet || fail "docker-compose config invalid"
ok "Config valid"

# ── Build ─────────────────────────────────────────────────────────────────────

log "Building images..."
docker compose build api gateway outbox-publisher lifecycle-consumer scheduler migrate
ok "Images built"

# ── Infrastructure ────────────────────────────────────────────────────────────

log "Starting infrastructure (postgres, nats, valkey)..."
docker compose up -d postgres nats valkey

log "Waiting for infrastructure to become healthy..."
TIMEOUT=120
INTERVAL=3
elapsed=0

wait_healthy() {
  local svc="$1"
  while true; do
    local health
    health=$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q "$svc" 2>/dev/null)" 2>/dev/null || echo "none")
    if [[ "$health" == "healthy" ]]; then
      return 0
    fi
    if [[ $elapsed -ge $TIMEOUT ]]; then
      return 1
    fi
    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
  done
}

for svc in postgres nats valkey; do
  log "  Waiting for $svc..."
  if wait_healthy "$svc"; then
    ok "  $svc is healthy"
  else
    docker compose logs "$svc" | tail -20
    fail "$svc did not become healthy within ${TIMEOUT}s"
  fi
  elapsed=0
done

# ── Migrations ────────────────────────────────────────────────────────────────

log "Running database migrations..."
docker compose run --rm migrate
ok "Migrations complete"

# ── Application Services ──────────────────────────────────────────────────────

log "Starting application services..."
docker compose up -d api gateway outbox-publisher lifecycle-consumer scheduler
ok "Services started"

# ── Readiness Checks ──────────────────────────────────────────────────────────

log "Waiting for API readiness..."
READY_TIMEOUT=60
elapsed=0
while true; do
  if curl -sf http://localhost:8000/health/live >/dev/null 2>&1; then
    ok "API is live"
    break
  fi
  if [[ $elapsed -ge $READY_TIMEOUT ]]; then
    docker compose logs api | tail -30
    fail "API did not become live within ${READY_TIMEOUT}s"
  fi
  sleep 3
  elapsed=$((elapsed + 3))
done

elapsed=0
while true; do
  if curl -sf http://localhost:8001/health/live >/dev/null 2>&1; then
    ok "Gateway is live"
    break
  fi
  if [[ $elapsed -ge $READY_TIMEOUT ]]; then
    docker compose logs gateway | tail -30
    fail "Gateway did not become live within ${READY_TIMEOUT}s"
  fi
  sleep 3
  elapsed=$((elapsed + 3))
done

# API ready check (may take a moment for NATS streams to initialise)
sleep 3
api_ready=$(curl -sf http://localhost:8000/health/ready 2>/dev/null || echo "{}")
if echo "$api_ready" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('ready') else 1)" 2>/dev/null; then
  ok "API reports ready"
else
  warn "API /health/ready check not fully green yet (may need more time)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}  VEYAAN Dev Stack is running${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "  API:            http://localhost:8000"
echo "  API docs:       http://localhost:8000/docs"
echo "  Gateway WS:     ws://localhost:8001/v1/ws"
echo "  NATS Monitoring: http://localhost:8222"
echo "  PostgreSQL:     localhost:5432 (veyaan / dev_password)"
echo "  Valkey:         localhost:6379"
echo ""
echo "  make logs          # follow all logs"
echo "  make test          # run tests"
echo "  make smoke         # run smoke tests"
echo "  make local-down    # stop the stack"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
