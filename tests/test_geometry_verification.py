"""Geometry verification regression tests."""
from pathlib import Path

import pytest

from garment_nesting.geometry.verify import verify_svg

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "FC_HH_Full_Pyjama.svg"


def _write_svg(tmp_path: Path, path: str, group_attr: str = "", parent_attr: str = "") -> Path:
    file = tmp_path / "fixture.svg"
    file.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" '
        'viewBox="0 0 100 100">'
        f'<g {parent_attr}><g id="piece" {group_attr}>'
        f'<path d="{path}"/><text>TEST</text></g></g></svg>',
        encoding="utf-8",
    )
    return file


def test_square_passes(tmp_path):
    report = verify_svg(_write_svg(tmp_path, "M0 0 L10 0 L10 10 L0 10 Z"))
    assert report.passed
    assert report.checks[0].area_delta_pct == 0
    assert report.checks[0].boundary_deviation_mm == 0


def test_self_intersection_fails(tmp_path):
    report = verify_svg(_write_svg(tmp_path, "M0 0 L10 10 L0 10 L10 0 Z"))
    assert not report.passed
    assert any("zero-area" in error.lower() for error in report.checks[0].errors)


@pytest.mark.parametrize("where", ["group", "ancestor"])
def test_transformed_outline_rejected(tmp_path, where):
    attr = 'transform="translate(10 0)"'
    file = _write_svg(
        tmp_path,
        "M0 0 L10 0 L10 10 L0 10 Z",
        group_attr=attr if where == "group" else "",
        parent_attr=attr if where == "ancestor" else "",
    )
    report = verify_svg(file)
    assert not report.passed
    assert any("transform" in e.lower() for e in report.checks[0].errors)


def test_curve_accuracy_metrics(tmp_path):
    report = verify_svg(_write_svg(tmp_path, "M0 0 C0 10 10 10 10 0 L0 0 Z"))
    assert len(report.checks) == 1
    assert report.checks[0].area_delta_pct is not None
    assert report.checks[0].boundary_deviation_mm is not None


def test_reference_inventory_has_44_verification_records():
    report = verify_svg(SAMPLE)
    assert len(report.checks) == 44
    assert len({p.group_id for p in report.checks}) == 44
    # Reference geometry verification is enforced by test_micro_geometry_repair.py.


def test_invalid_tolerance(tmp_path):
    with pytest.raises(ValueError, match="Tolerance"):
        verify_svg(_write_svg(tmp_path, "M0 0 L10 0 L10 10 Z"), tolerance_mm=0)
