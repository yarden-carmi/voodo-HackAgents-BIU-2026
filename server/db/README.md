# DB — Postgres + pgvector

Self-hosted, no cloud dependency. Postgres 16 + pgvector via the
`pgvector/pgvector:pg16` Docker image. Persists to a named Docker volume
(`voodo-db-data`) so seeds survive container restarts.

## Normal path: compose

`docker compose up -d` at the repo root brings the DB up alongside the
backend. `server/scripts/dev_all.sh` wraps that and auto-seeds on first
boot.

## Standalone path: `launch_db.sh`

For running the DB without the rest of the stack (e.g. during DB schema
development or to point a local Python interpreter at it):

```bash
bash server/db/launch_db.sh        # starts container, applies schema.sql
# .env at repo root must have DATABASE_URL set (see .env.example).
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/db/requirements.txt
python -m server.db.seed           # inserts 40 canned Windows fixes
```

Re-running `launch_db.sh` is idempotent — it removes the prior container
but keeps the volume, then re-applies the schema (which uses `IF NOT EXISTS`).

To wipe the DB completely:
```bash
docker rm -f voodo-db
docker volume rm voodo-db-data
```

## API

```python
from server.db.client import search_similar, record_solution, get_solution

matches = search_similar("my wifi keeps dropping", top_k=3)
for m in matches:
    print(m.score, m.record.problem_summary)

record_solution(SolutionRecord(problem_summary=..., steps=[...], success=True))
```

## Embeddings

`sentence-transformers/all-MiniLM-L6-v2` (384-dim) — small, fast, no API key.
If you swap models the dim must match `schema.sql` (`vector(384)`).
