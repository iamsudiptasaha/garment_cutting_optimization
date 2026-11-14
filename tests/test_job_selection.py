"""Selection controls must change only a validated per-session job specification."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from garment_nesting.job_selection import (
    ROTATION_ANGLES,
    edit_pattern,
    namespace_uploaded_rows,
    quantity_from_input,
    selected_job_rows,
    selection_summary,
)
from garment_nesting.webapp import inspect_upload

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "FC_HH_Full_Pyjama.svg"


def _sample_rows() -> list[dict]:
    return namespace_uploaded_rows(
        inspect_upload(SAMPLE.name, SAMPLE.read_bytes()),
        upload_id="upload-a",
    )


def test_all_reference_patterns_are_enabled_by_default_without_modifying_svg():
    before = SAMPLE.read_bytes()
    rows = _sample_rows()
    assert len(rows) == 44
    assert all(row["valid"] == "Valid" and row["included"] for row in rows)
    assert all(row["qty"] == 1 and row["rotation"] == "0°, 180°" for row in rows)
    assert selection_summary(rows) == {
        "imported_patterns": 44,
        "included_patterns": 44,
        "included_pieces": 44,
        "excluded_patterns": 0,
        "invalid_patterns": 0,
    }
    assert SAMPLE.read_bytes() == before


def test_quantity_and_rotation_edits_affect_selected_job_not_original_input():
    rows = _sample_rows()
    first = rows[0]
    edit_pattern(rows, first["id"], "qty", "4")
    edit_pattern(rows, first["id"], "rotation", "180° only")
    second = rows[1]
    edit_pattern(rows, second["id"], "qty", 2)

    assert selection_summary(rows)["included_pieces"] == 48
    selected = selected_job_rows(rows)
    assert selected[0] == {
        "source_id": "upload-a",
        "source_file": SAMPLE.name,
        "group_id": first["group"],
        "copies": 4,
        "allowed_rotations_deg": [180],
    }
    assert selected[1]["copies"] == 2
    assert selected[1]["allowed_rotations_deg"] == [0, 180]
    assert SAMPLE.read_bytes() == SAMPLE.read_bytes()


def test_inclusion_excludes_instances_without_erasing_quantity_or_rotation():
    rows = _sample_rows()
    first = rows[0]
    edit_pattern(rows, first["id"], "qty", 6)
    edit_pattern(rows, first["id"], "rotation", "0° only")
    edit_pattern(rows, first["id"], "included", False)

    assert selection_summary(rows)["included_patterns"] == 43
    assert selection_summary(rows)["included_pieces"] == 43
    assert all(p["group_id"] != first["group"] for p in selected_job_rows(rows))

    edit_pattern(rows, first["id"], "included", True)
    assert first["qty"] == 6
    assert first["rotation"] == "0° only"
    assert selected_job_rows(rows)[0]["allowed_rotations_deg"] == [0]
    assert selection_summary(rows)["included_pieces"] == 49


@pytest.mark.parametrize(
    "quantity",
    [0, -1, 10001, 2.5, "2.5", "nan", "", None, True, False, "2e3"],
)
def test_invalid_quantities_are_rejected_atomically(quantity):
    rows = _sample_rows()
    old = rows[0]["qty"]
    with pytest.raises(ValueError, match="Quantity"):
        edit_pattern(rows, rows[0]["id"], "qty", quantity)
    assert rows[0]["qty"] == old


@pytest.mark.parametrize("quantity,expected", [(1, 1), ("003", 3), (5.0, 5), (10000, 10000)])
def test_valid_quantities(quantity, expected):
    assert quantity_from_input(quantity) == expected


@pytest.mark.parametrize("value", ["90°", "mirror", "0, 90", "", None, 180])
def test_invalid_rotation_is_rejected_without_changing_row(value):
    rows = _sample_rows()
    old = rows[0]["rotation"]
    with pytest.raises(ValueError, match="Only 0° and 180°"):
        edit_pattern(rows, rows[0]["id"], "rotation", value)
    assert rows[0]["rotation"] == old


def test_supported_rotations_are_exactly_grain_safe():
    assert ROTATION_ANGLES == {
        "0° only": (0,),
        "180° only": (180,),
        "0°, 180°": (0, 180),
    }


def test_duplicate_filenames_are_namespaced_without_cross_file_edits():
    rows_a = namespace_uploaded_rows(
        inspect_upload(SAMPLE.name, SAMPLE.read_bytes()), "first-upload",
    )
    rows_b = namespace_uploaded_rows(
        inspect_upload(SAMPLE.name, SAMPLE.read_bytes()), "second-upload",
    )
    rows = rows_a + rows_b
    assert len({r["id"] for r in rows}) == 88
    edit_pattern(rows, rows_b[0]["id"], "qty", 9)
    assert rows_a[0]["qty"] == 1
    assert rows_b[0]["qty"] == 9
    assert selected_job_rows(rows_a)[0]["source_id"] == "first-upload"
    assert selected_job_rows(rows_b)[0]["source_id"] == "second-upload"


def test_browser_sessions_do_not_share_mutable_pattern_config():
    session_a = _sample_rows()
    session_b = deepcopy(session_a)
    edit_pattern(session_a, session_a[0]["id"], "included", False)
    assert session_b[0]["included"] is True


def test_invalid_patterns_are_excluded_and_cannot_be_enabled():
    rows = _sample_rows()
    rows[0]["valid"] = "Invalid"
    rows[0]["included"] = False
    assert selection_summary(rows)["invalid_patterns"] == 1
    with pytest.raises(ValueError, match="Invalid cutting geometry"):
        edit_pattern(rows, rows[0]["id"], "included", True)
    assert rows[0]["included"] is False
    # A malformed externally supplied selection cannot bypass the invariant.
    rows[0]["included"] = True
    with pytest.raises(ValueError, match="Invalid pattern"):
        selected_job_rows(rows)


def test_rejects_unknown_rows_and_non_editable_fields():
    rows = _sample_rows()
    with pytest.raises(ValueError, match="Pattern no longer exists"):
        edit_pattern(rows, "other-upload", "qty", 3)
    with pytest.raises(ValueError, match="not editable"):
        edit_pattern(rows, rows[0]["id"], "group", "changed")
    assert rows[0]["group"] != "changed"
