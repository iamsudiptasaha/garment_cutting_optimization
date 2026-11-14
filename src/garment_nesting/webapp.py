"""Local web UI shell. Input parsing is reused, never replaced by GUI code."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from garment_nesting.job_config import (
    DEFAULT_FABRIC_SETTINGS,
    edit_fabric_setting,
    job_input_payload,
)
from garment_nesting.job_selection import (
    edit_pattern,
    namespace_uploaded_rows,
    selection_summary,
)


def _source_revision() -> str:
    """Fingerprint loaded source code so old servers cannot masquerade as updated UI."""
    try:
        return sha256(Path(__file__).read_bytes()).hexdigest()[:12]
    except OSError:
        return "bundled"


UI_REVISION = _source_revision()


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
            "piece_margin_in": 0.0,
        })
    return rows


async def inspect_uploaded_file(file) -> list[dict]:
    """Read NiceGUI's async upload stream before passing bytes to the sync validator."""
    from nicegui import run

    content = await file.read()
    return await run.io_bound(inspect_upload, file.name, content)


def replace_inventory_table_rows(table, rows: list[dict]) -> None:
    """Replace browser table state and explicitly render, including on first upload."""
    table.rows = [row.copy() for row in rows]
    table.update()


async def add_uploaded_patterns(file, rows: list[dict], table) -> int:
    """Import and immediately display uploaded patterns without another UI action."""
    new_rows = await inspect_uploaded_file(file)
    rows.extend(namespace_uploaded_rows(new_rows, uuid4().hex))
    replace_inventory_table_rows(table, rows)
    return len(new_rows)


