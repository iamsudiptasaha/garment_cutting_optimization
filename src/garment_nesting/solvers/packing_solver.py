"""PackingSolver irregular input and independent certificate validation (inches).

The original SVG remains unchanged. No placement is accepted just because
PackingSolver emitted a certificate: all pieces and bounds are checked here.
"""
from __future__ import annotations

from collections import Counter
from math import isfinite
from pathlib import Path

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from garment_nesting.geometry.audit import flatten_path
from garment_nesting.geometry.repair import normalize_polygon
from garment_nesting.geometry.verify import verify_svg
from garment_nesting.importers.svg import inspect_svg

MM_PER_INCH = 25.4


def _positive(value: float, name: str) -> None:
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def prepare_instance(
    svg: str | Path,
    fabric_width_in: float,
    *,
    clearance_in: float = 0.04,
    tolerance_in: float = 0.01,
    one_way: bool = False,
) -> tuple[dict, dict]:
    """Build a single fixed-width, open-length irregular packing instance.

    Piece vertices are translated to local origins and converted to inches.
    All pieces are included once. Input SVG grain orientation is assumed correct.
    """
    _positive(fabric_width_in, "fabric_width_in")
    _positive(tolerance_in, "tolerance_in")
    if not isfinite(clearance_in) or clearance_in < 0:
        raise ValueError("clearance_in must be finite and nonnegative")
    verification = verify_svg(svg, tolerance_mm=tolerance_in * MM_PER_INCH)
    if not verification.passed:
        bad = [(p.group_id, p.errors) for p in verification.checks if not p.valid]
        raise ValueError(f"SVG geometry invalid or unsupported: {bad}")

    inventory = inspect_svg(svg)
    if not inventory.patterns:
        raise ValueError("SVG has no cutting patterns")
    ids = [piece.group_id for piece in inventory.patterns]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate cutting pattern IDs")
    if inventory.view_box is None or inventory.width_mm is None or inventory.height_mm is None:
        raise ValueError("SVG must provide physical dimensions and viewBox")
    vx, vy, vw, vh = inventory.view_box
    sx = inventory.width_mm / vw / MM_PER_INCH
    sy = inventory.height_mm / vh / MM_PER_INCH
    if abs(sx - sy) > max(sx, sy) * 1e-5:
        raise ValueError("Non-uniform source SVG scale is unsupported")

    shapes = []
    manifest_pieces = []
    height_bound = clearance_in
    total_area = 0.0
    allowed = [{"start": angle, "end": angle, "mirror": False}
               for angle in ([0] if one_way else [0, 180])]
    for item_id, piece in enumerate(inventory.patterns):
        coords = flatten_path(piece.path_d, tolerance_in / sx)
        poly = Polygon([((x - vx) * sx, (y - vy) * sy) for x, y in coords])
        poly = normalize_polygon(
            poly,
            max_deviation=tolerance_in,
            max_remnant_length=tolerance_in,
        ).polygon
        # Minor smoothing for solver speed; native SVG outlines are preserved.
        poly = poly.simplify(tolerance_in / 2, preserve_topology=True)
        if poly.is_empty or not poly.is_valid or poly.area <= 0 or poly.interiors:
            raise ValueError(f"Unsupported polygon after simplification: {piece.group_id}")
        min_x, min_y, max_x, max_y = poly.bounds
        width = max_x - min_x
        height = max_y - min_y
        if width > fabric_width_in + 1e-7:
            raise ValueError(
                f"PROVEN_INFEASIBLE: {piece.group_id} requires {width:.3f} in width; "
                f"fabric width is {fabric_width_in:.3f} in"
            )
        local = orient(translate(poly, xoff=-min_x, yoff=-min_y), sign=1.0)
        vertices = [{"x": float(x), "y": float(y)} for x, y in list(local.exterior.coords)[:-1]]
        shapes.append({
            "type": "polygon",
            "vertices": vertices,
            "copies": 1,
            "allowed_rotations": allowed,
        })
        manifest_pieces.append({
            "id": item_id,
            "group_id": piece.group_id,
            "label": " | ".join(piece.labels),
            "copies": 1,
            "vertices": vertices,
            "area_sq_in": float(local.area),
        })
        total_area += local.area
        height_bound += height + clearance_in

    solver_instance = {
        "objective": "open-dimension-y",
        "parameters": {"item_item_minimum_spacing": clearance_in},
        "bin_types": [{
            "type": "rectangle",
            "width": float(fabric_width_in),
            "height": float(height_bound),
            "copies": 1,
        }],
        "item_types": shapes,
    }
    manifest = {
        "units": "in",
        "source": str(svg),
        "fabric_width_in": float(fabric_width_in),
        "clearance_in": float(clearance_in),
        "one_way": bool(one_way),
        "required_pieces": len(manifest_pieces),
        "piece_area_sq_in": total_area,
        "pieces": manifest_pieces,
    }
    return solver_instance, manifest


