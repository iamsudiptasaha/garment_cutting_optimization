"""Create OS-native desktop bundle and zip it for GitHub Actions."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "NestingOptimizer"


def build(target: str) -> Path:
    if target not in ("windows-x64", "macos-arm64", "macos-x64"):
        raise ValueError(f"Unknown packaging target: {target}")
    is_mac = target.startswith("macos-")
    if is_mac != (sys.platform == "darwin"):
        raise RuntimeError(f"Cannot produce {target} on host {sys.platform}")
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", NAME,
        "--collect-all", "nicegui",
        "--collect-all", "packingsolver",
        "--collect-all", "resvg_py",
        "--collect-all", "fontTools",
        "--collect-all", "shapely",
        "--collect-submodules", "garment_nesting",
        str(ROOT / "src/garment_nesting/app.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    archive = release / f"{NAME}-{target}.zip"
    archive.unlink(missing_ok=True)
    if is_mac:
        application = ROOT / "dist" / f"{NAME}.app"
        if not application.is_dir():
            raise RuntimeError("PyInstaller did not produce the macOS .app")
        subprocess.run([
            "ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
            str(application), str(archive),
        ], check=True)
    else:
        directory = ROOT / "dist" / NAME
        if not (directory / f"{NAME}.exe").is_file():
            raise RuntimeError("PyInstaller did not produce the Windows .exe")
        shutil.make_archive(
            str(archive.with_suffix("")), "zip",
            root_dir=str(ROOT / "dist"), base_dir=NAME,
        )
    print(f"PACKAGED: {archive}")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    build(args.target)


if __name__ == "__main__":
    main()
