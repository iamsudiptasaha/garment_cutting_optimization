"""CLI entrypoint for local development and a one-click LAN desktop host."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser
from multiprocessing import freeze_support
from pathlib import Path
from urllib.request import urlopen


def _snapshot(root: Path) -> tuple[tuple[str, int], ...]:
    """Watch application Python source, including additions and deletions."""
    return tuple(sorted(
        (str(p), p.stat().st_mtime_ns)
        for p in root.rglob("*.py")
        if p.is_file()
    ))


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_development_server(port: int, *, show: bool = True) -> int:
    """Hot-reload by supervising the reliable reload=False server mode.

    NiceGUI's own reload process cannot reliably re-execute a Python -m
    module entrypoint. A small parent watcher restarts the server subprocess
    when our application's Python code changes.
    """
    root = Path(__file__).resolve().parent
    command = [
        sys.executable, "-m", "garment_nesting.app",
        "serve", "--host", "127.0.0.1", "--port", str(port),
    ]
    seen = _snapshot(root)
    process: subprocess.Popen | None = None
    browser_opened = not show
    try:
        while True:
            if process is None:
                process = subprocess.Popen(command)
                print(f"Local GUI: http://127.0.0.1:{port}", flush=True)
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
                process = None
                seen = updated
    except KeyboardInterrupt:
        return 0
    finally:
        if process is not None:
            _stop_process(process)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Garment Nesting LAN application")
    commands = parser.add_subparsers(dest="command")
    dev = commands.add_parser("dev", help="Localhost web GUI, reload Python edits")
    dev.add_argument("--port", type=int, default=8080)
    dev.add_argument("--no-browser", action="store_true", help="Do not launch a browser tab")
    serve = commands.add_parser("serve", help="Run the web GUI (used by desktop host)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
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
        return run_development_server(args.port, show=not args.no_browser)
    if args.command == "serve":
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
