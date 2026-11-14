"""Entrypoint for one-click desktop host and live-reloading localhost development."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from multiprocessing import freeze_support


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Garment Nesting LAN application")
    commands = parser.add_subparsers(dest="command")
    dev = commands.add_parser("dev", help="Localhost web GUI, reload Python edits")
    dev.add_argument("--port", type=int, default=8080)
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
        from garment_nesting.webapp import run_server

        run_server(host="127.0.0.1", port=args.port, reload=True, show=True)
        return 0
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
