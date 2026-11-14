"""Minimal one-click desktop launcher for a bundled LAN web server."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.request import urlopen

PORT = 8080


def data_directory() -> Path:
    """Use a writable directory outside the read-only packaged application."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        root = base / "NestingOptimizer"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "NestingOptimizer"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        root = root / "NestingOptimizer"
    root.mkdir(parents=True, exist_ok=True)
    return root


def lan_address() -> str | None:
    """Best-effort LAN address discovery; local loopback is not advertised to others."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conn:
            conn.connect(("192.0.2.1", 80))  # Route discovery; sends no packet.
            address = conn.getsockname()[0]
            if not address.startswith("127.") and address != "0.0.0.0":
                return address
    except OSError:
        pass
    return None


def server_command(port: int = PORT) -> list[str]:
    """Support both editable sources and PyInstaller-frozen desktop binaries."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "serve", "--host", "0.0.0.0", "--port", str(port)]
    return [
        sys.executable, "-m", "garment_nesting.app", "serve",
        "--host", "0.0.0.0", "--port", str(port),
    ]


def server_healthy(port: int = PORT) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.25) as response:
            return (
                response.status == 200
                and b'"application":"garment-nesting"' in response.read()
            )
    except (OSError, TimeoutError):
        return False


def launch() -> None:
    """Desktop Start/Stop panel; the browser UI runs in a subprocess."""
    import tkinter as tk
    from tkinter import ttk

    window = tk.Tk()
    window.title("Garment Nesting Optimizer")
    window.geometry("470x260")
    window.resizable(False, False)

    process: subprocess.Popen | None = None
    address = lan_address()
    host_url = f"http://{address}:{PORT}" if address else ""
    local_url = f"http://127.0.0.1:{PORT}"
    status = tk.StringVar(value="Server stopped")
    share_url = tk.StringVar(value="Press Start Server to begin")

    body = ttk.Frame(window, padding=20)
    body.pack(expand=True, fill="both")
    ttk.Label(body, text="Garment Nesting Optimizer", font=("Arial", 16, "bold")).pack(
        anchor="w", pady=(0, 8),
    )
    ttk.Label(body, textvariable=status).pack(anchor="w", pady=(0, 8))
    ttk.Label(body, textvariable=share_url, wraplength=425).pack(
        anchor="w", pady=(0, 12),
    )

    buttons = ttk.Frame(body)
    buttons.pack(anchor="w", fill="x")
    log_path = data_directory() / "server.log"

    def start() -> None:
        nonlocal process
        if process is not None and process.poll() is None:
            return
        if server_healthy():
            status.set("Port 8080 is already serving this application")
            return
        # Never pretend the server started successfully until /health responds.
        with log_path.open("ab") as logfile:
            env = os.environ.copy()
            if getattr(sys, "frozen", False):
                env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            process = subprocess.Popen(
                server_command(), stdout=logfile, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, env=env,
            )
        status.set("Starting LAN server…")
        share_url.set("Checking availability…")

    def stop() -> None:
        nonlocal process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=4)
        process = None
        status.set("Server stopped")
        share_url.set("Press Start Server to begin")

    def open_browser() -> None:
        if server_healthy():
            webbrowser.open(local_url)

    def copy_url() -> None:
        if server_healthy():
            window.clipboard_clear()
            window.clipboard_append(host_url or local_url)
            window.update()

    ttk.Button(buttons, text="Start Server", command=start).pack(
        side="left", padx=(0, 6),
    )
    ttk.Button(buttons, text="Stop", command=stop).pack(side="left", padx=(0, 6))
    ttk.Button(buttons, text="Open Browser", command=open_browser).pack(side="left")
    ttk.Button(body, text="Copy LAN Link", command=copy_url).pack(anchor="w", pady=10)
    ttk.Label(body, text=f"Diagnostic log: {log_path}", wraplength=425).pack(anchor="w")

    def monitor() -> None:
        if process is not None:
            if process.poll() is None and server_healthy():
                status.set("Server running · ready for LAN browsers")
                share_url.set(
                    f"LAN: {host_url}" if host_url else
                    "LAN IP not detected; check network settings. "
                    f"Local access: {local_url}"
                )
            elif process.poll() is not None:
                status.set(f"Server stopped unexpectedly (exit {process.returncode})")
                share_url.set(f"See diagnostic log: {log_path}")
        window.after(850, monitor)

    def close() -> None:
        stop()
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", close)
    monitor()
    window.mainloop()
