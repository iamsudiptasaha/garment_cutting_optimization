"""Phase 1 SVG inventory; no curve approximation or geometric validation."""
from __future__ import annotations
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
LENGTH = re.compile(r"^\s*(" + NUM + r")\s*(mm|cm|in|px|pt)?\s*$")
COMMAND = re.compile(r"[MmZzLlHhVvCcSsQqTtAa]")

@dataclass(frozen=True)
class PatternRecord:
    group_id: str
    path_d: str
    labels: tuple[str, ...]
    path_count: int
    source_transform: str | None
    text_transforms: tuple[str | None, ...]
    closed_by_command: bool

@dataclass(frozen=True)
class SvgInventory:
    source: str
    width_mm: float | None
    height_mm: float | None
    view_box: tuple[float, float, float, float] | None
    patterns: tuple[PatternRecord, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)

def _millimetres(value: str | None) -> float | None:
    if value is None:
        return None
    match = LENGTH.fullmatch(value)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2) or "px"
    return number * {"mm": 1, "cm": 10, "in": 25.4, "px": 25.4 / 96, "pt": 25.4 / 72}[unit]

def inspect_svg(path: str | Path) -> SvgInventory:
    """Inventory grouped patterns. This does NOT validate geometry or collisions."""
    source = Path(path)
    root = ET.parse(source).getroot()
    if root.tag != f"{{{SVG_NS}}}svg":
        raise ValueError("Not an SVG document")
    vb_raw = root.get("viewBox")
    view_box = None
    if vb_raw:
        coords = vb_raw.replace(",", " ").split()
        if len(coords) != 4:
            raise ValueError("SVG viewBox must contain four numbers")
        view_box = tuple(float(x) for x in coords)
        if view_box[2] <= 0 or view_box[3] <= 0:
            raise ValueError("SVG viewBox dimensions must be positive")
    warnings: list[str] = []
    patterns: list[PatternRecord] = []
    ids: set[str] = set()
    for group in root.iter(f"{{{SVG_NS}}}g"):
        paths = group.findall(f"{{{SVG_NS}}}path")
        if not paths:
            continue
        group_id = group.get("id")
        if not group_id:
            warnings.append("Pattern group missing id")
            continue
        if group_id in ids:
            warnings.append(f"Duplicate pattern group id: {group_id}")
        ids.add(group_id)
        if len(paths) != 1:
            warnings.append(f"{group_id}: expected one direct child path, found {len(paths)}")
        path_d = paths[0].get("d") or ""
        if not path_d.strip():
            warnings.append(f"{group_id}: empty path")
        labels = []
        transforms = []
        for text in group.iter(f"{{{SVG_NS}}}text"):
            label = "".join(text.itertext()).strip()
            if label:
                labels.append(label)
                # Ancestor transforms remain in the original SVG, not resolved here.
                transforms.append(text.get("transform"))
        if not labels:
            warnings.append(f"{group_id}: missing text label")
        commands = COMMAND.findall(path_d)
        patterns.append(PatternRecord(
            group_id=group_id,
            path_d=path_d,
            labels=tuple(labels),
            path_count=len(paths),
            source_transform=group.get("transform"),
            text_transforms=tuple(transforms),
            closed_by_command=bool(commands and commands[-1] in "Zz"),
        ))
    if not patterns:
        warnings.append("No grouped pattern paths found")
    return SvgInventory(
        source=source.name,
        width_mm=_millimetres(root.get("width")),
        height_mm=_millimetres(root.get("height")),
        view_box=view_box,
        patterns=tuple(patterns),
        warnings=tuple(warnings),
    )
