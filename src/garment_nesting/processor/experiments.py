"""Run independently checked fixed-width nesting experiments for GUI job inputs.

The shelf baseline is deterministic and always available. The native
PackingSolver adapter is optional, and uses conservative *uniform* clearance
for per-pattern keep-out margins. No solver result is accepted on trust.
"""
from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from garment_nesting.job_config import validate_fabric_settings
from garment_nesting.processor.packing import prepare_instance
from garment_nesting.processor.run import solve_instance

MAX_RUN_PIECES = 10_000
EPS = 0.00001


class NativeSolverUnavailable(RuntimeError):
    """Native solver module is not installed or supported in this interpreter."""


def _polygon(item: dict) -> Polygon:
    return Polygon([(vertex["x"], vertex["y"]) for vertex in item["vertices"]])


def _selected_source_svg(data: bytes, selected_groups: set[str]) -> bytes:
    """Keep only selected cutting groups in a temporary solver SVG copy.

    Excluded oversized/invalid groups must not prevent a valid selection
    from running. Original uploaded SVG bytes remain unchanged.
    """
    from garment_nesting.input.svg import SVG_NS

    root = ET.fromstring(data)
    group_tag = f"{{{SVG_NS}}}g"
    path_tag = f"{{{SVG_NS}}}path"
    for parent in root.iter():
        for child in list(parent):
            if (
                child.tag == group_tag and child.find(path_tag) is not None
                and child.get("id") not in selected_groups
            ):
                parent.remove(child)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def prepare_job(sources: dict[str, dict], job: dict) -> tuple[dict, dict]:
    """Convert checked upload snapshots and GUI selection into one solver instance.

    Sources are {upload_id: {filename: str, content: bytes}}. No upload bytes
    are written outside a TemporaryDirectory. Unselected pieces do not enter
    the solver instance. All copies share one item type, preserving item IDs.
    """
    if job.get("units") != "in":
        raise ValueError("Nesting job units must be inches")
    fabric = validate_fabric_settings(job["fabric"])
    specs = job.get("patterns", [])
    if not specs:
        raise ValueError("Select at least one valid pattern with positive copies")
    if sum(x["copies"] for x in specs) > MAX_RUN_PIECES:
        raise ValueError(
            f"This experiment runner supports up to {MAX_RUN_PIECES:,} total pieces; "
            "reduce copies or split the job. No copies were silently discarded."
        )
    width = fabric["fabric_width_in"] - (
        fabric["fabric_left_margin_in"] + fabric["fabric_right_margin_in"]
    )
    max_length = fabric["max_length_in"]
    usable_max_length = (
        None if max_length is None else
        max_length - fabric["fabric_start_margin_in"] - fabric["fabric_end_margin_in"]
    )
    selected_by_source: dict[str, set[str]] = {}
    for selected in specs:
        selected_by_source.setdefault(selected["source_id"], set()).add(
            selected["group_id"],
        )
    by_source = {}
    shapes = []
    pieces = []
    total_area = 0.0
    height_bound = 0.0
    total_copies = 0
    max_piece_margin = 0.0
    with TemporaryDirectory(prefix="nesting-experiment-") as directory:
        for spec in specs:
            source_id = spec["source_id"]
            original = sources.get(source_id)
            if original is None:
                raise ValueError(f"Uploaded SVG is unavailable for source {source_id}")
            if original["filename"] != spec["source_file"]:
                raise ValueError("Uploaded SVG filename does not match job selection")
            if source_id not in by_source:
                path = Path(directory) / f"{len(by_source)}.svg"
                path.write_bytes(_selected_source_svg(
                    original["content"], selected_by_source[source_id],
                ))
                source_instance, source_manifest = prepare_instance(
                    path, fabric_width_in=width, clearance_in=0,
                )
                by_source[source_id] = {
                    "shapes": source_instance["item_types"],
                    "pieces": {
                        item["group_id"]: (item, source_instance["item_types"][item["id"]])
                        for item in source_manifest["pieces"]
                    },
                    "sha256": sha256(original["content"]).hexdigest(),
                }

            catalogue = by_source[source_id]["pieces"]
            if spec["group_id"] not in catalogue:
                raise ValueError(f"Unknown SVG group {spec['group_id']}")
            if spec["copies"] <= 0:
                raise ValueError("Job selection must not include zero copies")
            angles = spec["allowed_rotations_deg"]
            if not angles or not set(angles).issubset({0, 180}):
                raise ValueError("Only 0° and 180° rotations are supported")
            margin = spec["piece_margin_in"]
            if not isfinite(margin) or margin < 0:
                raise ValueError("Extra piece margin must be finite and nonnegative")
            original_piece, original_shape = catalogue[spec["group_id"]]
            item_id = len(pieces)
            polygon = _polygon(original_piece)
            bounds = polygon.bounds
            piece_w, piece_h = bounds[2] - bounds[0], bounds[3] - bounds[1]
            if piece_w > width + EPS:
                raise ValueError(
                    f"PROVEN_INFEASIBLE: {spec['group_id']} needs {piece_w:.3f} in "
                    f"width; available width is {width:.3f} in"
                )
            if usable_max_length is not None and piece_h > usable_max_length + EPS:
                raise ValueError(
                    f"PROVEN_INFEASIBLE: {spec['group_id']} exceeds usable length "
                    f"{usable_max_length:.3f} in"
                )
            copies = spec["copies"]
            shapes.append({
                "type": "polygon",
                "vertices": original_shape["vertices"],
                "copies": copies,
                "allowed_rotations": [
                    {"start": angle, "end": angle, "mirror": False}
                    for angle in angles
                ],
            })
            pieces.append({
                "id": item_id,
                "source_id": source_id,
                "source_file": original["filename"],
                "source_sha256": by_source[source_id]["sha256"],
                "group_id": spec["group_id"],
                "label": original_piece["label"],
                "vertices": original_piece["vertices"],
                "area_sq_in": original_piece["area_sq_in"],
                "copies": copies,
                "allowed_rotations_deg": list(angles),
                "piece_margin_in": margin,
            })
            total_copies += copies
            total_area += original_piece["area_sq_in"] * copies
            max_piece_margin = max(max_piece_margin, margin)
            height_bound += (piece_h + 2 * margin + fabric["piece_clearance_in"]) * copies

    if max_length is not None and total_area > width * usable_max_length + EPS:
        raise ValueError(
            "PROVEN_INFEASIBLE: combined piece area exceeds usable fabric "
            "width × maximum usable length"
        )
    # Conservative bound: all items can fit vertically in independent shelves
    # if they can individually fit. If the user imposes a maximum, it is hard.
    strip_height = (
        usable_max_length if usable_max_length is not None
        else height_bound + fabric["piece_clearance_in"] + 0.01
    )
    global_spacing = fabric["piece_clearance_in"] + 2 * max_piece_margin
    instance = {
        "objective": "open-dimension-y",
        "parameters": {"item_item_minimum_spacing": global_spacing},
        "bin_types": [{
            "type": "rectangle",
            "width": width, "height": strip_height, "copies": 1,
        }],
        "item_types": shapes,
    }
    manifest = {
        "units": "in",
        "fabric": fabric,
        "usable_width_in": width,
        "strip_height_in": strip_height,
        "native_global_spacing_in": global_spacing,
        "required_pieces": total_copies,
        "piece_area_sq_in": total_area,
        "pieces": pieces,
    }
    return instance, manifest


