# Executor — Windows I/O service (reverse-WS)

Tiny Python service that runs on the Windows machine the agent will fix.
It opens a **persistent WebSocket out to the backend's `/executor`
endpoint** and services tool calls (screenshot, click, type, etc.) over
that pipe. No inbound port on Windows; the backend never needs the
Windows IP.

## Run

```powershell
git pull
.\client\scripts\dev_all.ps1 -Backend ws://<backend-host>:7860 -Token "the-shared-token"
```

If you keep a `.env` at the repo root, `-Backend` and `-Token` default to
`BACKEND_WS_URL` and `EXECUTOR_TOKEN` from that file.

Reconnects automatically with backoff if the link drops; press Ctrl-C to stop.

## Protocol (over the WebSocket)

Backend → executor:
```json
{ "req_id": 7, "name": "click", "args": { "x": 100, "y": 200 } }
```
Executor → backend:
```json
{ "req_id": 7, "ok": true, "result": { "x": 100, "y": 200 } }
```
or on error:
```json
{ "req_id": 7, "ok": false, "error": "PyAutoGUIException: ..." }
```

Tool names match `ToolName` in `shared/protocol.py`: `click`, `double_click`,
`right_click`, `type`, `key`, `hotkey`, `scroll`, `screenshot`, `wait`,
`finish`, plus the diagnostic helpers (`get_audio_devices`, `flush_dns`, …).

## Security

Single shared bearer token via `EXECUTOR_TOKEN` (sent as `?token=...` on
the WS connect). If unset, the backend accepts unauthenticated
connections — fine on a trusted local network, not for the public
internet. Set `VOODO_PROD=1` in `.env` to make the backend refuse to
start without a 16+ char token.
