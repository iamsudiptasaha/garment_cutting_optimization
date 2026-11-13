"""Phase 1 inventory tests; not geometric correctness tests."""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from garment_nesting.importers.svg import inspect_svg

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "FC_HH_Full_Pyjama.svg"

def test_reference_fixture_inventory():
    audit = inspect_svg(SAMPLE)
    assert len(audit.patterns) == 44
    assert all(len(p.labels) == 1 for p in audit.patterns)
    assert all(p.path_count == 1 and p.closed_by_command for p in audit.patterns)
    assert len({p.group_id for p in audit.patterns}) == 44
    assert audit.width_mm == pytest.approx(5609.89)
    assert audit.height_mm == pytest.approx(2450.88)
    assert audit.warnings == ()

def test_missing_label_is_reported(tmp_path):
    svg = tmp_path / "bad.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><g id="piece"><path d="M0 0 L1 0 Z"/></g></svg>')
    result = inspect_svg(svg)
    assert len(result.patterns) == 1
    assert any("missing text label" in warning for warning in result.warnings)

def test_invalid_viewbox_is_rejected(tmp_path):
    svg = tmp_path / "bad.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 1"/>')
    with pytest.raises(ValueError, match="positive"):
        inspect_svg(svg)

def test_svg_root_is_required(tmp_path):
    path = tmp_path / "not_svg.xml"
    ET.ElementTree(ET.Element("root")).write(path)
    with pytest.raises(ValueError, match="Not an SVG"):
        inspect_svg(path)