def shelf_certificate(manifest: dict) -> dict:
    """Place axis-aligned keep-out boxes by decreasing height; no curved collisions.

    Rectangular keep-outs are deliberately more conservative than polygon
    nesting but guarantee global gap + both piece-specific extra margins.
    """
    fabric = manifest["fabric"]
    gap = fabric["piece_clearance_in"]
    width = manifest["usable_width_in"]
    entries = []
    for item in manifest["pieces"]:
        shape = _polygon(item)
        angles = item["allowed_rotations_deg"]
        angle = 0 if 0 in angles else 180
        rotated = rotate(shape, angle, origin=(0, 0))
        min_x, min_y, max_x, max_y = rotated.bounds
        margin = item["piece_margin_in"] + gap / 2
        padded_w = max_x - min_x + 2 * margin
        padded_h = max_y - min_y + 2 * margin
        if padded_w > width + EPS:
            return {"bins": []}  # conservative shelf can't prove true infeasibility
        for copy in range(item["copies"]):
            entries.append((
                -padded_h, -padded_w, item["id"], copy, angle,
                padded_w, padded_h, min_x, min_y, margin,
            ))
    entries.sort()
    current_x = 0.0
    current_y = 0.0
    shelf_height = 0.0
    placements = []
    for entry in entries:
        _, _, item_id, _, angle, padded_w, padded_h, min_x, min_y, margin = entry
        if current_x + padded_w > width + EPS:
            current_y += shelf_height
            current_x = 0.0
            shelf_height = 0.0
        if current_y + padded_h > manifest["strip_height_in"] + EPS:
            return {"bins": []}
        placements.append({
            "id": item_id, "angle": angle, "mirror": False,
            "x": current_x + margin - min_x,
            "y": current_y + margin - min_y,
        })
        current_x += padded_w
        shelf_height = max(shelf_height, padded_h)
    return {"bins": [{"id": 0, "copies": 1, "items": placements}]}


