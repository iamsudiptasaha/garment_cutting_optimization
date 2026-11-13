"""Conservative original-curve-to-polygon boundary containment check.

Uses convex-hull containment of SVG Bézier controls, not another flattened
polyline or a sparse set of Bézier samples. Unsupported geometry fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import isfinite

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path
from shapely.geometry import MultiPoint, Polygon

Point = tuple[float, float]


@dataclass(frozen=True)
class CurveGuardResult:
    tolerance_mm: float
    checked_segments: int
    subdivisions: int


def _split_controls(control: tuple[Point, ...]) -> tuple[tuple[Point, ...], tuple[Point, ...]]:
    layers = [list(control)]
    while len(layers[-1]) > 1:
        previous = layers[-1]
        layers.append([
            ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
            for a, b in pairwise(previous)
        ])
    return tuple(layer[0] for layer in layers), tuple(layer[-1] for layer in reversed(layers))


def verify_curve_envelope(
    path_d: str,
    polygon_mm: Polygon,
    *,
    scale_mm_per_unit: float,
    viewbox_origin: Point = (0.0, 0.0),
    tolerance_mm: float,
    max_subdivisions: int = 100_000,
    max_depth: int = 24,
) -> CurveGuardResult:
    """Prove each supported SVG curve lies inside the polygon boundary's buffer.

    Bézier curves are contained in the convex hull of their control points.
    Adaptive de Casteljau subdivision proves hull containment, or fails closed
    if it cannot do so within the search limits. This establishes *directed*
    curve-to-polygon proximity, not a symmetric or topology guarantee.
    """
    if tolerance_mm <= 0 or not isfinite(tolerance_mm):
        raise ValueError("Curve guard tolerance must be finite and positive")
    if scale_mm_per_unit <= 0 or not isfinite(scale_mm_per_unit):
        raise ValueError("Physical scale must be finite and positive")
    if max_subdivisions <= 0 or max_depth <= 0:
        raise ValueError("Curve guard search limits must be positive")
    if polygon_mm.is_empty or not polygon_mm.is_valid:
        raise ValueError("Curve guard requires a nonempty valid polygon")
    buffer = polygon_mm.boundary.buffer(tolerance_mm, quad_segs=16)
    pen = RecordingPen()
    parse_path(path_d, pen)
    current: Point | None = None
    start: Point | None = None
    was_closed = False
    segments = 0
    subdivisions = 0
    vx, vy = viewbox_origin

    def check_segment(points: tuple[Point, ...]) -> None:
        nonlocal segments, subdivisions
        if not all(isfinite(v) for pt in points for v in pt):
            raise ValueError("Nonfinite SVG coordinate")
        stack = [(
            tuple(((x - vx) * scale_mm_per_unit, (y - vy) * scale_mm_per_unit)
                  for x, y in points),
            0,
        )]
        segments += 1
        while stack:
            controls, depth = stack.pop()
            hull = MultiPoint(controls).convex_hull
            if buffer.covers(hull):
                continue
            if len(controls) == 2:
                raise ValueError(f"SVG straight segment {segments} escapes guarded boundary")
            if depth >= max_depth or subdivisions >= max_subdivisions:
                raise ValueError(
                    f"SVG curve segment {segments} cannot be certified within "
                    f"{tolerance_mm:g} mm (subdivision limit or excessive deviation)"
                )
            left, right = _split_controls(controls)
            subdivisions += 1
            stack.extend([(left, depth + 1), (right, depth + 1)])

    for op, args in pen.value:
        if op == "moveTo":
            if start is not None:
                raise ValueError("Multiple SVG subpaths are not supported")
            start = current = tuple(args[0])
        elif op == "lineTo":
            if current is None:
                raise ValueError("SVG line without start")
            next_point = tuple(args[0])
            check_segment((current, next_point))
            current = next_point
        elif op in ("curveTo", "qCurveTo"):
            if current is None:
                raise ValueError("SVG curve without start")
            control = tuple(tuple(p) for p in args)
            expected = 3 if op == "curveTo" else 2
            if len(control) != expected:
                raise ValueError("Unsupported compound SVG curve")
            check_segment((current, *control))
            current = control[-1]
        elif op == "closePath":
            if current is None or start is None:
                raise ValueError("SVG close path without start")
            check_segment((current, start))
            was_closed = True
        elif op == "endPath":
            raise ValueError("Open SVG path is not supported")
        else:
            raise ValueError(f"Unsupported SVG command: {op}")
    if not was_closed or segments == 0:
        raise ValueError("SVG must contain one explicitly closed path")
    return CurveGuardResult(tolerance_mm, segments, subdivisions)