def run_server(*, host: str, port: int, reload: bool, show: bool) -> None:
    """Serve browser UI; localhost in development and LAN only on explicit launch."""
    from nicegui import app, ui

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"application": "garment-nesting", "status": "ok", "ui_revision": UI_REVISION}

    @ui.page("/")
    def home() -> None:
        rows: list[dict] = []
        fabric_settings = DEFAULT_FABRIC_SETTINGS.copy()
        ui.colors(primary="#17657b")
        ui.add_head_html("""
            <style>
              .nesting-input .q-field__native { font-size: 1.125rem; }
              .nesting-inventory .q-table thead th {
                font-size: 1rem; font-weight: 700;
              }
              .nesting-inventory .q-table tbody td { font-size: 0.975rem; }
              #pattern-editor { scroll-margin-top: 18px; }
            </style>
        """)
        with ui.column().classes("w-full max-w-7xl mx-auto p-5 gap-5"):
            ui.label("Garment Nesting Optimizer").classes("text-4xl font-bold")
            with ui.row().classes("items-center justify-between w-full gap-2"):
                ui.label("Local workspace · Input / Processor / Output").classes(
                    "text-base text-gray-600"
                )
                ui.label(f"UI version: {UI_REVISION}").classes(
                    "text-sm font-medium text-gray-600"
                )
            with ui.row().classes("w-full gap-3"):
                for title, description in (
                    ("1 · Input", "Import and validate SVG patterns"),
                    ("2 · Processor", "Plugin-based experiment runner — next phase"),
                    ("3 · Output", "Compare candidates and export the selected layout"),
                ):
                    with ui.card().classes("flex-1 min-w-60"):
                        ui.label(title).classes("text-lg font-semibold")
                        ui.label(description).classes("text-base text-gray-600")
            with ui.card().classes("w-full"):
                ui.label("Fabric & nesting inputs").classes("text-2xl font-bold")
                ui.label(
                    "Measurements are in inches. Left/right margins reserve unusable "
                    "selvedge; start/end margins reserve roll length. Piece gap is the "
                    "base spacing before each pattern's extra keep-out margin."
                ).classes("text-base text-gray-600")
                dimensions = ui.label().classes("text-lg font-semibold")

                def update_dimensions() -> None:
                    effective = (
                        fabric_settings["fabric_width_in"]
                        - fabric_settings["fabric_left_margin_in"]
                        - fabric_settings["fabric_right_margin_in"]
                    )
                    dimensions.text = (
                        f"Usable width: {effective:g} in · "
                        f"Base piece gap: {fabric_settings['piece_clearance_in']:g} in · "
                        "Length: "
                        + (
                            f"maximum {fabric_settings['max_length_in']:g} in"
                            if fabric_settings["max_length_in"] is not None
                            else "uncapped"
                        )
                    )

                def change_fabric(e, field: str) -> None:
                    previous = fabric_settings[field]
                    try:
                        edit_fabric_setting(fabric_settings, field, e.value)
                    except ValueError as exc:
                        ui.notify(str(exc), type="negative")
                        if e.sender.value != previous:
                            e.sender.set_value(previous)
                    finally:
                        update_dimensions()

                settings_fields = [
                    ("fabric_width_in", "Fabric width (in)", 0.1),
                    ("fabric_left_margin_in", "Left selvedge (in)", 0.01),
                    ("fabric_right_margin_in", "Right selvedge (in)", 0.01),
                    ("fabric_start_margin_in", "Start reserve (in)", 0.01),
                    ("fabric_end_margin_in", "End reserve (in)", 0.01),
                    ("piece_clearance_in", "Base piece gap (in)", 0.01),
                    ("max_length_in", "Max length (in; blank = open)", 0.1),
                    ("time_limit_seconds", "Solver time budget (s)", 1),
                ]
                with ui.grid(columns=4).classes("w-full gap-4"):
                    for field, title, step in settings_fields:
                        with ui.column().classes("w-full gap-1"):
                            ui.label(title).classes(
                                "text-lg font-semibold leading-normal"
                            )
                            ui.number(
                                value=fabric_settings[field],
                                min=0,
                                step=step,
                                on_change=lambda e, field=field: change_fabric(e, field),
                            ).props(
                                f'outlined input-style="font-size: 18px" '
                                f'aria-label="{title}"'
                            ).classes("w-full nesting-input")
                update_dimensions()
            with ui.card().classes("w-full gap-4"):
                ui.label("Pattern inventory").classes("text-2xl font-bold")
                ui.label(
                    "Step 1 · Upload your SVG files"
                ).classes("text-xl font-semibold")
                ui.label(
                    "Select one or more SVG files. Each file is validated automatically, "
                    "and its pattern rows appear below as soon as the import finishes."
                ).classes("text-base text-gray-600")

                async def uploaded(e) -> None:
                    try:
                        count = await add_uploaded_patterns(e.file, rows, table)
                    except (ValueError, OSError, RuntimeError, TypeError) as exc:
                        ui.notify(f"Cannot inspect {e.file.name}: {exc}", type="negative")
                        return
                    refresh(update_table=False)
                    import_status.text = (
                        f"{count} patterns imported from {e.file.name}. "
                        "Edit quantities, inclusion, rotation and margins below."
                    )
                    ui.notify(f"Imported {count} patterns. Review them below.")
                    await ui.run_javascript(
                        'document.getElementById("pattern-editor")'
                        '?.scrollIntoView({behavior: "smooth", block: "start"})'
                    )

                ui.upload(
                    on_upload=uploaded, multiple=True, auto_upload=True,
                    max_file_size=15_000_000, max_files=20,
                ).props("accept=.svg").classes("w-full").style(
                    "max-height: 145px; overflow: auto;"
                )
                ui.label("Step 2 · Review and edit pieces").classes(
                    "text-xl font-semibold"
                ).props("id=pattern-editor")
                import_status = ui.label(
                    "No SVG uploaded yet. The editable table will populate automatically."
                ).classes("text-base text-gray-600")
                ui.label(
                    "Set copies (including zero to skip), inclusion, 0°/180° rotations, "
                    "and optional extra keep-out margins for each piece."
                ).classes("text-base text-gray-600")
                columns = [
                    {"name": "included", "label": "Include", "field": "included", "align": "center"},
                    {"name": "source", "label": "Source SVG", "field": "source", "align": "left"},
                    {"name": "name", "label": "Pattern / Label", "field": "name", "align": "left"},
                    {"name": "valid", "label": "Geometry", "field": "valid", "align": "center"},
                    {"name": "qty", "label": "Copies", "field": "qty", "align": "center"},
                    {"name": "rotation", "label": "Allowed rotation", "field": "rotation"},
                    {"name": "piece_margin_in", "label": "Extra piece margin (in)", "field": "piece_margin_in"},
                ]
                summary = ui.label("0 patterns · 0 pieces selected").classes(
                    "text-lg font-semibold"
                )
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

                table = ui.table(
                    columns=columns,
                    rows=[],  # independent from mutable per-session server inventory
                    row_key="id",
                    pagination={"rowsPerPage": 25},
                ).classes("w-full nesting-inventory").props(
                    'rows-per-page-options="[10,25,50,0]"'
                )
                # Do not hide the table. Quasar may not reveal a hidden table
                # on the first upload; an empty table still shows its columns.
                empty_inventory = ui.label(
                    "Upload an SVG above; editable pattern rows will appear here."
                ).classes("text-base text-gray-600")

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
                      <q-input dense outlined type="number" min="0" max="10000" step="1"
                        style="width: 105px"
                        v-model.number="props.row.qty"
                        :disable="props.row.valid !== 'Valid'"
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

                table.add_slot("body-cell-piece_margin_in", r"""
                    <q-td :props="props">
                      <q-input dense outlined type="number" min="0" max="12" step="0.01"
                        style="width: 125px"
                        v-model.number="props.row.piece_margin_in"
                        :disable="props.row.valid !== 'Valid'"
                        @change="value => $parent.$emit('pattern-change',
                          {id: props.row.id, field: 'piece_margin_in', value: value})" />
                    </q-td>
                """)

                def refresh(*, update_table: bool = True) -> None:
                    totals = selection_summary(rows)
                    summary.text = (
                        f"{totals['included_patterns']} of {totals['imported_patterns']} "
                        f"patterns included · {totals['included_pieces']} pieces to nest · "
                        f"{totals['invalid_patterns']} invalid"
                    )
                    if update_table:
                        replace_inventory_table_rows(table, rows)
                    empty_inventory.set_visibility(not bool(rows))

                def change(e) -> None:
                    try:
                        data = e.args
                        edit_pattern(rows, data["id"], data["field"], data["value"])
                    except (ValueError, KeyError, TypeError) as exc:
                        ui.notify(str(exc), type="negative")
                    finally:
                        refresh()

                table.on("pattern-change", change)

                ui.label(
                    "Zero copies or unchecked patterns contribute no pieces. "
                    "All margins are keep-out/placement inputs, not seam allowances; "
                    "SVG cutting paths are never altered. Settings remain in this "
                    "browser session and are not yet used by the PackingSolver."
                ).classes("text-base text-gray-600")

                with ui.dialog() as preview_dialog, ui.card().classes("w-full max-w-3xl"):
                    ui.label("Validated job configuration").classes("text-2xl font-semibold")
                    preview_output = ui.code("", language="json").classes(
                        "w-full max-h-96 overflow-auto"
                    )
                    ui.button("Close", on_click=preview_dialog.close).props("flat")

                def preview_job() -> None:
                    import json

                    try:
                        payload = job_input_payload(rows, fabric_settings)
                    except ValueError as exc:
                        ui.notify(str(exc), type="negative")
                        return
                    preview_output.content = json.dumps(payload, indent=2)
                    preview_dialog.open()

                ui.button("Preview job inputs", on_click=preview_job).props("outline")

    ui.run(
        host=host, port=port, reload=reload, show=show,
        title="Garment Nesting Optimizer", favicon="✂️",
        show_welcome_message=False,
    )
