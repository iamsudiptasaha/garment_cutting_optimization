"""Local web UI shell. Input parsing is reused, never replaced by GUI code."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory


def inspect_upload(name: str, data: bytes) -> list[dict]:
    """Inventory and validate a file without trusting or persisting its filename."""
    if not name.lower().endswith(".svg"):
        raise ValueError("Only .svg files can be uploaded")
    if len(data) > 15_000_000:
        raise ValueError("SVG file exceeds the 15 MB limit")

    from garment_nesting.geometry.verify import verify_svg
    from garment_nesting.input.svg import inspect_svg

    with TemporaryDirectory(prefix="nesting-upload-") as directory:
        source = Path(directory) / "input.svg"
        source.write_bytes(data)
        inventory = inspect_svg(source)
        verification = verify_svg(source)
    valid_by_group = {piece.group_id: piece.valid for piece in verification.checks}
    return [
        {
            "id": f"{name}:{index}",
            "source": name,
            "name": " | ".join(pattern.labels) or pattern.group_id,
            "group": pattern.group_id,
            "valid": "Valid" if valid_by_group.get(pattern.group_id, False) else "Invalid",
            "qty": 1,
            "rotation": "0°, 180°",
        }
        for index, pattern in enumerate(inventory.patterns)
    ]


def run_server(*, host: str, port: int, reload: bool, show: bool) -> None:
    """Serve browser UI; localhost in development and LAN only on explicit launch."""
    from nicegui import app, run, ui

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"application": "garment-nesting", "status": "ok"}

    @ui.page("/")
    def home() -> None:
        rows: list[dict] = []
        ui.colors(primary="#17657b")
        with ui.column().classes("w-full max-w-6xl mx-auto p-5 gap-5"):
            ui.label("Garment Nesting Optimizer").classes("text-2xl font-semibold")
            ui.label("Local workspace · Input / Processor / Output").classes("text-gray-600")
            with ui.row().classes("w-full gap-3"):
                for title, description in (
                    ("1 · Input", "Import and validate SVG patterns"),
                    ("2 · Processor", "Plugin-based experiment runner — next phase"),
                    ("3 · Output", "Compare candidates and export the selected layout"),
                ):
                    with ui.card().classes("flex-1 min-w-60"):
                        ui.label(title).classes("font-semibold")
                        ui.label(description).classes("text-sm text-gray-600")
            with ui.card().classes("w-full"):
                ui.label("Pattern inventory").classes("text-lg font-semibold")
                ui.label(
                    "Upload one or more SVG files. Files are inspected using the existing "
                    "input and geometry layers; no uploaded files are permanently saved yet."
                ).classes("text-sm text-gray-600")
                columns = [
                    {"name": "source", "label": "Source SVG", "field": "source", "align": "left"},
                    {"name": "name", "label": "Pattern / Label", "field": "name", "align": "left"},
                    {"name": "valid", "label": "Geometry", "field": "valid"},
                    {"name": "qty", "label": "Copies (placeholder)", "field": "qty"},
                    {"name": "rotation", "label": "Rotation (placeholder)", "field": "rotation"},
                ]
                table = ui.table(columns=columns, rows=rows, row_key="id").classes("w-full")

                async def uploaded(e) -> None:
                    try:
                        new_rows = await run.io_bound(
                            inspect_upload, e.file.name, e.file.read(),
                        )
                    except (ValueError, OSError, RuntimeError, TypeError) as exc:
                        ui.notify(f"Cannot inspect {e.file.name}: {exc}", type="negative")
                        return
                    offset = len(rows)
                    for index, row in enumerate(new_rows):
                        row["id"] = f"{offset + index}:{row['id']}"
                    rows.extend(new_rows)
                    table.rows = rows
                    table.update()
                    ui.notify(f"Imported {len(new_rows)} patterns from {e.file.name}")

                ui.upload(
                    on_upload=uploaded, multiple=True, auto_upload=True,
                    max_file_size=15_000_000, max_files=20,
                ).props("accept=.svg").classes("w-full")
                ui.label(
                    "Next: editable quantities, inclusion and rotation controls; "
                    "algorithm registry, benchmark comparison and selected export."
                ).classes("text-sm text-gray-600")

    ui.run(
        host=host, port=port, reload=reload, show=show,
        title="Garment Nesting Optimizer", favicon="✂️",
        show_welcome_message=False,
    )
