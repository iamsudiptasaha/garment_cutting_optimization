"""Validate the fabric and experiment settings before any solver receives them.

All spatial measurements are inches. This is a pure job-input contract:
the current PackingSolver CLI does not yet use these GUI settings.
"""
from __future__ import annotations

from math import isfinite

DEFAULT_FABRIC_SETTINGS = {
    "fabric_width_in": 36.0,
    "fabric_left_margin_in": 0.0,
    "fabric_right_margin_in": 0.0,
    "fabric_start_margin_in": 0.0,
    "fabric_end_margin_in": 0.0,
    "piece_clearance_in": 0.04,
    "max_length_in": None,
    "time_limit_seconds": 30,
}
SPATIAL_SETTINGS = frozenset(DEFAULT_FABRIC_SETTINGS) - {"time_limit_seconds"}
MAX_MEASUREMENT_IN = 100_000.0
MAX_TIME_SECONDS = 3600
MAX_PIECE_MARGIN_IN = 12.0


def nonnegative_inches(value: object, field: str, *, maximum: float) -> float:
    """Parse finite decimal inches and reject booleans, NaN and negative values."""
    try:
        result = float(value) if not isinstance(value, bool) else float("nan")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a finite nonnegative number in inches") from exc
    if not isfinite(result) or not 0 <= result <= maximum:
        raise ValueError(f"{field} must be between 0 and {maximum:g} inches")
    return result


def piece_margin_from_input(value: object) -> float:
    """Extra uniform keep-out around this pattern, not a seam allowance."""
    return nonnegative_inches(value, "Piece margin", maximum=MAX_PIECE_MARGIN_IN)


def _time_seconds(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        result = value
    elif isinstance(value, float) and value.is_integer():
        result = int(value)
    elif isinstance(value, str) and value.strip().isdecimal():
        result = int(value.strip())
    else:
        raise ValueError("Time limit must be a whole number of seconds from 1 to 3600")
    if not 1 <= result <= MAX_TIME_SECONDS:
        raise ValueError("Time limit must be a whole number of seconds from 1 to 3600")
    return result


def validate_fabric_settings(settings: dict) -> dict:
    """Return a normalized snapshot and validate compound width/length constraints."""
    normalized = {}
    for field, default in DEFAULT_FABRIC_SETTINGS.items():
        raw = settings.get(field, default)
        if field == "max_length_in" and (raw is None or raw == ""):
            normalized[field] = None
        elif field == "time_limit_seconds":
            normalized[field] = _time_seconds(raw)
        else:
            normalized[field] = nonnegative_inches(
                raw, field, maximum=MAX_MEASUREMENT_IN,
            )
    width = normalized["fabric_width_in"]
    left = normalized["fabric_left_margin_in"]
    right = normalized["fabric_right_margin_in"]
    if width <= 0 or left + right >= width:
        raise ValueError("Fabric width must exceed its combined left and right margins")
    max_length = normalized["max_length_in"]
    if max_length is not None and (
        max_length <= 0
        or normalized["fabric_start_margin_in"] + normalized["fabric_end_margin_in"]
        >= max_length
    ):
        raise ValueError("Maximum length must exceed the start and end margins")
    return normalized


def edit_fabric_setting(settings: dict, field: str, value: object) -> dict:
    """Apply one edit atomically without leaving cross-field constraints invalid."""
    if field not in DEFAULT_FABRIC_SETTINGS:
        raise ValueError(f"Unknown fabric setting: {field}")
    candidate = {**settings, field: value}
    normalized = validate_fabric_settings(candidate)
    settings.update(normalized)
    return normalized


def job_input_payload(rows: list[dict], settings: dict) -> dict:
    """Validated preview for the next processor phase (not a solver execution)."""
    from garment_nesting.job_selection import selected_job_rows

    patterns = selected_job_rows(rows)
    if not patterns:
        raise ValueError("Include at least one valid pattern with quantity above zero")
    fabric = validate_fabric_settings(settings)
    return {
        "units": "in",
        "fabric": fabric,
        "effective_fabric_width_in": (
            fabric["fabric_width_in"]
            - fabric["fabric_left_margin_in"]
            - fabric["fabric_right_margin_in"]
        ),
        "patterns": patterns,
        "required_pieces": sum(row["copies"] for row in patterns),
        "spacing_convention": (
            "Minimum separation is piece_clearance_in plus each pattern's "
            "piece_margin_in. Extra piece margins do not change original SVG outlines."
        ),
    }
