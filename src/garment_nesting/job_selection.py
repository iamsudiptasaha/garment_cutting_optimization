"""Per-session pattern selection: quantities, inclusion, and grain-safe rotations.

This module transforms input inventory metadata only. It does not modify SVG
files or claim that the current PackingSolver adapter consumes these controls.
"""
from __future__ import annotations

import re

from garment_nesting.job_config import piece_margin_from_input

MAX_COPIES_PER_PATTERN = 10_000
ROTATION_ANGLES = {
    "0° only": (0,),
    "180° only": (180,),
    "0°, 180°": (0, 180),
}
QUANTITY_PATTERN = re.compile(r"[0-9]+")


def quantity_from_input(value: object) -> int:
    """Parse whole copy counts; zero is allowed and produces no solver instances."""
    if isinstance(value, int) and not isinstance(value, bool):
        quantity = value
    elif isinstance(value, float) and value.is_integer():
        quantity = int(value)
    elif isinstance(value, str) and QUANTITY_PATTERN.fullmatch(value.strip()):
        quantity = int(value.strip())
    else:
        raise ValueError("Quantity must be a whole number from 0 to 10,000")
    if not 0 <= quantity <= MAX_COPIES_PER_PATTERN:
        raise ValueError("Quantity must be a whole number from 0 to 10,000")
    return quantity


def namespace_uploaded_rows(rows: list[dict], upload_id: str) -> list[dict]:
    """Use a per-upload stable row key; identical filenames/IDs may recur."""
    if not upload_id:
        raise ValueError("Upload ID must not be empty")
    return [
        {**row, "id": f"{upload_id}:{index}", "source_id": upload_id}
        for index, row in enumerate(rows)
    ]


def edit_pattern(rows: list[dict], row_id: str, field: str, value: object) -> dict:
    """Apply an atomic validated edit to the server-owned state."""
    if field not in {"included", "qty", "rotation", "piece_margin_in"}:
        raise ValueError(f"Field is not editable: {field}")
    row = next((row for row in rows if row["id"] == row_id), None)
    if row is None:
        raise ValueError("Pattern no longer exists; upload it again")
    if field == "included":
        if not isinstance(value, bool):
            raise ValueError("Included must be a checkbox value")
        if value and row["valid"] != "Valid":
            raise ValueError("Invalid cutting geometry cannot be included")
    elif field == "qty":
        value = quantity_from_input(value)
    elif field == "piece_margin_in":
        value = piece_margin_from_input(value)
    elif field == "rotation" and (not isinstance(value, str) or value not in ROTATION_ANGLES):
        raise ValueError("Only 0° and 180° rotations are supported")
    row[field] = value
    return row


def selection_summary(rows: list[dict]) -> dict[str, int]:
    active = [
        row for row in rows
        if row["included"] and row["valid"] == "Valid" and row["qty"] > 0
    ]
    return {
        "imported_patterns": len(rows),
        "included_patterns": len(active),
        "included_pieces": sum(row["qty"] for row in active),
        "excluded_patterns": len(rows) - len(active),
        "invalid_patterns": sum(row["valid"] != "Valid" for row in rows),
    }


def selected_job_rows(rows: list[dict]) -> list[dict]:
    """Make a validated source-qualified selection for a future solver adapter."""
    active = []
    for row in rows:
        if not row["included"]:
            continue
        if row["valid"] != "Valid":
            raise ValueError(f"Invalid pattern is selected: {row['name']}")
        quantity = quantity_from_input(row["qty"])
        if quantity == 0:
            continue
        margin = piece_margin_from_input(row["piece_margin_in"])
        rotation = row["rotation"]
        if rotation not in ROTATION_ANGLES:
            raise ValueError(f"Unsupported rotation for {row['name']}")
        active.append({
            "source_id": row["source_id"],
            "source_file": row["source"],
            "group_id": row["group"],
            "copies": quantity,
            "piece_margin_in": margin,
            "allowed_rotations_deg": list(ROTATION_ANGLES[rotation]),
        })
    return active