def validate_job_certificate(manifest: dict, certificate: dict) -> dict:
    """Independently check every required piece, bounds, rotation and pair gap.

    Uses actual solver polygon geometry, not conservative shelf keep-outs.
    An incomplete result is NOT_FOUND, never a claimed feasible layout.
    """
    pieces = {item["id"]: item for item in manifest["pieces"]}
    required = Counter({item["id"]: item["copies"] for item in manifest["pieces"]})
    bins = certificate.get("bins", [])
    if not bins:
        return {
            "status": "NOT_FOUND", "required_pieces": manifest["required_pieces"],
            "placed_pieces": 0,
        }
    if len(bins) != 1 or bins[0].get("id") != 0 or bins[0].get("copies", 1) != 1:
        raise ValueError("Certificate must contain exactly one usable fabric strip")
    seen = Counter()
    polygons = []
    placements = []
    for placement in bins[0].get("items", []):
        item_id = placement.get("id")
        if item_id not in pieces:
            raise ValueError(f"Unknown item type {item_id} in certificate")
        item = pieces[item_id]
        seen[item_id] += 1
        if seen[item_id] > item["copies"]:
            raise ValueError(f"Too many copies of {item['group_id']}")
        angle = placement.get("angle", 0)
        if angle not in item["allowed_rotations_deg"]:
            raise ValueError(f"Disallowed rotation for {item['group_id']}: {angle}")
        if placement.get("mirror", False):
            raise ValueError(f"Mirroring is prohibited for {item['group_id']}")
        x, y = placement.get("x"), placement.get("y")
        if (
            isinstance(x, bool) or isinstance(y, bool)
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
            or not isfinite(x) or not isfinite(y)
        ):
            raise ValueError("Nonfinite or invalid certificate coordinates")
        polygon = translate(rotate(_polygon(item), angle, origin=(0, 0)), xoff=x, yoff=y)
        x0, y0, x1, y1 = polygon.bounds
        if (
            x0 < -EPS or y0 < -EPS
            or x1 > manifest["usable_width_in"] + EPS
            or y1 > manifest["strip_height_in"] + EPS
        ):
            raise ValueError(f"Pattern {item['group_id']} exceeds usable fabric bounds")
        polygons.append(polygon)
        placements.append({
            "id": item_id,
            "source_id": item["source_id"],
            "source_file": item["source_file"],
            "group_id": item["group_id"],
            "copy": seen[item_id],
            "rotation_deg": angle,
            "x_local_in": x, "y_local_in": y,
        })
    if seen != required:
        return {
            "status": "NOT_FOUND",
            "required_pieces": sum(required.values()),
            "placed_pieces": sum(seen.values()),
        }

    if len(polygons) > 1:
        spatial = STRtree(polygons)
        max_margin = max(item["piece_margin_in"] for item in pieces.values())
        gap = manifest["fabric"]["piece_clearance_in"]
        for i, polygon in enumerate(polygons):
            item_a = pieces[placements[i]["id"]]
            reach = gap + item_a["piece_margin_in"] + max_margin
            for j in spatial.query(polygon.buffer(reach + EPS)):
                j = int(j)
                if j <= i:
                    continue
                other = polygons[j]
                item_b = pieces[placements[j]["id"]]
                if polygon.intersection(other).area > 1e-7:
                    raise ValueError(f"Overlapping pieces: {i} and {j}")
                required_gap = gap + item_a["piece_margin_in"] + item_b["piece_margin_in"]
                if polygon.distance(other) + EPS < required_gap:
                    raise ValueError(f"Insufficient piece gap between {i} and {j}")

    y_min = min(p.bounds[1] for p in polygons)
    y_max = max(p.bounds[3] for p in polygons)
    fabric = manifest["fabric"]
    length = y_max - y_min + fabric["fabric_start_margin_in"] + fabric["fabric_end_margin_in"]
    max_length = fabric["max_length_in"]
    if max_length is not None and length > max_length + EPS:
        return {
            "status": "NOT_FOUND",
            "required_pieces": sum(required.values()),
            "placed_pieces": sum(seen.values()),
            "message": "Candidate exceeds maximum fabric length",
        }
    # Export/report transforms refer to the full physical fabric width.
    for placed in placements:
        placed["x_in"] = placed["x_local_in"] + fabric["fabric_left_margin_in"]
        placed["y_in"] = (
            placed["y_local_in"] - y_min + fabric["fabric_start_margin_in"]
        )
    fabric_area = fabric["fabric_width_in"] * length
    piece_area = manifest["piece_area_sq_in"]
    return {
        "status": "FEASIBLE",
        "fabric_width_in": fabric["fabric_width_in"],
        "usable_width_in": manifest["usable_width_in"],
        "fabric_length_consumed_in": length,
        "fabric_area_sq_in": fabric_area,
        "piece_area_sq_in": piece_area,
        "wastage_pct": 100 * (fabric_area - piece_area) / fabric_area,
        "utilization_pct": 100 * piece_area / fabric_area,
        "required_pieces": sum(required.values()),
        "placed_pieces": len(placements),
        "placements": placements,
    }


