"""Stable input/processor/output boundaries and one-piece SVG/PNG export."""
from __future__ import annotations

import json
from pathlib import Path
from struct import unpack
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

from garment_nesting.cli import main
from garment_nesting.input.svg import SVG_NS, inspect_svg
from garment_nesting.output.png import export_png
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
    assert root.get("width") == "7.8in"  # includes annotation margins
    assert root.get("height") == "3.55in"
    assert root.get("viewBox") == "0 0 7.8 3.55"
    assert root.get("data-fabric-width-in") == "6"
    assert root.get("data-fabric-length-in") == "2"
    guide = root.find(f".//{SVG}rect[@id='fabric-boundary']")
    assert guide is not None
    assert guide.get("width") == "6"
    assert guide.get("height") == "2"
    assert root.find(f".//{SVG}g[@id='fabric-guide']") is not None
    assert root.get("data-grain-direction") == "y"
    before = {g.get("id"): g for g in source.iter(SVG + "g") if g.find(SVG + "path") is not None}
    after = {g.get("id"): g for g in root.iter(SVG + "g") if g.find(SVG + "path") is not None}
    assert set(after) == set(before) == {"a", "b"}
    for key, source_group in before.items():
        assert after[key].find(SVG + "path").get("d") == source_group.find(SVG + "path").get("d")
        original_label = next(source_group.iter(SVG + "text"))
        exported_label = next(after[key].iter(SVG + "text"))
        assert exported_label.text == original_label.text
        assert exported_label.get("x") == original_label.get("x")
    assert "rotate(180)" in after["b"].get("transform")
    assert len(list(root.iter(SVG + "line"))) >= 4  # Dimension markers, not cutting paths.
    assert len(list(root.iter(SVG + "path"))) == 2
    assert manifest["source_sha256"]


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return unpack(">II", data[16:24])


def test_png_is_one_continuous_shareable_image(simple_layout, tmp_path):
    from garment_nesting.output.png import export_rasters

    original, manifest, report = simple_layout
    svg = export_svg(original, manifest, report, tmp_path / "nested.svg")
    png, jpg = export_rasters(
        svg, tmp_path / "nested.png", tmp_path / "nested.jpg",
    )
    assert _png_dimensions(png) == (3000, 1365)
    with Image.open(jpg) as preview:
        assert preview.format == "JPEG"
        assert preview.size == (3000, 1365)
    assert png.stat().st_size > 500
    assert jpg.stat().st_size > 500


def test_long_roll_is_one_png_without_pagination(tmp_path):
    svg = tmp_path / "long.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="6in" height="80in" viewBox="0 0 6 80">'
        '<path d="M1 1 L2 1 L2 75 L1 75 Z" fill="none" stroke="black"/>'
        '</svg>',
        encoding="utf-8",
    )
    png = export_png(svg, tmp_path / "long.png")
    assert _png_dimensions(png) == (432, 5760)


def test_extremely_long_layout_does_not_get_unreadable_png(tmp_path):
    svg = tmp_path / "very_long.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="36in" height="2000in" viewBox="0 0 36 2000"/>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="image size limit"):
        export_png(svg, tmp_path / "unreadable.png")


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
    assert (tmp_path / "output" / "trial.nested.png").exists()
    assert (tmp_path / "output" / "trial.nested.jpg").exists()


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


def test_image_resolution_is_not_silently_reduced(tmp_path):
    from garment_nesting.output.png import export_rasters

    svg = tmp_path / "strip.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="36in" '
        'height="100in" viewBox="0 0 36 100"/>',
        encoding="utf-8",
    )
    png, jpg = export_rasters(
        svg, tmp_path / "strip.png", tmp_path / "strip.jpg",
        preview_width_px=3200,
    )
    assert _png_dimensions(png) == (3200, 8889)
    with Image.open(jpg) as image:
        assert image.size == (3200, 8889)


def test_oversize_preview_fails_before_creating_files(tmp_path):
    from garment_nesting.output.png import export_rasters

    svg = tmp_path / "strip.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="36in" '
        'height="1500in" viewBox="0 0 36 1500"/>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="image size limit"):
        export_rasters(svg, tmp_path / "strip.png", tmp_path / "strip.jpg")
    assert not (tmp_path / "strip.png").exists()
    assert not (tmp_path / "strip.jpg").exists()
