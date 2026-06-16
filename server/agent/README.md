# Agent — Computer-use loop (server side)

The agent's brain runs on the backend alongside Postgres. It calls
OpenRouter (an OpenAI-compatible hosted gateway) for the model. It does
NOT touch the user's mouse/keyboard directly — every action is sent over
the executor WebSocket to the Windows box (see
[`client/executor/README.md`](../../client/executor/README.md)).

## Modules

| File          | What it owns |
|---------------|--------------|
| `agent.py`    | The main loop; orchestrates db lookup, llm calls, tool dispatch, db writeback. |
| `computer.py` | Thin sync caller into `server.app.bridge` (the WS connection from the Windows executor). |
| `llm.py`      | OpenAI client → OpenRouter. Builds vision messages, parses tool calls. |
| `tools.py`    | Tool schemas (OpenAI format) + dispatch table. |
| `mock_llm.py` | Canned VLM responses for offline dev. Used with `--mock-llm`. |

## Running standalone

```bash
source .venv/bin/activate
pip install -r server/agent/requirements.txt -r server/db/requirements.txt
# .env has OPENROUTER_API_KEY, DATABASE_URL, EXECUTOR_TOKEN, etc.
python -m server.agent.agent --mock-llm --skip-db --task "open notepad"
# (executor on Windows must be running and reachable)
```

## Adding a new tool

1. Add the literal to `ToolName` in [`shared/protocol.py`](../../shared/protocol.py).
2. Add the JSON schema in `server/agent/tools.py::TOOL_SCHEMAS`.
3. Implement the side effect in `client/executor/computer.py` (it runs on Windows).
4. Add a matching pass-through in `server/agent/computer.py` (thin WS client).

## Safety knobs

- `AGENT_MAX_STEPS` env caps the loop length (default 15).
- The executor has its own bearer-token auth (`EXECUTOR_TOKEN`).
- There is no `run_powershell` tool — it was removed for safety.
