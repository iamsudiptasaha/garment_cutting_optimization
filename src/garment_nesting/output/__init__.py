"""Output boundary: continuous full-resolution operator views and editable cutting SVG."""
from __future__ import annotations

from pathlib import Path

from garment_nesting.output.png import DEFAULT_WIDTH_PX, export_rasters
from garment_nesting.output.svg import export_svg
from garment_nesting.output.viewer import export_viewer


def export_layouts(
    source_svg: str | Path,
    manifest: dict,
    report: dict,
    prefix: str | Path,
    *,
    preview_width_px: int = DEFAULT_WIDTH_PX,
    preview_ppi: float | None = None,
) -> tuple[Path, Path, Path, Path]:
    svg = export_svg(source_svg, manifest, report, f"{prefix}.nested.svg")
    viewer = export_viewer(svg, f"{prefix}.nested.html")
    png, jpg = export_rasters(
        svg, f"{prefix}.nested.png", f"{prefix}.nested.jpg",
        preview_width_px=preview_width_px, preview_ppi=preview_ppi,
    )
    return svg, png, jpg, viewer