def validate_certificate(manifest: dict, certificate: dict) -> dict:
    """Validate a PackingSolver certificate before treating it as a layout."""
    items_by_id = {p["id"]: p for p in manifest["pieces"]}
    if len(items_by_id) != manifest["required_pieces"]:
        raise ValueError("Manifest contains missing or duplicate item types")
    width = manifest["fabric_width_in"]
    clearance = manifest["clearance_in"]
    bins = certificate.get("bins", [])
    if not bins:
        return {"status": "NOT_FOUND", "required_pieces": len(items_by_id),
                "placed_pieces": 0, "fabric_width_in": width}
    if len(bins) != 1 or bins[0].get("id") != 0 or bins[0].get("copies", 1) != 1:
        raise ValueError("Certificate must contain exactly one fabric strip")

    seen = Counter()
    placed = []
    for item in bins[0].get("items", []):
        idx = item.get("id")
        if idx not in items_by_id:
            raise ValueError(f"Unknown item type ID in solver certificate: {idx}")
        seen[idx] += 1
        if seen[idx] > items_by_id[idx]["copies"]:
            raise ValueError(f"Duplicate piece in solver certificate: {idx}")
        angle = item.get("angle", 0)
        if angle not in ([0] if manifest["one_way"] else [0, 180]):
            raise ValueError(f"Disallowed rotation for item {idx}: {angle}")
        if item.get("mirror", False):
            raise ValueError(f"Mirroring is prohibited for item {idx}")
        x, y = item.get("x"), item.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise ValueError(f"Invalid coordinates for item {idx}")
        if not isfinite(x) or not isfinite(y):
            raise ValueError(f"Nonfinite placement for item {idx}")
        source = Polygon([(p["x"], p["y"]) for p in items_by_id[idx]["vertices"]])
        position = translate(rotate(source, angle, origin=(0, 0)),
                             xoff=x, yoff=y)
        min_x, min_y, max_x, max_y = position.bounds
        if min_x < -1e-5 or max_x > width + 1e-5 or min_y < -1e-5:
            raise ValueError(f"Piece {idx} extends beyond the fabric bounds")
        for prior_id, prior in placed:
            if position.intersection(prior).area > 1e-7:
                raise ValueError(f"Pieces {prior_id} and {idx} overlap")
            if clearance and position.distance(prior) < clearance - 1e-5:
                raise ValueError(f"Pieces {prior_id} and {idx} violate clearance")
        placed.append((idx, position))

    required = Counter({p["id"]: p["copies"] for p in manifest["pieces"]})
    if seen != required:
        return {
            "status": "NOT_FOUND",
            "required_pieces": sum(required.values()),
            "placed_pieces": sum(seen.values()),
            "fabric_width_in": width,
        }
    length = max(poly.bounds[3] for _, poly in placed)
    area = manifest["piece_area_sq_in"]
    return {
        "status": "FEASIBLE",
        "fabric_width_in": width,
        "fabric_length_consumed_in": length,
        "fabric_area_sq_in": width * length,
        "piece_area_sq_in": area,
        "utilization_pct": 100 * area / (width * length),
        "required_pieces": sum(required.values()),
        "placed_pieces": sum(seen.values()),
        "placements": [
            {
                "id": item["id"],
                "group_id": items_by_id[item["id"]]["group_id"],
                "x_in": item["x"],
                "y_in": item["y"],
                "rotation_deg": item.get("angle", 0),
            }
            for item in bins[0]["items"]
        ],
    }
