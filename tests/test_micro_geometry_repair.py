"""Guardrails for microscopic geometry repair.

Raw SVG must remain untouched; only approximate solver polygons may be fixed.
"""
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from garment_nesting.geometry.audit import audit_svg
from garment_nesting.geometry.repair import normalize_polygon
from garment_nesting.geometry.verify import verify_svg

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "FC_HH_Full_Pyjama.svg"
EXPECTED_REPAIRS = {"_49405941312", "_49405935616", "_49405936960"}


def test_tiny_self_touch_has_explicit_repair_note():
    source = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0), (0.05, 0)])
    result = normalize_polygon(source, max_deviation=0.25, max_remnant_length=0.25)
    assert result.polygon.is_valid
    assert result.repaired
    assert "Self-intersection" in result.details
    assert result.polygon.area == 100


def test_large_spike_is_not_silently_discarded():
    source = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0), (-3, 0)])
    with pytest.raises(ValueError, match="exceeds limits"):
        normalize_polygon(source, max_deviation=0.25, max_remnant_length=0.25)


def test_bowtie_is_not_silently_repaired():
    source = Polygon([(0, 0), (10, 10), (0, 10), (10, 0)])
    with pytest.raises(ValueError, match="Zero-area"):
        normalize_polygon(source, max_deviation=0.25, max_remnant_length=0.25)


def test_sample_44_patterns_pass_and_three_repairs_are_reported():
    audit = audit_svg(SAMPLE)
    assert len(audit.pieces) == 44
    assert all(item.valid for item in audit.pieces), [
        (item.group_id, item.errors) for item in audit.pieces if not item.valid
    ]
    assert {item.group_id for item in audit.pieces if item.repaired} == EXPECTED_REPAIRS
    assert all(item.repair_details for item in audit.pieces if item.repaired)
    verified = verify_svg(SAMPLE)
    assert verified.passed, [
        (item.group_id, item.errors) for item in verified.checks if not item.valid
    ]
    assert {item.group_id for item in verified.checks if item.repaired} == EXPECTED_REPAIRS
