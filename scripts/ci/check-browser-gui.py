"""Real Chromium acceptance check: SVG import must reveal editable rows immediately.

Run explicitly in CI with playwright and its chromium browser installed.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SVG = ROOT / "samples" / "FC_HH_Full_Pyjama.svg"
ARTIFACTS = ROOT / "browser-test-results"


def _read_health(port: int) -> dict | None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("NICEGUI_SCREEN_TEST") or key == "PYTEST_CURRENT_TEST":
            env.pop(key)

    with (ARTIFACTS / "dev-server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [
                sys.executable, "-m", "garment_nesting.app", "dev",
                "--port", str(port), "--no-browser",
            ],
            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=os.name == "posix",
        )
    try:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            assert server.poll() is None, (ARTIFACTS / "dev-server.log").read_text()
            health = _read_health(port)
            if health and health.get("status") == "ok":
                break
            time.sleep(0.25)
        else:
            raise AssertionError("Server did not start")

        from garment_nesting.webapp import UI_REVISION

        assert health["ui_revision"] == UI_REVISION, (
            "Wrong/stale server responded: " + str(health)
        )
        print(f"Server revision: {UI_REVISION}; port: {port}", flush=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, args=["--no-sandbox"],
            )
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}", wait_until="domcontentloaded")
            page.get_by_text("Step 1 · Upload your SVG files").wait_for(timeout=15000)
            page.get_by_text("Step 2 · Review and edit pieces").wait_for(timeout=15000)
            page.get_by_text(f"UI version: {UI_REVISION}").wait_for()

            label = page.get_by_text("Fabric width (in)", exact=True)
            font_px = label.evaluate(
                "(element) => parseFloat(window.getComputedStyle(element).fontSize)"
            )
            assert font_px >= 18, f"Fabric label too small: {font_px}px"

            # This must update the visible table without Include/Exclude clicks.
            page.locator('input[type="file"]').set_input_files(str(SVG))
            page.get_by_text("44 of 44 patterns included", exact=False).wait_for(
                timeout=45000,
            )
            page.screenshot(
                path=str(ARTIFACTS / "browser-immediately-after-upload.png"),
                full_page=True,
            )
            dom = page.evaluate("""
                () => ({
                    inventoryCount: document.querySelectorAll('.nesting-inventory').length,
                    descendantRows: document.querySelectorAll(
                        '.nesting-inventory .q-table tbody tr').length,
                    inventoryRows: document.querySelectorAll(
                        '.nesting-inventory tbody tr').length,
                    globalRows: document.querySelectorAll('.q-table tbody tr').length,
                    inventoryText: document.querySelector('.nesting-inventory')?.innerText?.slice(0, 1500),
                    inventoryHtml: document.querySelector('.nesting-inventory')?.outerHTML?.slice(0, 3500),
                })
            """)
            print("Browser DOM after upload:", json.dumps(dom, indent=2), flush=True)
            print("Browser page errors:", json.dumps(errors), flush=True)
            (ARTIFACTS / "dom-after-upload.json").write_text(
                json.dumps({"dom": dom, "page_errors": errors}, indent=2),
                encoding="utf-8",
            )
            table_rows = page.locator(".nesting-inventory tbody tr")
            page.wait_for_function(
                "() => document.querySelectorAll('.nesting-inventory tbody tr').length >= 25",
                timeout=15000,
            )
            assert table_rows.count() >= 25
            first_row = table_rows.first.inner_text()
            assert "FC_HH" in first_row or len(first_row.strip()) >= 10, first_row

            # Actual editable quantity control must exist after SVG upload.
            copies = table_rows.first.locator('input[type="number"]').first
            copies.wait_for(timeout=10000)
            assert copies.get_attribute("min") == "0"
            copies.fill("0")
            copies.press("Tab")
            page.get_by_text("43 of 44 patterns included", exact=False).wait_for(
                timeout=15000,
            )
            rendered_count = table_rows.count()
            page.screenshot(
                path=str(ARTIFACTS / "pattern-editor-after-upload.png"),
                full_page=True,
            )
            (ARTIFACTS / "results.json").write_text(
                json.dumps({
                    "server_revision": UI_REVISION,
                    "fabric_field_label_font_px": font_px,
                    "rendered_rows_first_page": rendered_count,
                    "first_row": first_row[:150],
                    "quantity_zero_updated_summary": True,
                    "browser_page_errors": errors,
                }, indent=2),
                encoding="utf-8",
            )
            assert not errors, f"JavaScript runtime errors: {errors}"
            print(
                f"PASS browser: {rendered_count} rendered rows, "
                f"{font_px}px fabric label, quantity 0 updated",
                flush=True,
            )
            browser.close()
    finally:
        if server.poll() is None:
            if os.name == "posix":
                try:
                    os.killpg(server.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
