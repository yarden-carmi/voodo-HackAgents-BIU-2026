#!/usr/bin/env bash
# Stop the voodo backend stack. Preserves the postgres data volume
# (voodo-db-data) so seeds survive across restarts.
set -e
cd "$(dirname "$0")/../.."   # repo root
docker compose down
echo "[stop_all] stopped. (volume voodo-db-data preserved)"
