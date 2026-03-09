#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import fcntl
import os
import signal
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


@dataclass(frozen=True)
class LaunchPlan:
    port: int
    reuse_existing: bool
    open_browser_in_background: bool


@dataclass(frozen=True)
class AppState:
    port: int
    pid: int | None
    updated_at: float


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


def _read_app_state(state_path: Path) -> AppState | None:
    if not state_path.exists():
        return None
    try:
        raw = state_path.read_text(encoding="utf-8").strip()
        updated_at = state_path.stat().st_mtime
    except OSError:
        return None
    if not raw:
        return None
    lines = raw.splitlines()
    first_line = lines[0].strip()
    try:
        port = int(first_line)
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None

    pid: int | None = None
    if len(lines) > 1:
        second_line = lines[1].strip()
        if second_line:
            try:
                parsed_pid = int(second_line)
            except ValueError:
                parsed_pid = None
            if parsed_pid is not None and parsed_pid > 0:
                pid = parsed_pid

    return AppState(port=port, pid=pid, updated_at=updated_at)


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


def _is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _looks_like_current_app_process(pid: int, current_executable: Path) -> bool:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return False
    if result.returncode != 0:
        return False
    args = result.stdout.strip()
    if not args:
        return False
    current_path = str(current_executable)
    return current_path in args or current_executable.name in args


def _should_replace_existing_instance(
    pid: int | None,
    pid_running: bool,
    frozen: bool,
    state_updated_at: float,
    current_executable_updated_at: float | None,
) -> bool:
    if pid is None:
        return False
    if not pid_running:
        return True
    if not frozen or current_executable_updated_at is None:
        return False
    return current_executable_updated_at > state_updated_at + 1.0


def _maybe_replace_stale_instance(
    app_state: AppState | None,
    lock_path: Path,
    current_executable: Path,
) -> int | None:
    if app_state is None or app_state.pid is None:
        return None

    executable_updated_at: float | None = None
    try:
        executable_updated_at = current_executable.stat().st_mtime
    except OSError:
        executable_updated_at = None

    should_replace = _should_replace_existing_instance(
        pid=app_state.pid,
        pid_running=_is_process_running(app_state.pid),
        frozen=getattr(sys, "frozen", False),
        state_updated_at=app_state.updated_at,
        current_executable_updated_at=executable_updated_at,
    )
    if not should_replace:
        return None

    if _is_process_running(app_state.pid) and _looks_like_current_app_process(app_state.pid, current_executable):
        try:
            os.kill(app_state.pid, signal.SIGTERM)
        except OSError:
            return None

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        lock_fd = _acquire_single_instance_lock(lock_path)
        if lock_fd is not None:
            return lock_fd
        time.sleep(0.2)
    return None


def _build_launch_plan(
    lock_available: bool,
    state_port: int | None,
    preferred_port: int,
    selected_port: int,
) -> LaunchPlan:
    if not lock_available:
        return LaunchPlan(
            port=state_port or preferred_port,
            reuse_existing=True,
            open_browser_in_background=False,
        )
    return LaunchPlan(
        port=selected_port,
        reuse_existing=False,
        open_browser_in_background=True,
    )


def _open_browser_when_ready(port: int, timeout_seconds: float, background: bool) -> bool:
    url = f"http://127.0.0.1:{port}"

    def _worker() -> bool:
        if not _wait_for_port_open(port=port, timeout_seconds=timeout_seconds):
            return False
        _open_browser(url)
        return True

    if background:
        threading.Thread(target=_worker, daemon=True).start()
        return True
    return _worker()


def main() -> None:
    base_path = _get_base_path()
    _setup_environment(base_path)

    app_script = base_path / "app.py"
    if not app_script.exists():
        print(f"错误：找不到应用入口 {app_script}")
        sys.exit(1)

    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    preferred_port = _read_preferred_port()
    app_state = _read_app_state(_STATE_FILE)
    current_executable = Path(sys.executable).resolve()

    lock_fd = _acquire_single_instance_lock(_LOCK_FILE)
    if lock_fd is None:
        replacement_lock_fd = _maybe_replace_stale_instance(
            app_state=app_state,
            lock_path=_LOCK_FILE,
            current_executable=current_executable,
        )
        if replacement_lock_fd is not None:
            lock_fd = replacement_lock_fd
            _clear_state(_STATE_FILE)
            app_state = None

    selected_port = preferred_port
    if lock_fd is not None:
        selected_port = preferred_port if _can_bind_port(preferred_port) else _pick_available_port(preferred_port)

    launch_plan = _build_launch_plan(
        lock_available=lock_fd is not None,
        state_port=app_state.port if app_state is not None else None,
        preferred_port=preferred_port,
        selected_port=selected_port,
    )

    if launch_plan.reuse_existing:
        _open_browser_when_ready(
            port=launch_plan.port,
            timeout_seconds=6.0,
            background=launch_plan.open_browser_in_background,
        )
        return

    port = launch_plan.port
    if port != preferred_port:
        print(f"提示：{preferred_port} 端口已占用，改用 {port} 端口启动。")

    _write_state_port(_STATE_FILE, port)
    _open_browser_when_ready(
        port=port,
        timeout_seconds=30.0,
        background=launch_plan.open_browser_in_background,
    )

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
