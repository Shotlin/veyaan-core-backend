#!/usr/bin/env bash
# wait-healthy.sh — wait for named compose services to become healthy
# Usage: ./scripts/wait-healthy.sh postgres nats valkey

set -euo pipefail

TIMEOUT=120
INTERVAL=3

services=("$@")

if [[ ${#services[@]} -eq 0 ]]; then
  echo "Usage: $0 <service> [service...]"
  exit 1
fi

echo "Waiting up to ${TIMEOUT}s for services to be healthy: ${services[*]}"

elapsed=0
while true; do
  all_healthy=true
  for svc in "${services[@]}"; do
    state=$(docker compose ps --format json "$svc" 2>/dev/null | \
            python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Health','') if isinstance(d,dict) else next((x.get('Health','') for x in d if x.get('Service')=='$svc'),''))" 2>/dev/null || echo "")
    if [[ "$state" != "healthy" ]]; then
      all_healthy=false
      break
    fi
  done

  if $all_healthy; then
    echo "All services healthy after ${elapsed}s"
    exit 0
  fi

  if [[ $elapsed -ge $TIMEOUT ]]; then
    echo "ERROR: Services not healthy after ${TIMEOUT}s"
    docker compose ps
    exit 1
  fi

  sleep "$INTERVAL"
  elapsed=$((elapsed + INTERVAL))
done
