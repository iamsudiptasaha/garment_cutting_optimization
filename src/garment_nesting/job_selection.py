"""Per-session pattern selection: quantities, inclusion, and grain-safe rotations.

This module transforms input inventory metadata only. It does not modify SVG
files or claim that the current PackingSolver adapter consumes these controls.
"""
from __future__ import annotations

import re

MAX_COPIES_PER_PATTERN = 10_000
ROTATION_ANGLES = {
    "0° only": (0,),
    "180° only": (180,),
    "0°, 180°": (0, 180),
}
QUANTITY_PATTERN = re.compile(r"[0-9]+")


def quantity_from_input(value: object) -> int:
    """Parse only whole positive quantities (never silently round decimals)."""
    if isinstance(value, bool):
        raise ValueError("Quantity must be a whole number from 1 to 10,000")
    if isinstance(value, int):
        quantity = value
    elif isinstance(value, float) and value.is_integer():
        quantity = int(value)
    elif isinstance(value, str) and QUANTITY_PATTERN.fullmatch(value.strip()):
        quantity = int(value.strip())
    else:
        raise ValueError("Quantity must be a whole number from 1 to 10,000")
    if not 1 <= quantity <= MAX_COPIES_PER_PATTERN:
        raise ValueError("Quantity must be a whole number from 1 to 10,000")
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
    if field not in {"included", "qty", "rotation"}:
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
    elif field == "rotation":
        if not isinstance(value, str) or value not in ROTATION_ANGLES:
            raise ValueError("Only 0° and 180° rotations are supported")
    row[field] = value
    return row


def selection_summary(rows: list[dict]) -> dict[str, int]:
    active = [row for row in rows if row["included"] and row["valid"] == "Valid"]
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
        rotation = row["rotation"]
        if rotation not in ROTATION_ANGLES:
            raise ValueError(f"Unsupported rotation for {row['name']}")
        active.append({
            "source_id": row["source_id"],
            "source_file": row["source"],
            "group_id": row["group"],
            "copies": quantity,
            "allowed_rotations_deg": list(ROTATION_ANGLES[rotation]),
        })
    return active
