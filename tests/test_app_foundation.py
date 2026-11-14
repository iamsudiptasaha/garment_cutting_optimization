"""GUI foundation tests: existing input pipeline and desktop host contracts."""
from __future__ import annotations

import asyncio
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

from garment_nesting.desktop import lan_address, server_command
from garment_nesting.webapp import (
    inspect_upload,
    inspect_uploaded_file,
    replace_inventory_table_rows,
)

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "FC_HH_Full_Pyjama.svg"


def test_inventory_from_existing_svg_without_mutating_input():
    original = SAMPLE.read_bytes()
    rows = inspect_upload(SAMPLE.name, original)
    assert len(rows) == 44
    assert all(row["source"] == SAMPLE.name for row in rows)
    assert all(row["valid"] == "Valid" for row in rows)
    assert all(row["qty"] == 1 and row["piece_margin_in"] == 0 for row in rows)
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
    # NiceGUI's pytest plugin flags the test process as a screen-test server.
    # A manually spawned production-style subprocess must not inherit that mode.
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("NICEGUI_SCREEN_TEST") or key == "PYTEST_CURRENT_TEST":
            env.pop(key)
    with log_path.open("w", encoding="utf-8") as logfile:
        process = subprocess.Popen(
            [
                sys.executable, "-m", "garment_nesting.app", "dev",
                "--port", str(port), "--no-browser",
            ],
            stdout=logfile,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
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
        # Terminating just the watcher must also release the child listener.
        from garment_nesting.app import _port_available

        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and not _port_available(port):
            time.sleep(0.2)
        assert _port_available(port), "Dev server child retained port after shutdown"


def test_dev_mode_rejects_an_occupied_port(capsys):
    from garment_nesting.app import run_development_server

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        occupied.listen(1)
        assert run_development_server(port, show=False) == 2
        assert str(port) in capsys.readouterr().err


def test_dev_watcher_detects_python_file_changes(tmp_path):
    from garment_nesting.app import _snapshot

    before = _snapshot(tmp_path)
    file = tmp_path / "ui.py"
    file.write_text("version = 1\n", encoding="utf-8")
    added = _snapshot(tmp_path)
    assert added != before
    file.write_text("version = 2\n", encoding="utf-8")
    assert _snapshot(tmp_path) != added
    file.unlink()
    assert _snapshot(tmp_path) == before


def test_nicegui_async_upload_is_awaited_before_validation(monkeypatch):
    """Uploaded bytes must be read, not passed as a coroutine to len()."""
    from nicegui import run

    payload = SAMPLE.read_bytes()
    called = []

    class UploadedFile:
        name = SAMPLE.name

        async def read(self):
            called.append("read")
            return payload

    async def fake_io_bound(function, name, data):
        assert isinstance(data, bytes)
        assert name == SAMPLE.name
        called.append("validate")
        return function(name, data)

    monkeypatch.setattr(run, "io_bound", fake_io_bound)
    rows = asyncio.run(inspect_uploaded_file(UploadedFile()))
    assert called == ["read", "validate"]
    assert len(rows) == 44
    assert all(row["valid"] == "Valid" for row in rows)



def test_first_svg_upload_reveals_populated_table_without_extra_click():
    """Initial table must be an independent collection, and explicitly replaced."""
    original = []
    class MockTable:
        def __init__(self):
            self.rows = []
            self.visible = False
            self.calls = 0

        def update_rows(self, rows, *, clear_selection):
            assert clear_selection is False
            self.rows = rows
            self.calls += 1

    table = MockTable()
    rows = inspect_upload(SAMPLE.name, SAMPLE.read_bytes())
    original.extend(rows)
    replace_inventory_table_rows(table, original)
    assert table.visible is True
    assert table.calls == 1
    assert len(table.rows) == 44
    assert table.rows is not original
    assert table.rows[0] is not original[0]
    original[0]["qty"] = 7
    assert table.rows[0]["qty"] == 1  # subsequent mutation doesn't alias widget state
    replace_inventory_table_rows(table, original)
    assert table.rows[0]["qty"] == 7
    replace_inventory_table_rows(table, [])
    assert table.visible is False



def test_default_dev_port_auto_falls_back_without_touching_other_listener():
    """Explicit ports remain strict; unqualified dev start finds an OS-free port."""
    from garment_nesting.app import _select_development_port

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        taken = occupied.getsockname()[1]
        selected, fallback = _select_development_port(None, preferred_port=taken)
        assert fallback is True
        assert 1 <= selected <= 65535
        assert selected != taken
        # Occupied socket is still bound; we must never terminate unknown listeners.
        with pytest.raises(ValueError, match="occupied or invalid"):
            _select_development_port(taken)
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", selected))


@pytest.mark.skipif(os.name != "posix", reason="POSIX parent pipe watchdog")
def test_dev_child_releases_port_after_parent_sigkill(tmp_path):
    """SIGKILL cannot trigger a parent's finally: the child must detect EOF itself."""
    from garment_nesting.app import _port_available

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    log_path = tmp_path / "parent-death.log"
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("NICEGUI_SCREEN_TEST") or key == "PYTEST_CURRENT_TEST":
            env.pop(key)
    with log_path.open("w", encoding="utf-8") as logfile:
        parent = subprocess.Popen(
            [
                sys.executable, "-m", "garment_nesting.app", "dev",
                "--port", str(port), "--no-browser",
            ],
            stdout=logfile,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    child_pid = None
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if parent.poll() is not None:
                break
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("Development server never started: " + log_path.read_text()[-3000:])

        logs = log_path.read_text(encoding="utf-8")
        match = re.search(r"server PID (\d+)", logs)
        assert match, logs
        child_pid = int(match.group(1))
        # Kill only the watcher, not the child process group.
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=5)

        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not _port_available(port):
            time.sleep(0.2)
        assert _port_available(port), "Orphan server retained port after parent SIGKILL"
    finally:
        if parent.poll() is None:
            try:
                os.killpg(parent.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            parent.wait(timeout=5)
        if child_pid is not None:
            try:
                os.killpg(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
