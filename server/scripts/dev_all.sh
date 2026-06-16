#!/usr/bin/env bash
# Backend-side one-shot launcher for voodo. Idempotent.
#
# Brings up the backend stack via docker-compose (Postgres + backend).
# The LLM provider is OpenRouter — no local model server.
# The Windows executor is started separately via client/scripts/dev_all.ps1.
#
# Environment:
#   See .env.example. Required: OPENROUTER_API_KEY, EXECUTOR_TOKEN,
#                                POSTGRES_PASSWORD.
#
# Stop with:  bash server/scripts/stop_all.sh   (keeps the postgres volume)

set -euo pipefail

cd "$(dirname "$0")/../.."   # repo root
ROOT="$(pwd)"

# Load .env line-by-line (no eval) so values with shell metacharacters
# don't break the script.
if [[ -f .env ]]; then
    while IFS='=' read -r key val; do
        [[ -z "$key" || "$key" == \#* ]] && continue
        val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
        export "$key=$val"
    done < .env
fi

COMPOSE=(docker compose)

log() { echo -e "\033[1;36m[dev_all]\033[0m $*"; }
ok()  { echo -e "\033[1;32m[dev_all]\033[0m $*"; }

# Build the backend image if it's missing.
if ! docker image inspect voodo-backend:latest >/dev/null 2>&1; then
    log "building voodo-backend image (one-time)"
    "${COMPOSE[@]}" build backend
fi

log "starting stack (detached): postgres + backend"
"${COMPOSE[@]}" up -d

log "waiting for backend /health ..."
APP_PORT="${APP_PORT:-7860}"
for _ in $(seq 1 60); do
    if curl -sf --max-time 2 "http://localhost:${APP_PORT}/health" >/dev/null 2>&1; then
        ok "backend ready"
        break
    fi
    sleep 5
done

# Seed canned solutions if the table is empty (first start).
COUNT=$("${COMPOSE[@]}" exec -T postgres psql -U "${POSTGRES_USER:-voodo}" -d "${POSTGRES_DB:-voodo}" -tA \
    -c "select count(*) from solutions" 2>/dev/null | tr -d '[:space:]' || echo 0)
if [[ "$COUNT" == "0" ]]; then
    log "seeding solutions (40 canned Windows fixes — first run downloads embedder, ~30s)"
    "${COMPOSE[@]}" exec -T backend python -m server.db.seed | tail -3
else
    ok "DB already has $COUNT solutions"
fi

echo
ok "stack up:"
"${COMPOSE[@]}" ps
echo
echo "    chat UI:        http://localhost:${APP_PORT}/"
echo "    health:         curl http://localhost:${APP_PORT}/health"
echo "    Postgres:       localhost:5432"
echo "    Executor:       waits on ws://localhost:${APP_PORT}/executor"
echo "                    (Windows side dials in via client/scripts/dev_all.ps1)"
echo
echo "    tail backend:   docker compose logs -f backend"
echo "    stop:           bash server/scripts/stop_all.sh"
