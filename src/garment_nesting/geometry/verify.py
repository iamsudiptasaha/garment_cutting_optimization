"""Independent cross-tolerance geometry checks before nesting."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from shapely.affinity import affine_transform
from shapely.geometry import Polygon

from garment_nesting.geometry.audit import audit_svg, flatten_path
from garment_nesting.geometry.curve_guard import verify_curve_envelope
from garment_nesting.geometry.repair import normalize_polygon
from garment_nesting.importers.svg import SVG_NS, inspect_svg


@dataclass(frozen=True)
class Verification:
    group_id: str
    valid: bool
    area_delta_pct: float | None
    boundary_deviation_mm: float | None
    errors: tuple[str, ...]
    repaired: bool
    repair_details: str | None
    source_curve_guard_passed: bool
    source_curve_guard_mm: float | None
    minimum_solver_buffer_mm: float | None


@dataclass(frozen=True)
class VerificationReport:
    source: str
    tolerance_mm: float
    checks: tuple[Verification, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(item.valid for item in self.checks)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "tolerance_mm": self.tolerance_mm,
            "passed": self.passed,
            "checks": [asdict(item) for item in self.checks],
        }


def _transform_issues(path: str | Path) -> set[str]:
    """Identify transformed cutting outlines, including ancestor transforms."""
    root = ET.parse(path).getroot()
    issues: set[str] = set()

    def walk(node: ET.Element, transformed: bool = False, pattern_id: str | None = None) -> None:
        transformed = transformed or bool(node.get("transform"))
        if node.tag == f"{{{SVG_NS}}}g" and any(
            child.tag == f"{{{SVG_NS}}}path" for child in node
        ):
            pattern_id = node.get("id")
        if node.tag == f"{{{SVG_NS}}}path" and transformed and pattern_id:
            issues.add(pattern_id)
        for child in node:
            walk(child, transformed, pattern_id)

    walk(root)
    return issues


def verify_svg(
    path: str | Path,
    tolerance_mm: float = 0.25,
    max_area_delta_pct: float = 0.1,
    max_boundary_deviation_mm: float | None = None,
) -> VerificationReport:
    """Check coarse/fine approximations and reject unhandled transforms.

    Also certify that the *original* Bézier curves stay within a conservative
    buffer around the repaired polygon using control-hull subdivision.
    This is a directed boundary check, not a cutter-ready collision proof.
    """
    if tolerance_mm <= 0 or max_area_delta_pct < 0:
        raise ValueError("Tolerance must be positive and area limit nonnegative")
    if max_boundary_deviation_mm is None:
        max_boundary_deviation_mm = tolerance_mm
    if max_boundary_deviation_mm < 0:
        raise ValueError("Boundary deviation limit must be nonnegative")

    inventory = inspect_svg(path)
    audit = audit_svg(path, tolerance_mm)
    vx, vy, vw, _ = inventory.view_box
    scale = inventory.width_mm / vw
    transformed = _transform_issues(path)
    checks: list[Verification] = []
    for pattern, item in zip(inventory.patterns, audit.pieces, strict=True):
        errors = list(item.errors)
        delta = None
        deviation = None
        source_guard_passed = False
        source_guard_mm = None
        minimum_solver_buffer_mm = None
        if pattern.group_id in transformed:
            errors.append("Cutting outline or ancestor has an unsupported transform")
        if not errors:
            try:
                coarse = normalize_polygon(
                    Polygon(flatten_path(pattern.path_d, tolerance_mm / scale)),
                    max_deviation=tolerance_mm / scale,
                    max_remnant_length=tolerance_mm / scale,
                ).polygon
                fine = normalize_polygon(
                    Polygon(flatten_path(pattern.path_d, tolerance_mm / (4 * scale))),
                    max_deviation=tolerance_mm / scale,
                    max_remnant_length=tolerance_mm / scale,
                ).polygon
                delta = abs(coarse.area - fine.area) / fine.area * 100
                deviation = coarse.boundary.hausdorff_distance(fine.boundary) * scale
                if delta > max_area_delta_pct:
                    errors.append("Area changes beyond permitted tolerance")
                if deviation > max_boundary_deviation_mm:
                    errors.append("Boundary deviation exceeds permitted tolerance")
                if not errors:
                    original_mm_polygon = affine_transform(
                        coarse,
                        [scale, 0, 0, scale, -vx * scale, -vy * scale],
                    )
                    guard = verify_curve_envelope(
                        pattern.path_d,
                        original_mm_polygon,
                        scale_mm_per_unit=scale,
                        viewbox_origin=(vx, vy),
                        tolerance_mm=tolerance_mm,
                    )
                    source_guard_passed = True
                    source_guard_mm = guard.tolerance_mm
                    # Advisory for the future solver; no placement engine exists yet.
                    minimum_solver_buffer_mm = guard.tolerance_mm
            except (ValueError, TypeError, IndexError) as exc:
                errors.append(str(exc))
        checks.append(Verification(
            group_id=pattern.group_id,
            valid=not errors,
            area_delta_pct=None if delta is None else round(delta, 6),
            boundary_deviation_mm=None if deviation is None else round(deviation, 6),
            errors=tuple(errors),
            repaired=item.repaired,
            repair_details=item.repair_details,
            source_curve_guard_passed=source_guard_passed,
            source_curve_guard_mm=source_guard_mm,
            minimum_solver_buffer_mm=minimum_solver_buffer_mm,
        ))
    return VerificationReport(inventory.source, tolerance_mm, tuple(checks))
