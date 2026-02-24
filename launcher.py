#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

_DEFAULT_PORT = 8501
_MAX_PORT_SEARCH = 20
_STATE_DIR = Path.home() / "Library" / "Application Support" / "video_splicer"
_STATE_FILE = _STATE_DIR / "server_state.txt"
_LOCK_FILE = _STATE_DIR / "server.lock"


def _get_base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def _setup_environment(base_path: Path) -> None:
    os.environ["PATH"] = f"{base_path}:{os.environ.get('PATH', '')}"

    endcard = base_path / "assets" / "video" / "endcard.mp4"
    if endcard.exists():
        os.environ["SP_ENDCARD_PATH"] = str(endcard)


def _read_preferred_port() -> int:
    raw = os.environ.get("SP_APP_PORT", str(_DEFAULT_PORT)).strip()
    if not raw:
        return _DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        return _DEFAULT_PORT
    if 1 <= port <= 65535:
        return port
    return _DEFAULT_PORT


def _acquire_single_instance_lock(lock_path: Path) -> int | None:
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(lock_fd)
        return None
    return lock_fd


def _read_state_port(state_path: Path) -> int | None:
    if not state_path.exists():
        return None
    try:
        raw = state_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    first_line = raw.splitlines()[0].strip()
    try:
        port = int(first_line)
    except ValueError:
        return None
    if 1 <= port <= 65535:
        return port
    return None


def _write_state_port(state_path: Path, port: int) -> None:
    payload = f"{port}\n{os.getpid()}\n"
    try:
        state_path.write_text(payload, encoding="utf-8")
    except OSError:
        return


def _clear_state(state_path: Path) -> None:
    try:
        state_path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _is_port_open(port: int, timeout_seconds: float = 0.3) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _can_bind_port(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _pick_available_port(preferred_port: int) -> int:
    for candidate in range(preferred_port, preferred_port + _MAX_PORT_SEARCH):
        if _can_bind_port(candidate):
            return candidate
    return preferred_port


def _wait_for_port_open(port: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _is_port_open(port):
            return True
        time.sleep(0.2)
    return False


def _open_browser(url: str) -> None:
    try:
        subprocess.run(["open", url], check=False)
    except Exception:  # noqa: BLE001
        return


def _open_browser_when_ready(port: int, timeout_seconds: float) -> None:
    url = f"http://127.0.0.1:{port}"

    def _worker() -> None:
        _wait_for_port_open(port=port, timeout_seconds=timeout_seconds)
        _open_browser(url)

    threading.Thread(target=_worker, daemon=True).start()


def main() -> None:
    base_path = _get_base_path()
    _setup_environment(base_path)

    app_script = base_path / "app.py"
    if not app_script.exists():
        print(f"错误：找不到应用入口 {app_script}")
        sys.exit(1)

    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    preferred_port = _read_preferred_port()

    lock_fd = _acquire_single_instance_lock(_LOCK_FILE)
    if lock_fd is None:
        existing_port = _read_state_port(_STATE_FILE) or preferred_port
        _open_browser_when_ready(port=existing_port, timeout_seconds=6.0)
        return

    port = preferred_port if _can_bind_port(preferred_port) else _pick_available_port(preferred_port)
    if port != preferred_port:
        print(f"提示：{preferred_port} 端口已占用，改用 {port} 端口启动。")

    _write_state_port(_STATE_FILE, port)
    _open_browser_when_ready(port=port, timeout_seconds=30.0)

    sys.argv = [
        "streamlit",
        "run",
        str(app_script),
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "true",
        "--server.fileWatcherType",
        "none",
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]

    from streamlit.web.cli import main as st_main  # noqa: E402

    try:
        st_main()
    finally:
        _clear_state(_STATE_FILE)
        os.close(lock_fd)


if __name__ == "__main__":
    main()
