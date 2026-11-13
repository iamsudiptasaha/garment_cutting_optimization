"""Output boundary: editable cutting SVG and continuous PNG preview."""
from __future__ import annotations

from pathlib import Path

from garment_nesting.output.png import export_png
from garment_nesting.output.svg import export_svg


def export_layouts(
    source_svg: str | Path,
    manifest: dict,
    report: dict,
    prefix: str | Path,
    *,
    preview_ppi: float = 72.0,
) -> tuple[Path, Path]:
    svg = export_svg(source_svg, manifest, report, f"{prefix}.nested.svg")
    png = export_png(svg, f"{prefix}.nested.png", preview_ppi=preview_ppi)
    return svg, png
