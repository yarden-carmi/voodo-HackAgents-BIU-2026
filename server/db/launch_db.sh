#!/usr/bin/env bash
# Launch Postgres + pgvector for voodo. Persists data in a named volume so
# you can `docker rm -f` the container without losing the seed data.
#
# After the container is healthy, applies server/db/schema.sql idempotently.
set -euo pipefail

IMAGE="${IMAGE:-pgvector/pgvector:pg16}"
NAME="${NAME:-voodo-db}"
PORT="${PORT:-5432}"
VOLUME="${VOLUME:-voodo-db-data}"
PASSWORD="${POSTGRES_PASSWORD:-voodo}"
USER="${POSTGRES_USER:-voodo}"
DB="${POSTGRES_DB:-voodo}"

SCHEMA="$(cd "$(dirname "$0")" && pwd)/schema.sql"

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    echo "[launch_db] removing existing container '$NAME'"
    docker rm -f "$NAME" >/dev/null
fi

echo "[launch_db] starting $IMAGE on port $PORT (volume: $VOLUME)"
docker run -d \
    --name "$NAME" \
    -e POSTGRES_USER="$USER" \
    -e POSTGRES_PASSWORD="$PASSWORD" \
    -e POSTGRES_DB="$DB" \
    -v "${VOLUME}:/var/lib/postgresql/data" \
    -p "${PORT}:5432" \
    "$IMAGE" >/dev/null

echo "[launch_db] waiting for postgres to accept connections..."
for _ in $(seq 1 30); do
    if docker exec "$NAME" pg_isready -U "$USER" -d "$DB" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo "[launch_db] applying schema.sql"
docker exec -i "$NAME" psql -U "$USER" -d "$DB" < "$SCHEMA" >/dev/null

echo "[launch_db] ready."
echo "  DATABASE_URL=postgresql://$USER:$PASSWORD@localhost:$PORT/$DB"
