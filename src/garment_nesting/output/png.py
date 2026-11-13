"""Render one continuous, shareable PNG from the editable nested SVG."""
from __future__ import annotations

from math import isfinite, sqrt
from pathlib import Path
from xml.etree import ElementTree as ET

import cairosvg

# A very long roll may be thousands of inches. Keep a single image, but
# enforce reasonable raster limits to avoid exhausting operators' devices.
MAX_EDGE_PX = 24_000
MAX_PIXELS = 40_000_000
MIN_READABLE_PPI = 18.0


def _inches(raw: str | None) -> float:
    if raw is None or not raw.endswith("in"):
        raise ValueError("The rendered SVG must have inch-based physical dimensions")
    value = float(raw[:-2])
    if not isfinite(value) or value <= 0:
        raise ValueError("SVG size must be finite and positive")
    return value


def export_png(
    source_svg: str | Path,
    destination: str | Path,
    *,
    preview_ppi: float = 72.0,
) -> Path:
    """Single continuous preview. SVG remains the exact-size cutting master.

    The PNG is for phone/WhatsApp viewing, NOT a 1:1 printout. Resolution is
    automatically limited for long layouts. If that would make labels too
    small, fail explicitly instead of delivering an unreadable image.
    """
    if not isfinite(preview_ppi) or preview_ppi <= 0:
        raise ValueError("Preview pixels per inch must be finite and positive")
    source = Path(source_svg)
    root = ET.parse(source).getroot()
    width_in = _inches(root.get("width"))
    length_in = _inches(root.get("height"))
    effective_ppi = min(
        preview_ppi,
        MAX_EDGE_PX / max(width_in, length_in),
        sqrt(MAX_PIXELS / (width_in * length_in)),
    )
    if effective_ppi < MIN_READABLE_PPI:
        raise ValueError(
            f"Single-image preview would be below {MIN_READABLE_PPI:g} pixels/inch. "
            "Use the editable SVG for this very long layout; do not reduce it "
            "into an unreadable PNG."
        )
    width_px = max(1, round(width_in * effective_ppi))
    length_px = max(1, round(length_in * effective_ppi))
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        url=str(source),
        write_to=str(target),
        output_width=width_px,
        output_height=length_px,
        background_color="white",
    )
    return target
