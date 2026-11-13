"""Export validated placements as a physically scaled, editable SVG.

The exporter moves original SVG groups: it never replaces Bézier outlines
with the simplified polygons used by the solver.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from math import isclose
from pathlib import Path
from xml.etree import ElementTree as ET

from garment_nesting.input.svg import SVG_NS, inspect_svg
from garment_nesting.processor.packing import validate_certificate

SVG = f"{{{SVG_NS}}}"
MM_PER_INCH = 25.4
# Annotation margins are outside the physically measured fabric rectangle.
LEFT, RIGHT, HEADER, FOOTER = 0.45, 1.35, 1.2, 0.35


def _n(value: float) -> str:
    return f"{float(value):.10f}".rstrip("0").rstrip(".") or "0"



def _add_text(parent: ET.Element, x: float, y: float, value: str, size: float) -> None:
    element = ET.SubElement(parent, SVG + "text", {
        "x": _n(x), "y": _n(y),
        "font-family": "Arial, Helvetica, sans-serif",
        "font-size": _n(size), "font-weight": "bold", "fill": "#10202b",
    })
    element.text = value


def _draw_fabric_guide(root: ET.Element, width: float, length: float, report: dict) -> None:
    """Draw a measured boundary and dimension guides outside the cutting layer."""
    guide = ET.SubElement(root, SVG + "g", {
        "id": "fabric-guide", "data-role": "reference-not-cutting",
    })
    ET.SubElement(guide, SVG + "rect", {
        "id": "fabric-boundary", "x": _n(LEFT), "y": _n(HEADER),
        "width": _n(width), "height": _n(length),
        "fill": "none", "stroke": "#096B84", "stroke-width": "0.035",
    })
    _add_text(guide, LEFT, 0.31, "FABRIC CUTTING LAYOUT", 0.27)
    _add_text(
        guide, LEFT, 0.65, f"WIDTH: {width:.2f} in    LENGTH: {length:.2f} in", 0.22,
    )
    _add_text(
        guide, LEFT, 0.95,
        f"WASTAGE: {report['wastage_pct']:.2f}%    "
        f"UTILIZATION: {report['utilization_pct']:.2f}%    "
        f"PIECES: {report['placed_pieces']}/{report['required_pieces']}",
        0.19,
    )
    # The bracket measures the actual fabric width, excluding page margins.
    y = HEADER - 0.08
    ET.SubElement(guide, SVG + "line", {
        "x1": _n(LEFT), "y1": _n(y), "x2": _n(LEFT + width),
        "y2": _n(y), "stroke": "#096B84", "stroke-width": "0.018",
    })
    for x in (LEFT, LEFT + width):
        ET.SubElement(guide, SVG + "line", {
            "x1": _n(x), "y1": _n(y - 0.075), "x2": _n(x),
            "y2": _n(y + 0.075), "stroke": "#096B84", "stroke-width": "0.023",
        })
    dx = LEFT + width + 0.42
    ET.SubElement(guide, SVG + "line", {
        "x1": _n(dx), "y1": _n(HEADER),
        "x2": _n(dx), "y2": _n(HEADER + length),
        "stroke": "#096B84", "stroke-width": "0.018",
    })
    for y in (HEADER, HEADER + length):
        ET.SubElement(guide, SVG + "line", {
            "x1": _n(dx - 0.085), "y1": _n(y),
            "x2": _n(dx + 0.085), "y2": _n(y),
            "stroke": "#096B84", "stroke-width": "0.023",
        })
    if length >= 2.0:
        center_y = HEADER + length / 2
        note = ET.SubElement(guide, SVG + "text", {
            "x": _n(dx + 0.14), "y": _n(center_y),
            "font-family": "Arial, Helvetica, sans-serif",
            "font-size": "0.20", "font-weight": "bold", "fill": "#096B84",
            "text-anchor": "middle",
            "transform": f"rotate(90 {_n(dx + 0.14)} {_n(center_y)})",
        })
        note.text = f"LENGTH {length:.2f} in"


def export_svg(source_svg: str | Path, manifest: dict, report: dict, destination: str | Path) -> Path:
    """Write the original cutting groups at validated positions (all units inches)."""
    source = Path(source_svg)
    output = Path(destination)
    if report.get("status") != "FEASIBLE":
        raise ValueError("Only a complete FEASIBLE nesting result can be exported")
    if manifest.get("units") != "in":
        raise ValueError("Manifest measurements must be in inches")
    expected_sha = manifest.get("source_sha256")
    if not expected_sha:
        raise ValueError("Manifest lacks source fingerprint; regenerate with 'prepare' or 'nest'")
    if sha256(source.read_bytes()).hexdigest() != expected_sha:
        raise ValueError("Source SVG differs from the SVG used to prepare the placements")

    placements = report.get("placements", [])
    certificate = {"bins": [{"id": 0, "copies": 1, "items": [
        {
            "id": item["id"], "x": item["x_in"], "y": item["y_in"],
            "angle": item["rotation_deg"], "mirror": False,
        }
        for item in placements
    ]}]}
    checked = validate_certificate(manifest, certificate)
    if checked["status"] != "FEASIBLE":
        raise ValueError("Cannot export incomplete nesting")
    if not isclose(
        checked["fabric_length_consumed_in"], report["fabric_length_consumed_in"],
        rel_tol=0, abs_tol=1e-5,
    ):
        raise ValueError("Reported fabric length disagrees with placed geometry")
    width = checked["fabric_width_in"]
    length = checked["fabric_length_consumed_in"]

    inventory = inspect_svg(source)
    if inventory.view_box is None or inventory.width_mm is None or inventory.height_mm is None:
        raise ValueError("Source SVG must include physical dimensions and viewBox")
    vx, vy, vw, vh = inventory.view_box
    scale_x = inventory.width_mm / vw / MM_PER_INCH
    scale_y = inventory.height_mm / vh / MM_PER_INCH
    if not isclose(scale_x, scale_y, rel_tol=1e-5):
        raise ValueError("Nonuniform source SVG scale is unsupported")

    original_root = ET.parse(source).getroot()
    groups = {
        group.get("id"): group
        for group in original_root.iter(SVG + "g")
        if group.find(SVG + "path") is not None
    }
    items = {item["id"]: item for item in manifest["pieces"]}
    ids = {item["group_id"] for item in manifest["pieces"]}
    if (
        len(items) != manifest["required_pieces"]
        or len(groups) != len(ids)
        or set(groups) != ids
    ):
        raise ValueError("Source groups and manifest do not match exactly")

    # The solver can leave unused blank fabric ahead of the first piece.
    # Move every group together so the exported roll begins at its first edge.
    first_y = min(
        item["y_in"] + min(
            vertex["y"] if item["rotation_deg"] == 0 else -vertex["y"]
            for vertex in items[item["id"]]["vertices"]
        )
        for item in placements
    )

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    ET.register_namespace("xodm", "http://www.corel.com/coreldraw/odm/2003")
    root_attributes = {
        key: value for key, value in original_root.attrib.items()
        if key not in ("width", "height", "viewBox")
    }
    root = ET.Element(SVG + "svg", root_attributes)
    # The canvas includes annotation margins; its measured rectangle is W x L.
    page_width = width + LEFT + RIGHT
    page_height = length + HEADER + FOOTER
    root.set("width", f"{_n(page_width)}in")
    root.set("height", f"{_n(page_height)}in")
    root.set("viewBox", f"0 0 {_n(page_width)} {_n(page_height)}")
    root.set("data-fabric-width-in", _n(width))
    root.set("data-fabric-length-in", _n(length))
    root.set("data-fabric-origin-x-in", _n(LEFT))
    root.set("data-fabric-origin-y-in", _n(HEADER))
    root.set("data-grain-direction", "y")
    root.set("data-measurement-unit", "in")
    for child in original_root:
        if child.tag == SVG + "defs":
            root.append(deepcopy(child))

    _draw_fabric_guide(root, width, length, checked)
    layer = ET.SubElement(root, SVG + "g", {"id": "nested-cutting-pieces"})
    for placement in placements:
        item = items[placement["id"]]
        group_id = item["group_id"]
        if placement["group_id"] != group_id:
            raise ValueError(f"Wrong original group for item {placement['id']}")
        if "source_origin_in" not in item:
            raise ValueError("Missing source origin; regenerate the manifest")
        min_x, min_y = item["source_origin_in"]
        angle = placement["rotation_deg"]
        x = placement["x_in"] + LEFT
        y = placement["y_in"] - first_y + HEADER

        # Rightmost transform executes first. Source Bézier points are mapped
        # into inches, translated to the local solver origin, then positioned.
        transform = (
            f"translate({_n(x)} {_n(y)}) rotate({_n(angle)}) "
            f"translate({_n(-min_x)} {_n(-min_y)}) "
            f"scale({_n(scale_x)} {_n(scale_y)}) "
            f"translate({_n(-vx)} {_n(-vy)})"
        )
        moved_group = deepcopy(groups[group_id])
        if moved_group.get("transform"):
            raise ValueError(f"Unexpected transformed source group: {group_id}")
        moved_group.set("transform", transform)
        moved_group.set("data-solver-id", str(placement["id"]))
        layer.append(moved_group)

    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
    return output
