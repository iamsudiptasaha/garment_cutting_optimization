"""Tests for SVG path approximation and the reference fixture."""
from pathlib import Path

import pytest

from garment_nesting.geometry.audit import audit_svg, flatten_path

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "FC_HH_Full_Pyjama.svg"


def test_square_has_four_edges():
    points = flatten_path("M0 0 L10 0 L10 10 L0 10 Z", 0.1)
    assert points == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]


def test_cubic_is_subdivided():
    points = flatten_path("M0 0 C0 10 10 10 10 0 L0 0 Z", 0.1)
    assert len(points) > 5
    assert points[0] == points[-1]


def test_open_path_is_rejected():
    with pytest.raises(ValueError, match="closed"):
        flatten_path("M0 0 L10 0 L10 10", 0.1)


def test_multiple_subpaths_rejected():
    with pytest.raises(ValueError, match="Multiple subpaths"):
        flatten_path("M0 0 L10 0 Z M20 20 L30 20 Z", 0.1)


def test_tolerance_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        flatten_path("M0 0 L1 0 Z", 0)


def test_reference_svg_audit():
    audit = audit_svg(SAMPLE)
    assert len(audit.pieces) == 44
    assert all(p.group_id and p.label for p in audit.pieces)
    assert all(p.area_mm2 is not None and p.area_mm2 > 0 for p in audit.pieces)
    assert all(p.bounds_mm is not None for p in audit.pieces)
