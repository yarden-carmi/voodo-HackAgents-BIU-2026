"""Executor — runs on Windows.

Opens a persistent WebSocket to the backend's /executor endpoint and
services tool calls from there. Connects OUT so no inbound port needs to
be open on this machine; the backend never needs to know our IP.

Run:
    python -m executor.main --backend ws://<backend-host>:7860 --token <EXECUTOR_TOKEN>

(client/scripts/dev_all.ps1 wraps this.)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from . import computer


_DEBUG = os.getenv("VOODO_DEBUG", "").lower() in ("1", "true", "yes")

# Tools whose result payloads are too big / noisy to print fully.
_NOISY_RESULTS = {"screenshot", "list_running_apps", "list_usb_devices", "list_printers"}


def _fmt_args(args: dict[str, Any]) -> str:
    s = json.dumps(args, default=str)
    return s if len(s) <= 200 else s[:197] + "..."


def _fmt_result(name: str, result: Any) -> str:
    if name in _NOISY_RESULTS and isinstance(result, dict):
        keys = sorted(result.keys())
        return f"{{keys: {keys}}}"
    s = json.dumps(result, default=str)
    return s if len(s) <= 240 else s[:237] + "..."


async def _handle_one(ws: websockets.WebSocketClientProtocol) -> None:
    """Service tool calls on a single connection until it closes."""
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            print(f"[executor] dropped malformed frame ({len(raw)} bytes)", flush=True)
            continue
        req_id = msg.get("req_id")
        name = msg.get("name", "")
        args = msg.get("args", {}) or {}
        reply: dict[str, Any] = {"req_id": req_id}

        # Always log the call — this is the single most useful debug line.
        print(f"[executor] #{req_id} {name}({_fmt_args(args)})", flush=True)
        t0 = time.time()

        fn = getattr(computer, name, None)
        if fn is None:
            reply["ok"] = False
            reply["error"] = f"unknown tool: {name}"
            print(f"[executor] #{req_id} -> ERR unknown tool '{name}'", flush=True)
        else:
            try:
                result = await asyncio.to_thread(fn, **args)
                reply["ok"] = True
                reply["result"] = result
                dt = (time.time() - t0) * 1000
                print(
                    f"[executor] #{req_id} -> ok ({dt:.0f}ms) {_fmt_result(name, result)}",
                    flush=True,
                )
            except TypeError as e:
                reply["ok"] = False
                reply["error"] = f"bad args for {name}: {e}"
                print(f"[executor] #{req_id} -> ERR bad args: {e}", flush=True)
            except Exception as e:  # noqa: BLE001
                reply["ok"] = False
                reply["error"] = f"{type(e).__name__}: {e}"
                print(f"[executor] #{req_id} -> ERR {type(e).__name__}: {e}", flush=True)
                if _DEBUG:
                    import traceback
                    traceback.print_exc()

        await ws.send(json.dumps(reply))


def _print_startup_diag() -> None:
    """One-shot info dump so the user can sanity-check the environment."""
    print(f"[executor] python {sys.version.split()[0]}  platform={sys.platform}", flush=True)
    # Probe both the screen-capture and the click backends — they MUST
    # agree on the coordinate space, otherwise clicks land in the wrong
    # place. mss captures at physical pixels under DPI-aware level 2;
    # pyautogui clicks via SetCursorPos, which is also physical pixels
    # under DPI-aware level 2 — IF the awareness was set before pyautogui
    # was imported. Log both so a mismatch is obvious.
    mss_dim = pag_dim = sysmetrics_dim = None
    try:
        import mss
        with mss.mss() as sct:
            mon = sct.monitors[1]
            mss_dim = (mon["width"], mon["height"])
    except Exception as e:  # noqa: BLE001
        print(f"[executor] mss probe failed: {e}", flush=True)
    try:
        import pyautogui
        pag_dim = pyautogui.size()
        pag_dim = (int(pag_dim[0]), int(pag_dim[1]))
    except Exception as e:  # noqa: BLE001
        print(f"[executor] pyautogui probe failed: {e}", flush=True)
    if sys.platform == "win32":
        try:
            import ctypes
            gsm = ctypes.windll.user32.GetSystemMetrics
            sysmetrics_dim = (gsm(0), gsm(1))  # SM_CXSCREEN, SM_CYSCREEN
        except Exception as e:  # noqa: BLE001
            print(f"[executor] GetSystemMetrics probe failed: {e}", flush=True)
    print(
        f"[executor] screen dims: mss={mss_dim}  pyautogui.size={pag_dim}  "
        f"GetSystemMetrics={sysmetrics_dim}",
        flush=True,
    )
    if mss_dim and pag_dim and mss_dim != pag_dim:
        print(
            "[executor] WARNING: mss and pyautogui disagree on screen "
            "dim. Clicks will land in the wrong place. DPI-awareness "
            "probably wasn't set before pyautogui imported.",
            flush=True,
        )
    if _DEBUG:
        print("[executor] VOODO_DEBUG=1 (verbose tracebacks on tool errors)", flush=True)


async def _run(backend_url: str, token: str) -> None:
    _print_startup_diag()
    # Widget launches when the backend calls computer.open_assistant —
    # that happens on the user's first browser message. No pre-pop at
    # startup; an empty widget in the corner before any prompt is just
    # distracting.
    sep = "&" if "?" in backend_url else "?"
    url = f"{backend_url.rstrip('/')}/executor{sep}token={token}" if token \
        else f"{backend_url.rstrip('/')}/executor"
    backoff = 1.0
    while True:
        try:
            print(f"[executor] connecting to {backend_url} ...", flush=True)
            async with websockets.connect(url, max_size=64 * 1024 * 1024) as ws:
                print("[executor] connected; awaiting tool calls", flush=True)
                backoff = 1.0
                await _handle_one(ws)
        except ConnectionClosed as e:
            print(f"[executor] connection closed: {e}", flush=True)
        except OSError as e:
            print(f"[executor] connect failed: {e}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[executor] error: {type(e).__name__}: {e}", flush=True)
        print(f"[executor] reconnecting in {backoff:.1f}s", flush=True)
        time.sleep(backoff)
        backoff = min(backoff * 2, 15.0)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--backend",
        default=os.getenv("BACKEND_WS_URL", "ws://localhost:7860"),
        help="Backend WS base URL (e.g. ws://<backend-host>:7860).",
    )
    p.add_argument(
        "--token",
        default=os.getenv("EXECUTOR_TOKEN", ""),
        help="Shared bearer token (sent as ?token=...).",
    )
    args = p.parse_args()
    try:
        asyncio.run(_run(args.backend, args.token))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
