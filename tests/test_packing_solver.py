"""Inch-based solver input and certificate acceptance checks."""
import json
from pathlib import Path

import pytest

from garment_nesting.cli import main
from garment_nesting.solvers.packing_solver import prepare_instance, validate_certificate

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "FC_HH_Full_Pyjama.svg"


def test_44_piece_instance_in_inches():
    instance, manifest = prepare_instance(SAMPLE, fabric_width_in=60)
    assert instance["objective"] == "open-dimension-y"
    assert instance["bin_types"][0]["width"] == 60
    assert instance["bin_types"][0]["height"] > 0
    assert len(instance["item_types"]) == manifest["required_pieces"] == 44
    assert manifest["units"] == "in"
    assert manifest["piece_area_sq_in"] > 0
    assert len({piece["group_id"] for piece in manifest["pieces"]}) == 44
    assert all(p["copies"] == 1 for p in instance["item_types"])
    assert all(
        p["allowed_rotations"] == [
            {"start": 0, "end": 0, "mirror": False},
            {"start": 180, "end": 180, "mirror": False},
        ]
        for p in instance["item_types"]
    )


def test_one_way_fabric_disallows_turning():
    instance, _ = prepare_instance(SAMPLE, 60, one_way=True)
    assert all(p["allowed_rotations"] == [
        {"start": 0, "end": 0, "mirror": False}
    ] for p in instance["item_types"])


def test_narrow_fabric_is_proven_impossible():
    with pytest.raises(ValueError, match="PROVEN_INFEASIBLE"):
        prepare_instance(SAMPLE, fabric_width_in=0.5)


def test_invalid_width():
    for width in (0, -10, float("nan")):
        with pytest.raises(ValueError, match="fabric_width_in"):
            prepare_instance(SAMPLE, fabric_width_in=width)


def _fixture():
    rect = [{"x": 0, "y": 0}, {"x": 2, "y": 0},
            {"x": 2, "y": 2}, {"x": 0, "y": 2}]
    manifest = {
        "units": "in", "fabric_width_in": 6, "clearance_in": 0.04,
        "one_way": False, "required_pieces": 2, "piece_area_sq_in": 8,
        "pieces": [
            {"id": 0, "group_id": "a", "copies": 1, "vertices": rect},
            {"id": 1, "group_id": "b", "copies": 1, "vertices": rect},
        ],
    }
    certificate = {"bins": [{"id": 0, "copies": 1, "items": [
        {"id": 0, "x": 0, "y": 0, "angle": 0, "mirror": False},
        {"id": 1, "x": 2.1, "y": 0, "angle": 0, "mirror": False},
    ]}]}
    return manifest, certificate


def test_certificate_reports_consumed_fabric_length():
    manifest, certificate = _fixture()
    result = validate_certificate(manifest, certificate)
    assert result["status"] == "FEASIBLE"
    assert result["fabric_length_consumed_in"] == 2
    assert result["placed_pieces"] == 2
    assert result["fabric_area_sq_in"] == 12
    assert result["utilization_pct"] == pytest.approx(66.66666667)
    assert result["wastage_pct"] == pytest.approx(33.33333333)


@pytest.mark.parametrize("x,match", [
    (1, "overlap"),
    (2.02, "clearance"),
    (5, "fabric bounds"),
])
def test_bad_placement_rejected(x, match):
    manifest, certificate = _fixture()
    certificate["bins"][0]["items"][1]["x"] = x
    with pytest.raises(ValueError, match=match):
        validate_certificate(manifest, certificate)


def test_missing_piece_returns_not_found():
    manifest, certificate = _fixture()
    certificate["bins"][0]["items"].pop()
    result = validate_certificate(manifest, certificate)
    assert result["status"] == "NOT_FOUND"
    assert result["placed_pieces"] == 1


def test_mirroring_and_90_degree_rotation_rejected():
    manifest, certificate = _fixture()
    certificate["bins"][0]["items"][0]["mirror"] = True
    with pytest.raises(ValueError, match="Mirroring"):
        validate_certificate(manifest, certificate)
    certificate["bins"][0]["items"][0]["mirror"] = False
    certificate["bins"][0]["items"][0]["angle"] = 90
    with pytest.raises(ValueError, match="rotation"):
        validate_certificate(manifest, certificate)


def test_prepare_cli_writes_packing_input(tmp_path):
    prefix = tmp_path / "trial"
    status = main(["prepare", str(SAMPLE), "--fabric-width-in", "60",
                   "--output-prefix", str(prefix)])
    assert status == 0
    instance = json.loads((tmp_path / "trial.instance.json").read_text())
    manifest = json.loads((tmp_path / "trial.manifest.json").read_text())
    assert len(instance["item_types"]) == manifest["required_pieces"] == 44



def test_native_packingsolver_smoke(tmp_path):
    psi = pytest.importorskip("packingsolver.irregular")
    # Exercise the real Python wheel / JSON API without running 44 large items.
    rect = [{"x": 0, "y": 0}, {"x": 2, "y": 0},
            {"x": 2, "y": 2}, {"x": 0, "y": 2}]
    instance = {
        "objective": "open-dimension-y",
        "parameters": {"item_item_minimum_spacing": 0.04},
        "bin_types": [{"type": "rectangle", "width": 6, "height": 6}],
        "item_types": [
            {"type": "polygon", "vertices": rect, "copies": 1,
             "allowed_rotations": [{"start": 0, "end": 0, "mirror": False}]},
        ],
    }
    instance_path = tmp_path / "instance.json"
    solution_path = tmp_path / "solution.json"
    instance_path.write_text(json.dumps(instance), encoding="utf-8")
    builder = psi.InstanceBuilder()
    builder.read(str(instance_path))
    parameters = psi.OptimizeParameters()
    parameters.time_limit = 2
    output = psi.optimize(builder.build(), parameters)
    output.solution.write(str(solution_path))
    assert solution_path.exists()
    solved = json.loads(solution_path.read_text())
    manifest = {
        "fabric_width_in": 6, "clearance_in": 0.04, "one_way": True,
        "required_pieces": 1, "piece_area_sq_in": 4,
        "pieces": [{"id": 0, "group_id": "square", "copies": 1, "vertices": rect}],
    }
    report = validate_certificate(manifest, solved)
    assert report["status"] == "FEASIBLE"
    assert report["required_pieces"] == 1


def test_consumed_length_ignores_leading_empty_strip():
    manifest, certificate = _fixture()
    for piece in certificate["bins"][0]["items"]:
        piece["y"] += 10
    result = validate_certificate(manifest, certificate)
    assert result["fabric_length_consumed_in"] == pytest.approx(2)
    assert result["fabric_area_sq_in"] == pytest.approx(12)
    assert result["wastage_pct"] == pytest.approx(100 * (12 - 8) / 12)


def test_longitudinal_gap_increases_consumed_length_and_wastage():
    manifest, certificate = _fixture()
    certificate["bins"][0]["items"][1]["y"] = 2.1
    result = validate_certificate(manifest, certificate)
    expected_total = 6 * 4.1
    assert result["fabric_length_consumed_in"] == pytest.approx(4.1)
    assert result["fabric_area_sq_in"] == pytest.approx(expected_total)
    assert result["wastage_pct"] == pytest.approx((expected_total - 8) * 100 / expected_total)
    assert result["utilization_pct"] + result["wastage_pct"] == pytest.approx(100)
