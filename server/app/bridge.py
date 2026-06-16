"""ExecutorBridge — reverse-WS pipe between the agent loop and the
Windows executor.

The Windows side opens a persistent WebSocket to the backend's /executor
endpoint. From then on, the agent loop (running in a worker thread) calls
`bridge.call_sync("click", {"x": 100, "y": 200})` and gets the result —
the bridge serializes the request over the WS, awaits the matching reply
by `req_id`, and returns the payload.

This removes the need for the backend-side .env to know any client IP.
The client tells us where it is by connecting to us.
"""
from __future__ import annotations

import asyncio
import itertools
from typing import Any

from fastapi import WebSocket


class ExecutorBridge:
    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._ids = itertools.count(1)
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def serve(self, ws: WebSocket, loop: asyncio.AbstractEventLoop) -> None:
        """Hold a single connection. If another arrives, the new one wins."""
        # Eject any prior connection cleanly.
        if self._ws is not None:
            try:
                await self._ws.close(code=1000)
            except Exception:  # noqa: BLE001
                pass
        self._ws = ws
        self._loop = loop
        try:
            while True:
                msg = await ws.receive_json()
                req_id = msg.get("req_id")
                fut = self._pending.pop(req_id, None) if req_id is not None else None
                if fut is not None and not fut.done():
                    fut.set_result(msg)
        finally:
            # Drop the connection; fail any in-flight calls.
            self._ws = None
            self._loop = None
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("executor disconnected"))
            self._pending.clear()

    async def _call_async(
        self, name: str, args: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        if self._ws is None or self._loop is None:
            raise RuntimeError("no executor connected")
        req_id = next(self._ids)
        fut = self._loop.create_future()
        self._pending[req_id] = fut
        async with self._lock:
            await self._ws.send_json({"req_id": req_id, "name": name, "args": args})
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise RuntimeError(f"executor call '{name}' timed out after {timeout}s") from None

    def call_sync(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Call from the agent worker thread. Blocks until the WS reply lands."""
        if not self.connected or self._loop is None:
            raise RuntimeError(
                "No Windows executor is connected. Start the executor on "
                "your Windows machine (client/scripts/dev_all.ps1)."
            )
        fut = asyncio.run_coroutine_threadsafe(
            self._call_async(name, args or {}, timeout),
            self._loop,
        )
        reply = fut.result(timeout=timeout + 5)
        if not reply.get("ok", False):
            raise RuntimeError(reply.get("error", "executor returned ok=false"))
        return reply.get("result", {})


# Singleton — imported by server/app/main.py (server side) and server/agent/computer.py (caller side).
bridge = ExecutorBridge()
