"""Lightweight preview of independently validated solver polygons.

This is NOT a cutting master. Original SVG Béziers and text are retained in
the upload bytes for the later original-vector export stage.
"""
from __future__ import annotations

import base64
from xml.etree import ElementTree as ET

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

SVG = "http://www.w3.org/2000/svg"
COLORS = ("#64a4c7", "#6eb89e", "#ecc780", "#b9a3d2", "#e8a2a4", "#a6b1cb")
MAX_PREVIEW_PIECES = 1_500


def geometry_preview_uri(manifest: dict, report: dict) -> str:
    """Return an SVG data URI preserving the actual relative fabric geometry."""
    if report.get("status") != "FEASIBLE":
        raise ValueError("Preview requires a validated feasible solution")
    placements = report["placements"]
    if len(placements) > MAX_PREVIEW_PIECES:
        raise ValueError(
            f"Geometry preview limited to {MAX_PREVIEW_PIECES:,} instances; "
            "the checked result metrics remain available."
        )
    width = report["fabric_width_in"]
    length = report["fabric_length_consumed_in"]
    root = ET.Element(f"{{{SVG}}}svg", {
        "xmlns": SVG,
        "width": "100%", "viewBox": f"0 0 {width:.7g} {length:.7g}",
        "role": "img", "aria-label": "Validated nesting polygon approximation",
    })
    ET.SubElement(root, f"{{{SVG}}}rect", {
        "x": "0", "y": "0", "width": str(width), "height": str(length),
        "fill": "#f8fafc", "stroke": "#17394c", "stroke-width": "0.05",
    })
    fabric = manifest["fabric"]
    left = fabric["fabric_left_margin_in"]
    right = fabric["fabric_right_margin_in"]
    start = fabric["fabric_start_margin_in"]
    end = fabric["fabric_end_margin_in"]
    for x in (left, width - right):
        ET.SubElement(root, f"{{{SVG}}}line", {
            "x1": str(x), "x2": str(x), "y1": "0", "y2": str(length),
            "stroke": "#9aa7b3", "stroke-width": "0.025",
            "stroke-dasharray": "0.16,0.16",
        })
    for y in (start, length - end):
        ET.SubElement(root, f"{{{SVG}}}line", {
            "x1": "0", "x2": str(width), "y1": str(y), "y2": str(y),
            "stroke": "#9aa7b3", "stroke-width": "0.025",
            "stroke-dasharray": "0.16,0.16",
        })
    pieces = {piece["id"]: piece for piece in manifest["pieces"]}
    for entry in placements:
        item = pieces[entry["id"]]
        poly = Polygon([(v["x"], v["y"]) for v in item["vertices"]])
        poly = translate(
            rotate(poly, entry["rotation_deg"], origin=(0, 0)),
            xoff=entry["x_in"], yoff=entry["y_in"],
        )
        points = " ".join(f"{x:.5f},{y:.5f}" for x, y in list(poly.exterior.coords)[:-1])
        ET.SubElement(root, f"{{{SVG}}}polygon", {
            "points": points,
            "fill": COLORS[entry["id"] % len(COLORS)],
            "fill-opacity": "0.72",
            "stroke": "#254658", "stroke-width": "0.025",
        })
        if poly.area >= 1:
            center = poly.representative_point()
            text = ET.SubElement(root, f"{{{SVG}}}text", {
                "x": f"{center.x:.5f}", "y": f"{center.y:.5f}",
                "text-anchor": "middle", "font-size": "0.21",
                "fill": "#143548", "font-family": "sans-serif",
            })
            text.text = f"{entry['group_id']} #{entry['copy']}"
    svg_data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return "data:image/svg+xml;base64," + base64.b64encode(svg_data).decode("ascii")
