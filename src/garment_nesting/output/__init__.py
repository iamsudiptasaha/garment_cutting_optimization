"""Output boundary: write cutting layout and vector PDF from validated placements."""
from __future__ import annotations

from pathlib import Path

from garment_nesting.output.pdf import export_pdf
from garment_nesting.output.svg import export_svg


def export_layouts(source_svg: str | Path, manifest: dict, report: dict, prefix: str | Path) -> tuple[Path, Path]:
    svg = export_svg(source_svg, manifest, report, f"{prefix}.nested.svg")
    pdf = export_pdf(svg, f"{prefix}.nested.pdf")
    return svg, pdf
