"""Stable input/processor/output boundaries and true-size SVG/PDF export."""
from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from pypdf import PdfReader

from garment_nesting.cli import main
from garment_nesting.input.svg import SVG_NS, inspect_svg
from garment_nesting.output.pdf import export_pdf
from garment_nesting.output.svg import export_svg
from garment_nesting.processor.packing import prepare_instance, validate_certificate

SVG = f"{{{SVG_NS}}}"
SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "FC_HH_Full_Pyjama.svg"


@pytest.fixture
def simple_layout(tmp_path):
    original = tmp_path / "input.svg"
    original.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="100in" height="100in" viewBox="0 0 100 100">'
        '<defs><style>.outline{fill:none;stroke:#222;stroke-width:0.03}</style></defs>'
        '<g id="a"><path class="outline" d="M10 10 L12 10 L12 12 L10 12 Z"/>'
        '<g transform="translate(1 0)"><text x="10" y="11">FRONT</text></g></g>'
        '<g id="b"><path class="outline" d="M40 40 L42 40 L42 42 L40 42 Z"/>'
        '<g transform="translate(1 0)"><text x="40" y="41">BACK</text></g></g>'
        '<line id="fabric-grainline" x1="90" y1="10" x2="90" y2="80"/>'
        '</svg>',
        encoding="utf-8",
    )
    _, manifest = prepare_instance(original, fabric_width_in=6)
    certificate = {"bins": [{"id": 0, "items": [
        {"id": 0, "x": 0, "y": 0, "angle": 0},
        {"id": 1, "x": 4.1, "y": 2, "angle": 180},
    ]}]}
    report = validate_certificate(manifest, certificate)
    assert report["status"] == "FEASIBLE"
    return original, manifest, report


def test_export_preserves_editable_curves_and_labels(simple_layout, tmp_path):
    original, manifest, report = simple_layout
    out = export_svg(original, manifest, report, tmp_path / "output" / "nested.svg")
    root = ET.parse(out).getroot()
    source = ET.parse(original).getroot()
    assert root.get("width") == "6in"
    assert root.get("height") == "2in"
    assert root.get("viewBox") == "0 0 6 2"
    assert root.get("data-grain-direction") == "y"
    before = {g.get("id"): g for g in source.iter(SVG + "g") if g.find(SVG + "path") is not None}
    after = {g.get("id"): g for g in root.iter(SVG + "g") if g.find(SVG + "path") is not None}
    assert set(after) == set(before) == {"a", "b"}
    for key in before:
        assert after[key].find(SVG + "path").get("d") == before[key].find(SVG + "path").get("d")
        assert list(after[key].iter(SVG + "text"))[0].text == (
            list(before[key].iter(SVG + "text"))[0].text
        )
        assert list(after[key].iter(SVG + "text"))[0].get("x") == (
            list(before[key].iter(SVG + "text"))[0].get("x")
        )
    assert "rotate(180)" in after["b"].get("transform")
    assert len(list(root.iter(SVG + "line"))) == 0  # Reference isn't a cutting path.
    assert len(list(root.iter(SVG + "path"))) == 2
    assert manifest["source_sha256"]


def test_pdf_is_vector_and_at_exact_inch_scale(simple_layout, tmp_path):
    original, manifest, report = simple_layout
    svg = export_svg(original, manifest, report, tmp_path / "nested.svg")
    pdf = export_pdf(svg, tmp_path / "nested.pdf")
    document = PdfReader(str(pdf))
    assert len(document.pages) == 1
    assert float(document.pages[0].mediabox.width) == pytest.approx(6 * 72)
    assert float(document.pages[0].mediabox.height) == pytest.approx(2 * 72)
    assert len(pdf.read_bytes()) > 500


def test_pdf_long_roll_splits_pages_without_resizing(tmp_path):
    svg = tmp_path / "long.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="6in" height="80in" viewBox="0 0 6 80">'
        '<path d="M1 1 L2 1 L2 75 L1 75 Z" fill="none" stroke="black"/>'
        '</svg>',
        encoding="utf-8",
    )
    pdf = export_pdf(svg, tmp_path / "long.pdf")
    pages = PdfReader(str(pdf)).pages
    assert len(pages) == 2
    assert [float(p.mediabox.width) for p in pages] == pytest.approx([432, 432])
    assert [float(p.mediabox.height) for p in pages] == pytest.approx([5184, 576])


def test_export_rejects_modified_input(simple_layout, tmp_path):
    original, manifest, report = simple_layout
    original.write_text(original.read_text().replace("FRONT", "CHANGED"), encoding="utf-8")
    with pytest.raises(ValueError, match="differs"):
        export_svg(original, manifest, report, tmp_path / "bad.svg")


def test_export_rejects_incomplete_report(simple_layout, tmp_path):
    original, manifest, report = simple_layout
    report["placements"].pop()
    with pytest.raises(ValueError, match="incomplete"):
        export_svg(original, manifest, report, tmp_path / "bad.svg")


def test_render_cli_does_not_reoptimize(simple_layout, tmp_path):
    original, manifest, report = simple_layout
    manpath, repath = tmp_path / "manifest.json", tmp_path / "report.json"
    manpath.write_text(json.dumps(manifest), encoding="utf-8")
    repath.write_text(json.dumps(report), encoding="utf-8")
    prefix = tmp_path / "output" / "trial"
    rc = main(["render", str(original), "--manifest", str(manpath),
               "--report", str(repath), "--output-prefix", str(prefix)])
    assert rc == 0
    assert (tmp_path / "output" / "trial.nested.svg").exists()
    assert (tmp_path / "output" / "trial.nested.pdf").exists()


def test_reference_44_original_outlines_survive_export(tmp_path):
    _, manifest = prepare_instance(SAMPLE, fabric_width_in=60)
    items = []
    y = 0.0
    for item in manifest["pieces"]:
        items.append({"id": item["id"], "x": 0.0, "y": y, "angle": 0})
        y += max(v["y"] for v in item["vertices"]) + 0.05
    report = validate_certificate(manifest, {"bins": [{"id": 0, "items": items}]})
    assert report["status"] == "FEASIBLE"
    out = export_svg(SAMPLE, manifest, report, tmp_path / "stacked.svg")
    original_inventory = inspect_svg(SAMPLE)
    output_inventory = inspect_svg(out)
    assert len(output_inventory.patterns) == len(original_inventory.patterns) == 44
    original_paths = {p.group_id: p.path_d for p in original_inventory.patterns}
    assert all(p.path_d == original_paths[p.group_id] for p in output_inventory.patterns)
