"""GUI foundation tests: existing input pipeline and desktop host contracts."""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

from garment_nesting.desktop import lan_address, server_command
from garment_nesting.webapp import inspect_upload

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "FC_HH_Full_Pyjama.svg"


def test_inventory_from_existing_svg_without_mutating_input():
    original = SAMPLE.read_bytes()
    rows = inspect_upload(SAMPLE.name, original)
    assert len(rows) == 44
    assert all(row["source"] == SAMPLE.name for row in rows)
    assert all(row["valid"] == "Valid" for row in rows)
    assert all(row["qty"] == 1 for row in rows)
    assert SAMPLE.read_bytes() == original


@pytest.mark.parametrize("filename", ["not-an-svg.txt", "malicious.svg.exe"])
def test_upload_rejects_non_svg(filename):
    with pytest.raises(ValueError, match="Only .svg"):
        inspect_upload(filename, b"<svg/>")


def test_upload_rejects_oversized_svg():
    with pytest.raises(ValueError, match="15 MB"):
        inspect_upload("large.svg", b"0" * 15_000_001)


def test_source_server_command_uses_active_interpreter(monkeypatch):
    import sys

    monkeypatch.delattr(sys, "frozen", raising=False)
    command = server_command(8099)
    assert command[:3] == [sys.executable, "-m", "garment_nesting.app"]
    assert command[-2:] == ["--port", "8099"]


def test_frozen_server_command_uses_same_bundled_executable(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert server_command() == [
        sys.executable, "serve", "--host", "0.0.0.0", "--port", "8080",
    ]


def test_lan_address_returns_string_or_none():
    address = lan_address()
    assert address is None or (isinstance(address, str) and not address.startswith("127."))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group cleanup")
def test_dev_module_starts_with_hot_reload_enabled(tmp_path):
    """Regression: a live NiceGUI reload child must serve actual HTTP."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    log_path = tmp_path / "dev-server.log"
    with log_path.open("w", encoding="utf-8") as logfile:
        process = subprocess.Popen(
            [
                sys.executable, "-m", "garment_nesting.app", "dev",
                "--port", str(port), "--no-browser",
            ],
            stdout=logfile,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                    if (
                        response.status == 200
                        and b'"application":"garment-nesting"' in response.read()
                    ):
                        with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as page:
                            assert page.status == 200
                            assert b"Garment Nesting Optimizer" in page.read()
                        return
            except OSError:
                pass
            time.sleep(0.25)
        pytest.fail(
            "NiceGUI dev server failed to start with reload=True:\\n"
            + log_path.read_text(encoding="utf-8")[-5000:]
        )
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
