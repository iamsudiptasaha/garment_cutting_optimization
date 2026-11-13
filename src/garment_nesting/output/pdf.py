"""Produce a vector PDF at true inch scale, splitting long rolls into pages."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from math import ceil, isfinite
from pathlib import Path
from xml.etree import ElementTree as ET

import cairosvg
from pypdf import PdfReader, PdfWriter


def _inches(value: str | None) -> float:
    if value is None or not value.endswith("in"):
        raise ValueError("Exported SVG dimensions must be in inches")
    inches = float(value[:-2])
    if not isfinite(inches) or inches <= 0:
        raise ValueError("Exported SVG dimensions must be finite and positive")
    return inches


def export_pdf(
    source_svg: str | Path,
    destination: str | Path,
    *,
    max_page_length_in: float = 72.0,
) -> Path:
    """Render editable SVG curves to PDF without rasterizing the cutting paths.

    A continuous SVG roll can exceed supported PDF page sizes. Split it into
    consecutive pages up to max_page_length_in, preserving 1:1 physical scale.
    """
    if not isfinite(max_page_length_in) or not 0 < max_page_length_in <= 72:
        raise ValueError("PDF page length must be between 0 and 72 inches")
    source = Path(source_svg)
    root = ET.parse(source).getroot()
    width = _inches(root.get("width"))
    length = _inches(root.get("height"))
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if length <= max_page_length_in:
        cairosvg.svg2pdf(url=str(source), write_to=str(dest))
        return dest

    writer = PdfWriter()
    for page in range(ceil(length / max_page_length_in)):
        start = page * max_page_length_in
        segment = min(max_page_length_in, length - start)
        page_svg = deepcopy(root)
        page_svg.set("width", f"{width:.10f}in")
        page_svg.set("height", f"{segment:.10f}in")
        page_svg.set("viewBox", f"0 {start:.10f} {width:.10f} {segment:.10f}")
        page_svg.set("overflow", "hidden")
        vector_pdf = cairosvg.svg2pdf(bytestring=ET.tostring(page_svg, encoding="utf-8"))
        writer.add_page(PdfReader(BytesIO(vector_pdf)).pages[0])
    with dest.open("wb") as handle:
        writer.write(handle)
    return dest
