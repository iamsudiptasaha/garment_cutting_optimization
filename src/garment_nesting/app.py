"""CLI entrypoint for local development and a one-click LAN desktop host."""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser
from contextlib import contextmanager
from multiprocessing import freeze_support
from pathlib import Path
from threading import Thread, current_thread, main_thread
from urllib.request import urlopen


def _snapshot(root: Path) -> tuple[tuple[str, int], ...]:
    """Watch application Python source, including additions and deletions."""
    return tuple(sorted(
        (str(p), p.stat().st_mtime_ns)
        for p in root.rglob("*.py")
        if p.is_file()
    ))


def _stop_process(process: subprocess.Popen) -> None:
    """Shut down the server and any processes in its private POSIX group."""
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=5)


def _port_available(port: int) -> bool:
    """Check availability before launching a second instance."""
    if not 1 <= port <= 65535:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        # Match uvicorn's SO_REUSEADDR semantics: recently closed HTTP
        # connections can retain TIME_WAIT sockets without an active listener.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _select_development_port(requested_port: int | None, *, preferred_port: int = 8080) -> tuple[int, bool]:
    """Auto-select a usable localhost port unless the caller explicitly requested one."""
    if requested_port is not None:
        if not _port_available(requested_port):
            raise ValueError(
                f"Cannot start localhost GUI on port {requested_port}: occupied or invalid. "
                f"Check with: lsof -nP -iTCP:{requested_port} -sTCP:LISTEN"
            )
        return requested_port, False
    if _port_available(preferred_port):
        return preferred_port, False
    # Ask the OS for an ephemeral port, rather than guessing 8081, 8082, ...
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1]), True


def _dev_lock_path(root: Path) -> Path:
    """A stable lock for this checkout, not a lock on an individual TCP port."""
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:20]
    return Path(tempfile.gettempdir()) / f"garment-nesting-dev-{digest}.lock"


