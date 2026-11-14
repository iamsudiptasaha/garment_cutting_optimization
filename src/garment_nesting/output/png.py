"""High-resolution continuous operator PNG and JPEG from one editable vector layout."""
from __future__ import annotations

from io import BytesIO
from math import isfinite
from pathlib import Path
from xml.etree import ElementTree as ET

# A long roll can be many inches. These explicit limits prevent an
# unbounded allocation and avoid silently shrinking the preview.
MAX_EDGE_PX = 60_000
MAX_PIXELS = 200_000_000
DEFAULT_WIDTH_PX = 5000


def _inches(raw: str | None) -> float:
    if raw is None or not raw.endswith("in"):
        raise ValueError("The rendered SVG must have inch-based physical dimensions")
    value = float(raw[:-2])
    if not isfinite(value) or value <= 0:
        raise ValueError("SVG size must be finite and positive")
    return value


def _dimensions(
    source: Path, preview_width_px: int, preview_ppi: float | None,
) -> tuple[int, int]:
    root = ET.parse(source).getroot()
    width_in = _inches(root.get("width"))
    height_in = _inches(root.get("height"))
    if preview_ppi is not None:
        if not isfinite(preview_ppi) or preview_ppi <= 0:
            raise ValueError("--preview-ppi must be finite and positive")
        preview_width_px = round(width_in * preview_ppi)
    if not 0 < preview_width_px <= MAX_EDGE_PX:
        raise ValueError(f"Preview width must be between 1 and {MAX_EDGE_PX} pixels")
    height_px = max(1, round(preview_width_px * height_in / width_in))
    if height_px > MAX_EDGE_PX or preview_width_px * height_px > MAX_PIXELS:
        raise ValueError(
            "Single-image preview exceeds the image size limit at "
            f"{preview_width_px} px wide ({height_px} px tall). "
            "Try --preview-width-px 2400 or view the continuously zoomable SVG. "
            "The exporter does not silently reduce image quality."
        )
    return preview_width_px, height_px


def _cairo():
    """Load native Cairo only during raster export, not before optimization."""
    try:
        import cairosvg
    except OSError as exc:
        raise RuntimeError(
            "Cairo system library not found. On macOS: brew install cairo; "
            'export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix cairo)/lib"; '
            "then use python -m garment_nesting.cli."
        ) from exc
    return cairosvg


def export_rasters(
    source_svg: str | Path,
    png_destination: str | Path,
    jpeg_destination: str | Path,
    *,
    preview_width_px: int = DEFAULT_WIDTH_PX,
    preview_ppi: float | None = None,
    jpeg_quality: int = 95,
) -> tuple[Path, Path]:
    """Export ONE long PNG and ONE long JPEG, preserving the full aspect ratio.

    PNG is lossless. JPEG uses quality 95 and 4:4:4 subsampling for clean text and fine lines.
    Neither is a 1:1 cutting master; use the editable SVG for geometry.
    """
    if not 1 <= jpeg_quality <= 95:
        raise ValueError("JPEG quality must be between 1 and 95")
    source = Path(source_svg)
    width_px, height_px = _dimensions(source, preview_width_px, preview_ppi)
    png = Path(png_destination)
    jpg = Path(jpeg_destination)
    png.parent.mkdir(parents=True, exist_ok=True)
    jpg.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    try:
        data = _cairo().svg2png(
            url=str(source),
            output_width=width_px,
            output_height=height_px,
            background_color="white",
        )
        png.write_bytes(data)
        with Image.open(BytesIO(data)) as rendered:
            rendered.convert("RGB").save(
                jpg, format="JPEG", quality=jpeg_quality, subsampling=0,
                optimize=True,
            )
    except Exception:
        png.unlink(missing_ok=True)
        jpg.unlink(missing_ok=True)
        raise
    return png, jpg


def export_png(
    source_svg: str | Path,
    destination: str | Path,
    *,
    preview_ppi: float = 72.0,
) -> Path:
    """Backward-compatible single-PNG helper with explicit pixel limits."""
    source = Path(source_svg)
    width_px, height_px = _dimensions(source, DEFAULT_WIDTH_PX, preview_ppi)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    _cairo().svg2png(
        url=str(source), write_to=str(target),
        output_width=width_px, output_height=height_px,
        background_color="white",
    )
    return target
