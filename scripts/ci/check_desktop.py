"""Verify frozen app starts and imports packaged GUI and solver libraries."""
from __future__ import annotations

import argparse
import os
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
            [str(executable), "smoke"],
            cwd=ROOT, capture_output=True, text=True, timeout=90, env=env,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        if result.returncode:
            raise RuntimeError(
                f"Frozen application smoke test failed ({result.returncode})"
            )
        if not marker.exists() or "bundled dependencies OK" not in marker.read_text():
            raise RuntimeError("Frozen app did not load the GUI and solver libraries")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    check(args.target)


if __name__ == "__main__":
    main()
