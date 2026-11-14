"""Local web UI shell. Input parsing is reused, never replaced by GUI code."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from garment_nesting.job_selection import (
    edit_pattern,
    namespace_uploaded_rows,
    selection_summary,
)


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
    check_by_group = {piece.group_id: piece for piece in verification.checks}
    group_counts = Counter(pattern.group_id for pattern in inventory.patterns)
    rows = []
    for index, pattern in enumerate(inventory.patterns):
        check = check_by_group.get(pattern.group_id)
        issues = list(check.errors) if check else ["Pattern was not geometry-checked"]
        if group_counts[pattern.group_id] > 1:
            issues.append("Duplicate cutting group ID within source SVG")
        valid = not issues and check is not None and check.valid
        rows.append({
            "id": f"{name}:{index}",
            "source": name,
            "name": " | ".join(pattern.labels) or pattern.group_id,
            "group": pattern.group_id,
            "valid": "Valid" if valid else "Invalid",
            "issues": "; ".join(issues),
            "included": valid,
            "qty": 1,
            "rotation": "0°, 180°",
        })
    return rows


async def inspect_uploaded_file(file) -> list[dict]:
    """Read NiceGUI's async upload stream before passing bytes to the sync validator."""
    from nicegui import run

    content = await file.read()
    return await run.io_bound(inspect_upload, file.name, content)


def run_server(*, host: str, port: int, reload: bool, show: bool) -> None:
    """Serve browser UI; localhost in development and LAN only on explicit launch."""
    from nicegui import app, ui

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
                ui.label(
                    "Set copies, select which cutting pieces to nest, and choose the "
                    "allowed grain-safe rotation for each pattern. Invalid patterns "
                    "cannot be included."
                ).classes("text-sm text-gray-600")
                columns = [
                    {"name": "included", "label": "Include", "field": "included", "align": "center"},
                    {"name": "source", "label": "Source SVG", "field": "source", "align": "left"},
                    {"name": "name", "label": "Pattern / Label", "field": "name", "align": "left"},
                    {"name": "valid", "label": "Geometry", "field": "valid", "align": "center"},
                    {"name": "qty", "label": "Copies", "field": "qty", "align": "center"},
                    {"name": "rotation", "label": "Allowed rotation", "field": "rotation"},
                ]
                summary = ui.label("0 patterns · 0 pieces selected").classes("font-semibold")
                table = ui.table(
                    columns=columns,
                    rows=rows,
                    row_key="id",
                    pagination={"rowsPerPage": 25},
                ).classes("w-full").props('rows-per-page-options="[10,25,50,0]"')

                table.add_slot("body-cell-included", r"""
                    <q-td :props="props">
                      <q-checkbox dense v-model="props.row.included"
                        :disable="props.row.valid !== 'Valid'"
                        @update:model-value="value => $parent.$emit('pattern-change',
                          {id: props.row.id, field: 'included', value: value})" />
                    </q-td>
                """)
                table.add_slot("body-cell-valid", r"""
                    <q-td :props="props">
                      <q-badge :color="props.row.valid === 'Valid' ? 'positive' : 'negative'">
                        {{ props.row.valid }}
                        <q-tooltip v-if="props.row.issues">{{ props.row.issues }}</q-tooltip>
                      </q-badge>
                    </q-td>
                """)
                table.add_slot("body-cell-qty", r"""
                    <q-td :props="props">
                      <q-input dense outlined type="number" min="1" max="10000" step="1"
                        style="width: 105px"
                        v-model.number="props.row.qty"
                        :disable="!props.row.included || props.row.valid !== 'Valid'"
                        @change="value => $parent.$emit('pattern-change',
                          {id: props.row.id, field: 'qty', value: value})" />
                    </q-td>
                """)
                table.add_slot("body-cell-rotation", r"""
                    <q-td :props="props">
                      <q-select dense outlined options-dense
                        style="min-width: 140px"
                        v-model="props.row.rotation"
                        :options="['0° only', '180° only', '0°, 180°']"
                        :disable="!props.row.included || props.row.valid !== 'Valid'"
                        @update:model-value="value => $parent.$emit('pattern-change',
                          {id: props.row.id, field: 'rotation', value: value})" />
                    </q-td>
                """)

                def refresh() -> None:
                    totals = selection_summary(rows)
                    summary.text = (
                        f"{totals['included_patterns']} of {totals['imported_patterns']} "
                        f"patterns included · {totals['included_pieces']} pieces to nest · "
                        f"{totals['invalid_patterns']} invalid"
                    )
                    table.rows = list(rows)
                    table.update()

                def change(e) -> None:
                    try:
                        data = e.args
                        edit_pattern(rows, data["id"], data["field"], data["value"])
                    except (ValueError, KeyError, TypeError) as exc:
                        ui.notify(str(exc), type="negative")
                    finally:
                        refresh()

                table.on("pattern-change", change)

                with ui.row().classes("gap-3"):
                    def select_all() -> None:
                        for row in rows:
                            row["included"] = row["valid"] == "Valid"
                        refresh()

                    def exclude_all() -> None:
                        for row in rows:
                            row["included"] = False
                        refresh()

                    ui.button("Include all valid", on_click=select_all).props("outline")
                    ui.button("Exclude all", on_click=exclude_all).props("outline")

                async def uploaded(e) -> None:
                    try:
                        new_rows = await inspect_uploaded_file(e.file)
                    except (ValueError, OSError, RuntimeError, TypeError) as exc:
                        ui.notify(f"Cannot inspect {e.file.name}: {exc}", type="negative")
                        return
                    rows.extend(namespace_uploaded_rows(new_rows, uuid4().hex))
                    refresh()
                    ui.notify(f"Imported {len(new_rows)} patterns from {e.file.name}")

                ui.upload(
                    on_upload=uploaded, multiple=True, auto_upload=True,
                    max_file_size=15_000_000, max_files=20,
                ).props("accept=.svg").classes("w-full")
                ui.label(
                    "Changes apply to this browser session only. Pattern configuration "
                    "will be passed to the solver registry in the next phase. "
                    "Original SVG files remain unchanged."
                ).classes("text-sm text-gray-600")

    ui.run(
        host=host, port=port, reload=reload, show=show,
        title="Garment Nesting Optimizer", favicon="✂️",
        show_welcome_message=False,
    )
