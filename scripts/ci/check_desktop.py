"""Verify frozen binary imports dependencies AND serves its bundled browser UI."""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def check(target: str) -> None:
    if target == "windows-x64":
        executable = ROOT / "dist/NestingOptimizer/NestingOptimizer.exe"
    elif target in ("macos-arm64", "macos-x64"):
        executable = ROOT / "dist/NestingOptimizer.app/Contents/MacOS/NestingOptimizer"
    else:
        raise ValueError(f"Unknown target: {target}")
    if not executable.is_file():
        raise FileNotFoundError(executable)

    with TemporaryDirectory(prefix="nesting-smoke-") as directory:
        marker = Path(directory) / "success.txt"
        env = os.environ.copy()
        env["NESTING_SMOKE_FILE"] = str(marker)
        result = subprocess.run(
            [str(executable), "smoke"], cwd=ROOT,
            capture_output=True, text=True, timeout=90, env=env,
        )
        if result.returncode:
            raise RuntimeError(
                f"Frozen import smoke test failed ({result.returncode}): {result.stderr}"
            )
        if not marker.exists() or "bundled dependencies OK" not in marker.read_text():
            raise RuntimeError("Frozen app did not import the GUI and native solver")

        port = _free_port()
        logfile = Path(directory) / "server.log"
        with logfile.open("wb") as stream:
            server = subprocess.Popen(
                [str(executable), "serve", "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, env=env,
            )
        try:
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    break
                try:
                    with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as resp:
                        if b'"application":"garment-nesting"' in resp.read():
                            with urlopen(f"http://127.0.0.1:{port}/", timeout=3) as page:
                                if page.status != 200:
                                    raise RuntimeError("GUI home page did not return HTTP 200")
                                if b"Garment Nesting Optimizer" not in page.read():
                                    raise RuntimeError("GUI home page did not render its title")
                            print(f"PASS: frozen {target} GUI serves health and home page")
                            return
                except (URLError, OSError, TimeoutError):
                    pass
                time.sleep(0.5)
            raise RuntimeError(
                f"Frozen web UI did not start: exit={server.poll()}\n"
                f"{logfile.read_text(errors='replace')[-4000:]}"
            )
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    check(args.target)


if __name__ == "__main__":
    main()
