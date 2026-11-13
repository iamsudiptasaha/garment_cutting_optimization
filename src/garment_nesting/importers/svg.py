"""Backward-compatible imports. New code should use garment_nesting.input.svg."""
from garment_nesting.input.svg import SVG_NS, PatternRecord, SvgInventory, inspect_svg

__all__ = ["SVG_NS", "PatternRecord", "SvgInventory", "inspect_svg"]
