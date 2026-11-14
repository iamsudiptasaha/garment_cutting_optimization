"""Fabric and nesting constraints remain validated before solver integration."""
from __future__ import annotations

from copy import deepcopy
from math import inf, nan
from pathlib import Path

import pytest

from garment_nesting.job_config import (
    DEFAULT_FABRIC_SETTINGS,
    edit_fabric_setting,
    job_input_payload,
    nonnegative_inches,
    piece_margin_from_input,
    validate_fabric_settings,
)
from garment_nesting.job_selection import edit_pattern, namespace_uploaded_rows
from garment_nesting.webapp import inspect_upload

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "FC_HH_Full_Pyjama.svg"


def test_defaults_are_fixed_width_open_length():
    settings = validate_fabric_settings(DEFAULT_FABRIC_SETTINGS)
    assert settings["fabric_width_in"] == 36
    assert settings["piece_clearance_in"] == 0.04
    assert settings["max_length_in"] is None
    assert settings["time_limit_seconds"] == 30


def test_editing_fabric_settings_preserves_consistent_usable_width():
    settings = DEFAULT_FABRIC_SETTINGS.copy()
    edit_fabric_setting(settings, "fabric_width_in", 40)
    edit_fabric_setting(settings, "fabric_left_margin_in", "0.25")
    edit_fabric_setting(settings, "fabric_right_margin_in", 0.5)
    edit_fabric_setting(settings, "piece_clearance_in", "0.06")
    edit_fabric_setting(settings, "fabric_start_margin_in", 1.5)
    edit_fabric_setting(settings, "fabric_end_margin_in", 1.0)
    edit_fabric_setting(settings, "max_length_in", 100)
    edit_fabric_setting(settings, "time_limit_seconds", "90")
    assert settings["fabric_width_in"] - settings["fabric_left_margin_in"] - settings[
        "fabric_right_margin_in"
    ] == 39.25
    assert settings["max_length_in"] == 100
    assert settings["time_limit_seconds"] == 90


@pytest.mark.parametrize(
    "field,value",
    [
        ("fabric_width_in", 0),
        ("fabric_width_in", -1),
        ("fabric_left_margin_in", 100),
        ("fabric_right_margin_in", 36),
        ("piece_clearance_in", -0.001),
        ("piece_clearance_in", nan),
        ("fabric_end_margin_in", inf),
        ("max_length_in", 0),
        ("max_length_in", -3),
        ("time_limit_seconds", 0),
        ("time_limit_seconds", 3601),
        ("time_limit_seconds", 2.5),
        ("time_limit_seconds", True),
    ],
)
def test_fabric_invalid_inputs_are_atomic(field, value):
    settings = DEFAULT_FABRIC_SETTINGS.copy()
    original = deepcopy(settings)
    with pytest.raises(ValueError):
        edit_fabric_setting(settings, field, value)
    assert settings == original


def test_fabric_max_length_must_allow_start_end_reserves():
    settings = DEFAULT_FABRIC_SETTINGS.copy()
    edit_fabric_setting(settings, "fabric_start_margin_in", 5)
    edit_fabric_setting(settings, "fabric_end_margin_in", 4)
    with pytest.raises(ValueError, match="Maximum length"):
        edit_fabric_setting(settings, "max_length_in", 9)
    assert settings["max_length_in"] is None
    edit_fabric_setting(settings, "max_length_in", 9.01)
    assert settings["max_length_in"] == 9.01
    edit_fabric_setting(settings, "max_length_in", None)
    assert settings["max_length_in"] is None


def test_invalid_fabric_setting_key_is_rejected():
    settings = DEFAULT_FABRIC_SETTINGS.copy()
    with pytest.raises(ValueError, match="Unknown fabric setting"):
        edit_fabric_setting(settings, "mirror", True)


@pytest.mark.parametrize("value", [-1, nan, inf, None, True, "oops"])
def test_invalid_nonnegative_inches(value):
    with pytest.raises(ValueError):
        nonnegative_inches(value, "Margin", maximum=10)


def test_zero_piece_margin_and_fractional_value_supported():
    assert piece_margin_from_input("0") == 0.0
    assert piece_margin_from_input("0.125") == 0.125


def test_job_payload_omits_zero_copy_and_carries_margins_without_changing_svg():
    before = SAMPLE.read_bytes()
    rows = namespace_uploaded_rows(
        inspect_upload(SAMPLE.name, before), upload_id="one",
    )
    edit_pattern(rows, rows[0]["id"], "qty", 0)
    edit_pattern(rows, rows[1]["id"], "qty", 3)
    edit_pattern(rows, rows[1]["id"], "piece_margin_in", 0.2)
    edit_pattern(rows, rows[1]["id"], "rotation", "0° only")
    settings = DEFAULT_FABRIC_SETTINGS.copy()
    edit_fabric_setting(settings, "fabric_left_margin_in", 0.25)
    edit_fabric_setting(settings, "fabric_right_margin_in", 0.25)
    job = job_input_payload(rows, settings)
    assert len(job["patterns"]) == 43
    assert job["required_pieces"] == 45
    assert job["effective_fabric_width_in"] == 35.5
    assert job["patterns"][0]["group_id"] == rows[1]["group"]
    assert job["patterns"][0]["copies"] == 3
    assert job["patterns"][0]["allowed_rotations_deg"] == [0]
    assert job["patterns"][0]["piece_margin_in"] == 0.2
    assert SAMPLE.read_bytes() == before


def test_job_payload_requires_positive_included_quantity():
    rows = namespace_uploaded_rows(
        inspect_upload(SAMPLE.name, SAMPLE.read_bytes()), upload_id="one",
    )
    for row in rows:
        edit_pattern(rows, row["id"], "qty", 0)
    with pytest.raises(ValueError, match="above zero"):
        job_input_payload(rows, DEFAULT_FABRIC_SETTINGS)
