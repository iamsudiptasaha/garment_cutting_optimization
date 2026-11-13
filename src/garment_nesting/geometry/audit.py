"""Approximate SVG paths for diagnostics; original SVG data remains untouched."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path
from shapely.geometry import Polygon

from garment_nesting.geometry.repair import normalize_polygon
from garment_nesting.importers.svg import inspect_svg

Point = tuple[float, float]


@dataclass(frozen=True)
class PieceAudit:
    group_id: str
    label: str
    valid: bool
    area_mm2: float | None
    bounds_mm: tuple[float, float, float, float] | None
    vertices: int
    errors: tuple[str, ...]
    repaired: bool
    repair_details: str | None


@dataclass(frozen=True)
class GeometryAudit:
    source: str
    tolerance_mm: float
    pieces: tuple[PieceAudit, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _distance_to_chord(point: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return ((point[0] - a[0]) ** 2 + (point[1] - a[1]) ** 2) ** 0.5
    # Clamp to the finite chord, not its infinite supporting line.
    # Otherwise a Bézier doubling back beyond an endpoint can be flattened away.
    t = max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (length * length)))
    projection = (a[0] + t * dx, a[1] + t * dy)
    return ((point[0] - projection[0]) ** 2 + (point[1] - projection[1]) ** 2) ** 0.5


def _mid(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _flatten_curve(points: tuple[Point, ...], tolerance: float, depth: int = 0) -> list[Point]:
    a, b = points[0], points[-1]
    if all(_distance_to_chord(p, a, b) <= tolerance for p in points[1:-1]):
        return [b]
    if depth >= 24:
        raise ValueError("Curve subdivision limit exceeded")
    levels = [list(points)]
    while len(levels[-1]) > 1:
        last = levels[-1]
        levels.append([_mid(last[i], last[i + 1]) for i in range(len(last) - 1)])
    left = tuple(level[0] for level in levels)
    right = tuple(level[-1] for level in reversed(levels))
    return _flatten_curve(left, tolerance, depth + 1) + _flatten_curve(
        right, tolerance, depth + 1
    )


def flatten_path(d: str, tolerance: float) -> list[Point]:
    """Flatten one closed SVG subpath in SVG user units."""
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    pen = RecordingPen()
    parse_path(d, pen)
    points: list[Point] = []
    current: Point | None = None
    start: Point | None = None
    closed = False
    for command, args in pen.value:
        if command == "moveTo":
            if start is not None:
                raise ValueError("Multiple subpaths require explicit handling")
            start = current = tuple(args[0])
            points.append(current)
        elif command == "lineTo":
            if current is None:
                raise ValueError("Line without start")
            current = tuple(args[0])
            points.append(current)
        elif command in ("curveTo", "qCurveTo"):
            if current is None:
                raise ValueError("Curve without start")
            control = tuple(tuple(p) for p in args)
            if (command == "curveTo" and len(control) != 3) or (
                command == "qCurveTo" and len(control) != 2
            ):
                raise ValueError("Unsupported compound curve")
            points.extend(_flatten_curve((current, *control), tolerance))
            current = control[-1]
        elif command == "closePath":
            closed = True
        elif command == "endPath":
            pass
        else:
            raise ValueError(f"Unsupported SVG operation: {command}")
    if not closed or start is None:
        raise ValueError("Path is not explicitly closed")
    if points and points[-1] != points[0]:
        points.append(points[0])
    return points


def audit_svg(path: str | Path, tolerance_mm: float = 0.25) -> GeometryAudit:
    """Approximate pieces and report topology; not a certified cutting validation."""
    if tolerance_mm <= 0:
        raise ValueError("tolerance_mm must be positive")
    inventory = inspect_svg(path)
    if inventory.view_box is None or inventory.width_mm is None or inventory.height_mm is None:
        raise ValueError("SVG requires physical width, height and viewBox")
    vx, vy, vw, vh = inventory.view_box
    sx, sy = inventory.width_mm / vw, inventory.height_mm / vh
    if abs(sx - sy) > max(sx, sy) * 1e-5:
        raise ValueError("Non-uniform SVG physical scale is not supported")
    scale = sx
    records: list[PieceAudit] = []
    for pattern in inventory.patterns:
        errors: list[str] = []
        area = None
        bounds = None
        vertices = 0
        repaired = False
        repair_details = None
        if pattern.path_count != 1:
            errors.append("Expected exactly one cutting outline")
        if pattern.source_transform:
            errors.append("Pattern group transform not yet supported")
        try:
            if errors:
                raise ValueError("; ".join(errors))
            points = flatten_path(pattern.path_d, tolerance_mm / scale)
            vertices = len(points) - 1
            physical = [((x - vx) * scale, (y - vy) * scale) for x, y in points]
            normalized = normalize_polygon(
                Polygon(physical),
                max_deviation=tolerance_mm,
                max_remnant_length=tolerance_mm,
            )
            polygon = normalized.polygon
            repaired = normalized.repaired
            repair_details = normalized.details
            area = round(polygon.area, 3)
            bounds = tuple(round(v, 3) for v in polygon.bounds)
        except (ValueError, TypeError, IndexError) as exc:
            if not errors:
                errors.append(str(exc))
        records.append(PieceAudit(
            group_id=pattern.group_id,
            label=" | ".join(pattern.labels),
            valid=not errors,
            area_mm2=area,
            bounds_mm=bounds,
            vertices=vertices,
            errors=tuple(errors),
            repaired=repaired,
            repair_details=repair_details,
        ))
    return GeometryAudit(inventory.source, tolerance_mm, tuple(records))
