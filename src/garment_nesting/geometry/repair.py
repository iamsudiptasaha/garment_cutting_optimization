"""Conservative, auditable normalization of microscopic SVG outline defects.

Only approximate solver polygons are normalized. Source path strings remain intact.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely import make_valid
from shapely.geometry import Polygon
from shapely.validation import explain_validity


@dataclass(frozen=True)
class NormalizedPolygon:
    polygon: Polygon
    repaired: bool
    details: str | None


def normalize_polygon(
    source: Polygon,
    *,
    max_deviation: float,
    max_remnant_length: float,
    max_area_delta_pct: float = 0.001,
) -> NormalizedPolygon:
    """Repair only a single-polygon self-touch whose changes are negligible.

    Units are the same as the source polygon coordinates. Reject disconnected
    polygons, significant leftover linework, changed area, or shifted boundaries.
    This is not a general-purpose polygon repair method.
    """
    if max_deviation < 0 or max_remnant_length < 0 or max_area_delta_pct < 0:
        raise ValueError("Repair thresholds must be nonnegative")
    if source.is_empty or source.area <= 0:
        raise ValueError("Zero-area or empty polygon")
    if source.is_valid:
        return NormalizedPolygon(source, False, None)

    reason = explain_validity(source)
    fixed = make_valid(source)
    polygons: list[Polygon] = []
    remnant_length = 0.0
    pending = [fixed]
    while pending:
        geom = pending.pop()
        if geom.geom_type in ("GeometryCollection", "MultiPolygon", "MultiLineString"):
            pending.extend(geom.geoms)
        elif geom.geom_type == "Polygon":
            polygons.append(geom)
        elif geom.geom_type in ("LineString", "LinearRing"):
            remnant_length += geom.length
        elif geom.geom_type in ("Point", "MultiPoint"):
            continue
        else:
            raise ValueError(f"Unsupported repair geometry: {geom.geom_type}")

    if len(polygons) != 1:
        raise ValueError(f"{reason}: repair produced {len(polygons)} polygons; rejected")
    polygon = polygons[0]
    if not polygon.is_valid or polygon.is_empty or polygon.area <= 0 or polygon.interiors:
        raise ValueError(f"{reason}: repair produced invalid geometry or a hole")
    area_delta = abs(source.area - polygon.area) / source.area * 100
    deviation = source.boundary.hausdorff_distance(polygon.boundary)
    if (
        remnant_length > max_remnant_length
        or deviation > max_deviation
        or area_delta > max_area_delta_pct
    ):
        raise ValueError(
            f"{reason}: repair exceeds limits "
            f"(remnant={remnant_length:.6f}, "
            f"boundary={deviation:.6f}, area_pct={area_delta:.8f})"
        )
    return NormalizedPolygon(
        polygon,
        True,
        f"{reason}; repaired remnant={remnant_length:.6f}, "
        f"boundary={deviation:.6f}, area_pct={area_delta:.8f}",
    )