def _native_certificate(instance: dict, time_limit: int) -> dict:
    """Read the native solution from a temporary certificate, never trust it."""
    try:
        import packingsolver.irregular  # noqa: F401
    except ImportError as exc:
        raise NativeSolverUnavailable(
            "Native PackingSolver unavailable in this Python environment. "
            "The shelf baseline works without it; use a compatible Python "
            "interpreter with pip install -e '.[solver]'."
        ) from exc
    with TemporaryDirectory(prefix="nesting-native-") as directory:
        source = Path(directory) / "instance.json"
        certificate = Path(directory) / "certificate.json"
        source.write_text(json.dumps(instance), encoding="utf-8")
        solve_instance(source, certificate, time_limit)
        if not certificate.exists():
            return {"bins": []}
        return json.loads(certificate.read_text(encoding="utf-8"))


def _shelf_adapter(_instance: dict, manifest: dict) -> dict:
    return shelf_certificate(manifest)


def _native_adapter(instance: dict, manifest: dict) -> dict:
    return _native_certificate(instance, manifest["fabric"]["time_limit_seconds"])


# Plug-in contract: (display label, prepare-once processor callable).
# New processors can be added here without changing the runner or GUI.
PROCESSOR_REGISTRY = {
    "shelf": ("Deterministic shelf (baseline)", _shelf_adapter),
    "native": ("PackingSolver (native optimizer)", _native_adapter),
}
ALGORITHMS = {key: item[0] for key, item in PROCESSOR_REGISTRY.items()}


def run_experiments(
    sources: dict[str, dict], job: dict, algorithms: list[str],
) -> dict:
    """Prepare once, compare selected plugins, accept only validated layouts."""
    if not algorithms:
        raise ValueError("Choose at least one solving algorithm")
    if any(name not in ALGORITHMS for name in algorithms):
        raise ValueError("Unknown solver algorithm")
    instance, manifest = prepare_job(sources, job)
    candidates = []
    for name in dict.fromkeys(algorithms):
        try:
            certificate = PROCESSOR_REGISTRY[name][1](instance, manifest)
            report = validate_job_certificate(manifest, certificate)
            candidates.append({
                "algorithm": name,
                "name": ALGORITHMS[name],
                "status": report["status"],
                "report": report,
                "message": report.get("message", ""),
            })
        except NativeSolverUnavailable as exc:
            candidates.append({
                "algorithm": name, "name": ALGORITHMS[name],
                "status": "UNAVAILABLE", "message": str(exc),
            })
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
            candidates.append({
                "algorithm": name, "name": ALGORITHMS[name],
                "status": "ERROR", "message": f"{type(exc).__name__}: {exc}",
            })
    candidates.sort(key=lambda c: (
        c["status"] != "FEASIBLE",
        c.get("report", {}).get("fabric_length_consumed_in", float("inf")),
    ))
    return {
        "manifest": manifest,
        "candidates": candidates,
        "best_algorithm": next(
            (c["algorithm"] for c in candidates if c["status"] == "FEASIBLE"),
            None,
        ),
    }
