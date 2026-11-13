"""Independent cross-tolerance geometry checks before nesting."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from shapely.geometry import Polygon

from garment_nesting.geometry.audit import audit_svg, flatten_path
from garment_nesting.importers.svg import SVG_NS, inspect_svg


@dataclass(frozen=True)
class Verification:
    group_id: str
    valid: bool
    area_delta_pct: float | None
    boundary_deviation_mm: float | None
    errors: tuple[str, ...]


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

    The finer approximation is a numerical reference, not an exact Bézier
    distance proof. This verification does not certify cutter-ready geometry.
    """
    if tolerance_mm <= 0 or max_area_delta_pct < 0:
        raise ValueError("Tolerance must be positive and area limit nonnegative")
    if max_boundary_deviation_mm is None:
        max_boundary_deviation_mm = tolerance_mm
    if max_boundary_deviation_mm < 0:
        raise ValueError("Boundary deviation limit must be nonnegative")

    inventory = inspect_svg(path)
    audit = audit_svg(path, tolerance_mm)
    _, _, vw, _ = inventory.view_box
    scale = inventory.width_mm / vw
    transformed = _transform_issues(path)
    checks: list[Verification] = []
    for pattern, item in zip(inventory.patterns, audit.pieces, strict=True):
        errors = list(item.errors)
        delta = None
        deviation = None
        if pattern.group_id in transformed:
            errors.append("Cutting outline or ancestor has an unsupported transform")
        if not errors:
            try:
                coarse = Polygon(flatten_path(pattern.path_d, tolerance_mm / scale))
                fine = Polygon(flatten_path(pattern.path_d, tolerance_mm / (4 * scale)))
                if not fine.is_valid or fine.is_empty or fine.area <= 0:
                    errors.append("Fine approximation has invalid topology")
                else:
                    delta = abs(coarse.area - fine.area) / fine.area * 100
                    deviation = coarse.boundary.hausdorff_distance(fine.boundary) * scale
                    if delta > max_area_delta_pct:
                        errors.append("Area changes beyond permitted tolerance")
                    if deviation > max_boundary_deviation_mm:
                        errors.append("Boundary deviation exceeds permitted tolerance")
            except (ValueError, TypeError, IndexError) as exc:
                errors.append(str(exc))
        checks.append(Verification(
            group_id=pattern.group_id,
            valid=not errors,
            area_delta_pct=None if delta is None else round(delta, 6),
            boundary_deviation_mm=None if deviation is None else round(deviation, 6),
            errors=tuple(errors),
        ))
    return VerificationReport(inventory.source, tolerance_mm, tuple(checks))
