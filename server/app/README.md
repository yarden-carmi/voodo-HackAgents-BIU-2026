# App — Chat UI + backend

FastAPI server that ships a chat UI and a WebSocket. Each user message
spawns the agent loop in a background thread; AgentEvents stream back
over the WS to the browser. The user opens the UI from any device at
`http://<backend-host>:7860`.

## Running

```bash
source .venv/bin/activate
pip install -r server/app/requirements.txt
uvicorn server.app.main:app --host 0.0.0.0 --port 7860 --reload
```

Or use `server/scripts/dev_all.sh` which also starts Postgres in compose.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/`               | Serves the chat UI (`static/index.html`). |
| GET    | `/static/*`       | Static assets. |
| GET    | `/health`         | Liveness probe: `{"ok": true, "executor_connected": bool}`. |
| GET    | `/it`             | IT dashboard (HTTP Basic auth: `IT_USERNAME` / `IT_PASSWORD`). |
| GET    | `/admin`          | Admin dashboard (HTTP Basic auth: `ADMIN_PASSWORD`). |
| WS     | `/ws`             | Browser ↔ agent: client sends `{type:"message", text:"..."}`, server streams `AgentEvent` JSON. |
| WS     | `/executor`       | Reverse-WS from the Windows executor (gated by `EXECUTOR_TOKEN`). |
| GET    | `/api/solutions`              | List all approved solutions (IT auth). |
| POST   | `/api/pending-changes`        | Submit a fix for review. |
| GET    | `/api/pending-changes`        | List pending submissions. |
| DELETE | `/api/pending-changes/{id}`   | Cancel a pending submission. |
| GET    | `/api/admin/pending-changes`  | Admin list of pending changes. |
| PUT    | `/api/admin/pending-changes/{id}/approve` | Promote pending → solutions. |
| PUT    | `/api/admin/pending-changes/{id}/reject`  | Reject with reviewer note. |

## Dev modes

- `MOCK_AGENT=1 uvicorn server.app.main:app --port 7860` — canned events; no agent / LLM / Windows executor needed. Pure UI dev.
- `MOCK_LLM=1` — real agent loop, canned LLM responses; still needs the executor to be reachable so screenshots/clicks happen for real.
- `SKIP_DB=1` — skip DB lookup and writeback.

## UI rendering of `AgentEvent` kinds

| kind          | Render |
|---------------|--------|
| `thought`     | Italic line under the assistant bubble. |
| `tool_call`   | Pill with tool name + abbreviated args. |
| `observation` | Collapsible JSON. |
| `result`      | Big green/red banner. |
| `error`       | Red row. |
| `status`      | Greyed-out subtitle. |
