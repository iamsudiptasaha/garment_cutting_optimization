"""Independent source-curve guard; regressions must fail closed."""
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from garment_nesting.geometry.curve_guard import verify_curve_envelope
from garment_nesting.geometry.verify import verify_svg

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "FC_HH_Full_Pyjama.svg"


def _svg(tmp_path: Path, d: str, *, width_mm: int = 100) -> Path:
    source = tmp_path / "shape.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width_mm}mm" height="{width_mm}mm" viewBox="0 0 100 100">'
        f'<g id="piece"><path d="{d}"/><text>PIECE</text></g></svg>',
        encoding="utf-8",
    )
    return source


def test_known_fixture_is_curve_guarded():
    report = verify_svg(SAMPLE)
    assert report.passed
    assert len(report.checks) == 44
    assert all(check.source_curve_guard_passed for check in report.checks)
    assert all(check.source_curve_guard_mm == 0.25 for check in report.checks)
    assert all(check.minimum_solver_buffer_mm == 0.25 for check in report.checks)


def test_curve_overshoot_missed_by_old_flatness_check_is_rejected(tmp_path):
    # Both control points lie on the infinite endpoint line, beyond the finite
    # chord. The old flattening routine collapses this long detour to M0 L10.
    d = "M0 0 C-50 0 -50 0 10 0 L10 10 L0 10 Z"
    report = verify_svg(_svg(tmp_path, d))
    assert not report.passed
    item = report.checks[0]
    assert item.area_delta_pct == 0
    assert item.boundary_deviation_mm == 0
    assert not item.source_curve_guard_passed
    assert item.minimum_solver_buffer_mm is None
    assert any("cannot be certified" in message for message in item.errors)


@pytest.mark.parametrize(
    "d",
    [
        "M0 0 L10 0 L10 10 L0 10 Z",
        "M0 0 Q5 12 10 0 L10 10 L0 10 Z",
        "M0 0 C0 -10 10 -10 10 0 L10 10 L0 10 Z",
    ],
)
def test_multiple_silhouettes_are_guarded(tmp_path, d):
    result = verify_svg(_svg(tmp_path, d))
    assert result.passed, [check.errors for check in result.checks]


def test_guard_uses_mm_not_viewbox_units(tmp_path):
    result = verify_svg(_svg(tmp_path, "M0 0 L10 0 L10 10 L0 10 Z", width_mm=20))
    assert result.passed
    assert result.checks[0].source_curve_guard_mm == 0.25


def test_guards_source_line_segment_not_present_on_polygon():
    d = "M0 0 L10 0 L10 10 L0 10 Z"
    wrong_polygon = Polygon([(0, 0), (5, 0), (5, 10), (0, 10)])
    with pytest.raises(ValueError, match="escapes guarded boundary"):
        verify_curve_envelope(
            d, wrong_polygon, scale_mm_per_unit=1, tolerance_mm=0.25
        )


@pytest.mark.parametrize("tolerance", [0, -1])
def test_invalid_guard_tolerance_rejected(tolerance):
    with pytest.raises(ValueError, match="positive"):
        verify_curve_envelope(
            "M0 0 L1 0 L1 1 L0 1 Z",
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            scale_mm_per_unit=1,
            tolerance_mm=tolerance,
        )