@contextmanager
def _dev_instance_lock(root: Path):
    """Hold a cross-process advisory lock for the lifetime of one dev launcher.

    The OS releases this lock even on SIGKILL. Keep the file itself in place
    between runs; unlinking a locked file could allow competing lock inodes.
    """
    with _dev_lock_path(root).open("a+", encoding="utf-8") as state:
        if os.name == "nt":
            import msvcrt

            state.seek(0, os.SEEK_END)
            if state.tell() == 0:
                state.write(" ")
                state.flush()
            state.seek(0)
            try:
                msvcrt.locking(state.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                yield None, _read_dev_state(state)
                return
            try:
                yield state, None
            finally:
                state.seek(0)
                msvcrt.locking(state.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(state.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                yield None, _read_dev_state(state)
                return
            try:
                yield state, None
            finally:
                fcntl.flock(state.fileno(), fcntl.LOCK_UN)


def _read_dev_state(state) -> dict:
    state.seek(0)
    try:
        data = json.loads(state.read())
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_dev_state(state, port: int) -> None:
    state.seek(0)
    state.truncate()
    state.write(json.dumps({"port": port, "launcher_pid": os.getpid()}))
    state.flush()


def _dev_server_revision(port: int) -> str | None:
    """Read the revision of the process actually serving this localhost URL."""
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.75) as response:
            data = json.load(response)
            if data.get("application") == "garment-nesting":
                return data.get("ui_revision", "old build (no revision)")
    except (OSError, ValueError, TypeError):
        pass
    return None


def _restart_existing_development_launcher(root: Path) -> bool:
    """Stop only the verified launcher holding this checkout's lock.

    No signal is sent to arbitrary TCP listeners, other Python programs,
    or unmatched PIDs from a stale lock file.
    """
    if os.name != "posix":
        print("--restart is currently supported for macOS/Linux development only.", file=sys.stderr)
        return False
    with _dev_instance_lock(root) as (owner, existing):
        if owner is not None:
            return True
        pid = existing.get("launcher_pid")
        if not isinstance(pid, int) or pid <= 1 or pid == os.getpid():
            print("Cannot verify existing launcher PID. Refusing to terminate it.", file=sys.stderr)
            return False
        lookup = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, check=False,
        )
        if lookup.returncode != 0 or not all(
            token in lookup.stdout for token in ("-m garment_nesting.app", "dev")
        ):
            print(
                f"PID {pid} is not a verified garment_nesting.app dev process; "
                "refusing to stop it.",
                file=sys.stderr,
            )
            return False
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        with _dev_instance_lock(root) as (owner, _):
            if owner is not None:
                print(f"Stopped old development launcher PID {pid}.", flush=True)
                return True
        time.sleep(0.2)
    print("Old launcher did not exit. Stop it manually; no new server was opened.", file=sys.stderr)
    return False


def _reuse_existing_dev(state: dict, *, show: bool) -> int:
    """A second invocation reuses the current browser URL; never spawns a child."""
    port = state.get("port")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        print("Development launcher already starting; no additional server opened.")
        return 0
    url = f"http://127.0.0.1:{port}"
    print(f"Development server already running or starting at {url}; reusing it.")
    from garment_nesting.webapp import UI_REVISION

    serving_revision = _dev_server_revision(port)
    if serving_revision and serving_revision != UI_REVISION:
        print(
            f"STALE GUI: running revision {serving_revision}; "
            f"current source revision {UI_REVISION}. "
            "Run: python -m garment_nesting.app dev --restart",
            file=sys.stderr,
        )
    if show:
        try:
            with urlopen(f"{url}/health", timeout=0.5) as response:
                if response.status == 200 and b'"application":"garment-nesting"' in response.read():
                    webbrowser.open(url)
        except OSError:
            print("Existing server is starting; open the URL when ready.")
    return 0


def _watch_parent_pipe(read_fd: int) -> None:
    """Stop an orphan server if its supervising dev process disappears.

    The parent holds the write side of the pipe open. A forced parent kill
    closes that descriptor, delivering EOF even though no signal is sent to
    this server (which runs in a separate process group).
    """
    try:
        while os.read(read_fd, 1):
            pass
    except OSError:
        pass
    finally:
        os.close(read_fd)
    os._exit(0)


def _spawn_development_child(command: list[str]) -> tuple[subprocess.Popen, int | None]:
    """Use a POSIX pipe watchdog so SIGKILL of the parent cannot orphan the server."""
    if os.name != "posix":
        return subprocess.Popen(command), None
    read_fd, write_fd = os.pipe()
    try:
        child = subprocess.Popen(
            [*command, "--parent-watch-fd", str(read_fd)],
            pass_fds=(read_fd,),
            start_new_session=True,
        )
    except BaseException:
        os.close(write_fd)
        raise
    finally:
        os.close(read_fd)
    return child, write_fd


def _exit_on_signal(_signum, _frame) -> None:
    """Let finally terminate the child on SIGTERM or terminal hang-up."""
    raise KeyboardInterrupt



def run_development_server(
    port: int | None = None, *, show: bool = True, restart: bool = False,
) -> int:
    """Enforce one dev server per checkout, with reuse and orphan protection."""
    root = Path(__file__).resolve().parent
    if restart and not _restart_existing_development_launcher(root):
        return 2
    with _dev_instance_lock(root) as (owner, existing):
        if owner is None:
            return _reuse_existing_dev(existing, show=show)
        try:
            selected_port, used_fallback = _select_development_port(port)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        _write_dev_state(owner, selected_port)
        from garment_nesting.webapp import UI_REVISION

        print(f"Loaded UI revision: {UI_REVISION}", flush=True)
        print(f"Source package: {root}", flush=True)
        if used_fallback:
            print(
                f"Port 8080 occupied; using port {selected_port} "
                "for this single development instance.",
                flush=True,
            )
        return _run_owned_dev_server(selected_port, show=show, root=root)


def _run_owned_dev_server(port: int, *, show: bool, root: Path) -> int:
    """Watch Python files and supervise exactly one NiceGUI child."""
    command = [
        sys.executable, "-m", "garment_nesting.app",
        "serve", "--host", "127.0.0.1", "--port", str(port),
    ]
    seen = _snapshot(root)
    process: subprocess.Popen | None = None
    parent_pipe: int | None = None
    browser_opened = not show
    previous_handlers = {}
    if current_thread() is main_thread():
        for signum in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):
            if signum is not None:
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, _exit_on_signal)
    try:
        while True:
            if process is None:
                process, parent_pipe = _spawn_development_child(command)
                print(
                    f"Local GUI: http://127.0.0.1:{port} (server PID {process.pid})",
                    flush=True,
                )
            if process.poll() is not None:
                print(f"Local GUI stopped (exit {process.returncode})", file=sys.stderr)
                return process.returncode or 1
            if not browser_opened:
                try:
                    with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.25) as response:
                        if response.status == 200:
                            webbrowser.open(f"http://127.0.0.1:{port}")
                            browser_opened = True
                except OSError:
                    pass
            time.sleep(0.4)
            updated = _snapshot(root)
            if updated != seen:
                print("Python source changed; restarting local GUI", flush=True)
                _stop_process(process)
                if parent_pipe is not None:
                    os.close(parent_pipe)
                    parent_pipe = None
                process = None
                seen = updated
    except KeyboardInterrupt:
        return 0
    finally:
        if process is not None:
            _stop_process(process)
        if parent_pipe is not None:
            os.close(parent_pipe)
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Garment Nesting LAN application")
    commands = parser.add_subparsers(dest="command")
    dev = commands.add_parser("dev", help="Localhost web GUI, reload Python edits")
    dev.add_argument(
        "--port", type=int, default=None,
        help="Use this exact port (default: 8080, or an automatic free port if occupied)",
    )
    dev.add_argument("--no-browser", action="store_true", help="Do not launch a browser tab")
    dev.add_argument(
        "--restart", action="store_true",
        help="Stop the verified existing dev launcher for this checkout and start fresh",
    )
    serve = commands.add_parser("serve", help="Run the web GUI (used by desktop host)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--parent-watch-fd", type=int, default=None, help=argparse.SUPPRESS)
    commands.add_parser("smoke", help="Verify bundled GUI and native dependencies")
    args = parser.parse_args(argv)

    if args.command == "smoke":
        import packingsolver.irregular  # noqa: F401
        import resvg_py  # noqa: F401
        from nicegui import ui  # noqa: F401

        from garment_nesting.input.svg import inspect_svg  # noqa: F401

        marker = os.environ.get("NESTING_SMOKE_FILE")
        if marker:
            Path(marker).write_text("NestingOptimizer bundled dependencies OK\n", encoding="utf-8")
        else:
            print("NestingOptimizer bundled dependencies OK")
        return 0
    if args.command == "dev":
        return run_development_server(
            args.port, show=not args.no_browser, restart=args.restart,
        )
    if args.command == "serve":
        if args.parent_watch_fd is not None:
            Thread(target=_watch_parent_pipe, args=(args.parent_watch_fd,), daemon=True).start()
        from garment_nesting.webapp import run_server

        run_server(host=args.host, port=args.port, reload=False, show=False)
        return 0
    if args.command is None:
        from garment_nesting.desktop import launch

        launch()
        return 0
    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
