"""Remote computer module — proxies tool calls to the Windows executor.

The agent runs on the backend; the user's screen is on a different machine.
Each function here is a sync call into the in-process ExecutorBridge, which
forwards the call over the long-lived WebSocket that the Windows executor
opened to us. Function signatures match client/executor/computer.py so
server/agent/tools.py::dispatch works unchanged.
"""
from __future__ import annotations

from typing import Any

from server.app.bridge import bridge


def _call(name: str, args: dict[str, Any] | None = None, timeout: float = 60.0) -> dict[str, Any]:
    return bridge.call_sync(name, args or {}, timeout=timeout)


def screenshot() -> dict[str, Any]:
    return _call("screenshot")


def click(x: int, y: int) -> dict[str, Any]:
    return _call("click", {"x": x, "y": y})


def double_click(x: int, y: int) -> dict[str, Any]:
    return _call("double_click", {"x": x, "y": y})


def right_click(x: int, y: int) -> dict[str, Any]:
    return _call("right_click", {"x": x, "y": y})


def type(text: str) -> dict[str, Any]:  # noqa: A001
    return _call("type", {"text": text})


def key(key: str) -> dict[str, Any]:  # noqa: A002
    return _call("key", {"key": key})


def hotkey(keys: list[str]) -> dict[str, Any]:
    return _call("hotkey", {"keys": keys})


def scroll(amount: int) -> dict[str, Any]:
    return _call("scroll", {"amount": amount})


# `run_powershell` has been REMOVED. PowerShell is no longer a tool the
# model can call. Internal diagnostic tools (flush_dns, check_disk_space,
# list_printers, etc.) still shell out to PowerShell on the executor
# side, but with fixed scripts and validated, env-passed parameters.


def wait(seconds: float) -> dict[str, Any]:
    return _call("wait", {"seconds": seconds}, timeout=float(seconds) + 5.0)


def open_app(app_name: str) -> dict[str, Any]:
    return _call("open_app", {"app_name": app_name})


def close_app(app_name: str) -> dict[str, Any]:
    return _call("close_app", {"app_name": app_name})


def list_running_apps() -> dict[str, Any]:
    return _call("list_running_apps")


def focus_window(window_title: str) -> dict[str, Any]:
    return _call("focus_window", {"window_title": window_title})


def minimize_all_windows() -> dict[str, Any]:
    return _call("minimize_all_windows")


def get_system_info() -> dict[str, Any]:
    return _call("get_system_info")


def set_volume(level: int, mute: bool = False) -> dict[str, Any]:
    return _call("set_volume", {"level": level, "mute": mute})


def get_audio_devices() -> dict[str, Any]:
    return _call("get_audio_devices")


def set_default_audio_device(device_name: str) -> dict[str, Any]:
    return _call("set_default_audio_device", {"device_name": device_name})


def toggle_network(wifi: bool = True, bluetooth: bool = True) -> dict[str, Any]:
    return _call("toggle_network", {"wifi": wifi, "bluetooth": bluetooth}, timeout=20.0)


def check_network_status() -> dict[str, Any]:
    return _call("check_network_status")


def change_display_brightness(level: int) -> dict[str, Any]:
    return _call("change_display_brightness", {"level": level})


def read_clipboard() -> dict[str, Any]:
    return _call("read_clipboard")


def write_clipboard(text: str) -> dict[str, Any]:
    return _call("write_clipboard", {"text": text})


def search_files(query: str, directory: str = ".") -> dict[str, Any]:
    return _call("search_files", {"query": query, "directory": directory}, timeout=40.0)


def read_file_preview(file_path: str) -> dict[str, Any]:
    return _call("read_file_preview", {"file_path": file_path})


def flush_dns() -> dict[str, Any]:
    return _call("flush_dns")


def get_ip_info() -> dict[str, Any]:
    return _call("get_ip_info")


def list_printers() -> dict[str, Any]:
    return _call("list_printers")


def clear_print_queue() -> dict[str, Any]:
    return _call("clear_print_queue", timeout=15.0)


def check_camera() -> dict[str, Any]:
    return _call("check_camera")


def list_usb_devices() -> dict[str, Any]:
    return _call("list_usb_devices")


def check_disk_space() -> dict[str, Any]:
    return _call("check_disk_space")


def clear_temp_files() -> dict[str, Any]:
    return _call("clear_temp_files", timeout=60.0)


def get_event_log_errors() -> dict[str, Any]:
    return _call("get_event_log_errors")


def list_startup_programs() -> dict[str, Any]:
    return _call("list_startup_programs")


def suggest_solution(suggestion: str) -> dict[str, Any]:
    # Like finish, this is handled entirely by the agent loop/UI to talk to the user.
    return {"status": "suggested", "suggestion": suggestion}


def highlight_at(x: int, y: int, label: str = "", seconds: float = 4.0,
                 type_hint: str = "") -> dict[str, Any]:
    """Forward to the executor. The executor BLOCKS until the user clicks
    (or moves the mouse, or the spotlight times out), so the bridge needs
    a longer timeout than the default — generous so the agent can wait
    out a slow user."""
    args: dict[str, Any] = {"x": x, "y": y, "label": label, "seconds": seconds}
    if type_hint:
        args["type_hint"] = type_hint
    return _call("highlight_at", args, timeout=60.0)


def finish(success: bool, summary: str) -> dict[str, Any]:
    # Local terminator — not sent to the executor.
    return {"success": bool(success), "summary": summary}
