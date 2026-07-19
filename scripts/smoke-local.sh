#!/usr/bin/env bash
# smoke-local.sh — basic smoke tests against a running local stack
# Run after: make local-up

set -euo pipefail

API="http://localhost:8000"
GW="http://localhost:8001"
PASS=0
FAIL=0

ok()   { echo "  ✓ $*"; PASS=$((PASS + 1)); }
fail() { echo "  ✗ $*"; FAIL=$((FAIL + 1)); }

check_http() {
  local label="$1"
  local url="$2"
  local expected_status="${3:-200}"

  actual_status=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  if [[ "$actual_status" == "$expected_status" ]]; then
    ok "$label ($actual_status)"
  else
    fail "$label — expected $expected_status, got $actual_status ($url)"
  fi
}

check_json_field() {
  local label="$1"
  local url="$2"
  local field="$3"
  local expected="$4"

  actual=$(curl -s "$url" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$field',''))" 2>/dev/null || echo "")
  if [[ "$actual" == "$expected" ]]; then
    ok "$label"
  else
    fail "$label — expected '$expected', got '$actual'"
  fi
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  VEYAAN Smoke Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "[API] Liveness and readiness"
check_http   "GET /health/live"   "$API/health/live"
check_http   "GET /health/ready"  "$API/health/ready"
check_json_field "root service name" "$API/" "service" "VEYAAN API"

echo ""
echo "[API] OpenAPI docs (development mode)"
check_http   "GET /docs"          "$API/docs"
check_http   "GET /openapi.json"  "$API/openapi.json"

echo ""
echo "[API] Auth routes reachable (expect 401 without token)"
check_http   "GET /v1/devices (no auth)"  "$API/v1/devices"  "401"
check_http   "GET /v1/commands (no auth)" "$API/v1/commands" "401"
check_http   "GET /v1/approvals (no auth)" "$API/v1/approvals" "401"
check_http   "GET /v1/notifications (no auth)" "$API/v1/notifications" "401"

echo ""
echo "[API] Metrics endpoint"
check_http   "GET /metrics"       "$API/metrics/"

echo ""
echo "[Gateway] Liveness and readiness"
check_http   "GET /health/live"   "$GW/health/live"
check_http   "GET /health/ready"  "$GW/health/ready"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
