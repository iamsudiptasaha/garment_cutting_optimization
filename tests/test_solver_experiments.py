"""End-to-end GUI job selection -> baseline/native solver -> independent checks."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from garment_nesting.job_config import DEFAULT_FABRIC_SETTINGS, job_input_payload
from garment_nesting.job_selection import edit_pattern, namespace_uploaded_rows
from garment_nesting.processor.experiments import (
    MAX_RUN_PIECES,
    prepare_job,
    run_experiments,
    shelf_certificate,
    validate_job_certificate,
)
from garment_nesting.processor.preview import geometry_preview_uri
from garment_nesting.webapp import inspect_upload

REFERENCE = Path(__file__).resolve().parents[1] / "samples" / "FC_HH_Full_Pyjama.svg"
SIMPLE = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'width="50in" height="50in" viewBox="0 0 50 50">'
    '<g id="front"><path d="M 2 3 L 4 3 L 4 5 L 2 5 Z" />'
    '<text x="2.5" y="4">FRONT</text></g>'
    '<g id="back"><path d="M 20 20 L 23 20 L 23 22 L 20 22 Z" />'
    '<text x="21" y="21">BACK</text></g>'
    '</svg>'
).encode()


def _make_job(
    *, sources: dict[str, dict] | None = None,
    copies: tuple[int, int] = (2, 1),
    fabric_width: float = 12,
    gap: float = 0.04,
    margin: tuple[float, float] = (0.2, 0.1),
    max_length: float | None = None,
    angles: tuple[str, str] = ("0° only", "180° only"),
):
    sources = sources or {"s0": {"filename": "cutting.svg", "content": SIMPLE}}
    rows = namespace_uploaded_rows(inspect_upload("cutting.svg", SIMPLE), "s0")
    for i, row in enumerate(rows):
        edit_pattern(rows, row["id"], "qty", copies[i])
        edit_pattern(rows, row["id"], "piece_margin_in", margin[i])
        edit_pattern(rows, row["id"], "rotation", angles[i])
    fabric = DEFAULT_FABRIC_SETTINGS.copy()
    fabric["fabric_width_in"] = fabric_width
    fabric["piece_clearance_in"] = gap
    fabric["max_length_in"] = max_length
    return sources, job_input_payload(rows, fabric)


def test_shelf_places_all_copies_while_respecting_individual_margins():
    sources, job = _make_job()
    results = run_experiments(sources, job, ["shelf"])
    assert results["best_algorithm"] == "shelf"
    candidate = results["candidates"][0]
    assert candidate["status"] == "FEASIBLE"
    report = candidate["report"]
    assert report["required_pieces"] == report["placed_pieces"] == 3
    assert {item["rotation_deg"] for item in report["placements"]} == {0, 180}
    assert {item["copy"] for item in report["placements"]} == {1, 2}
    assert 0 < report["utilization_pct"] < 100
    assert report["utilization_pct"] + report["wastage_pct"] == pytest.approx(100)
    assert report["fabric_length_consumed_in"] >= 2
    preview = geometry_preview_uri(results["manifest"], report)
    assert preview.startswith("data:image/svg+xml;base64,")


def test_zero_copy_is_skipped_not_omitted_silently():
    sources, job = _make_job(copies=(0, 2))
    results = run_experiments(sources, job, ["shelf"])
    assert len(results["manifest"]["pieces"]) == 1
    assert results["manifest"]["pieces"][0]["group_id"] == "back"
    assert results["manifest"]["required_pieces"] == 2
    assert results["candidates"][0]["report"]["placed_pieces"] == 2


def test_multiple_uploads_with_same_filename_do_not_merge_group_id():
    sources = {
        "first": {"filename": "cutting.svg", "content": SIMPLE},
        "second": {"filename": "cutting.svg", "content": SIMPLE},
    }
    rows = namespace_uploaded_rows(inspect_upload("cutting.svg", SIMPLE), "first")
    rows += namespace_uploaded_rows(inspect_upload("cutting.svg", SIMPLE), "second")
    for row in rows:
        edit_pattern(rows, row["id"], "qty", 1 if row["group"] == "front" else 0)
    fabric = DEFAULT_FABRIC_SETTINGS.copy()
    fabric["fabric_width_in"] = 12
    job = job_input_payload(rows, fabric)
    instance, manifest = prepare_job(sources, job)
    assert len(instance["item_types"]) == 2
    assert {item["source_id"] for item in manifest["pieces"]} == {"first", "second"}
    assert run_experiments(sources, job, ["shelf"])["candidates"][0]["status"] == "FEASIBLE"


def test_reference_svg_one_selected_piece_can_be_solved():
    data = REFERENCE.read_bytes()
    rows = namespace_uploaded_rows(inspect_upload(REFERENCE.name, data), "reference")
    for row in rows:
        edit_pattern(rows, row["id"], "qty", 0)
    edit_pattern(rows, rows[0]["id"], "qty", 2)
    settings = DEFAULT_FABRIC_SETTINGS.copy()
    settings["fabric_width_in"] = 60
    result = run_experiments(
        {"reference": {"filename": REFERENCE.name, "content": data}},
        job_input_payload(rows, settings),
        ["shelf"],
    )
    assert result["candidates"][0]["status"] == "FEASIBLE"
    assert result["candidates"][0]["report"]["placed_pieces"] == 2
    assert REFERENCE.read_bytes() == data


def test_rejects_missing_uploaded_bytes_and_tampered_filename():
    sources, job = _make_job()
    with pytest.raises(ValueError, match="unavailable"):
        prepare_job({}, job)
    bad = deepcopy(sources)
    bad["s0"]["filename"] = "other.svg"
    with pytest.raises(ValueError, match="filename"):
        prepare_job(bad, job)


def test_proven_infeasible_width_and_area_are_not_silent_failures():
    sources, job = _make_job(fabric_width=1)
    with pytest.raises(ValueError, match="PROVEN_INFEASIBLE"):
        prepare_job(sources, job)
    sources, job = _make_job(fabric_width=5, max_length=2.5, copies=(4, 4))
    with pytest.raises(ValueError, match="PROVEN_INFEASIBLE"):
        prepare_job(sources, job)


def test_incomplete_certificate_is_not_found_not_feasible():
    sources, job = _make_job()
    _, manifest = prepare_job(sources, job)
    cert = shelf_certificate(manifest)
    cert["bins"][0]["items"].pop()
    report = validate_job_certificate(manifest, cert)
    assert report["status"] == "NOT_FOUND"
    assert report["required_pieces"] == 3
    assert report["placed_pieces"] == 2


def test_rejects_overlap_bad_rotation_and_mirror_in_certificate():
    sources, job = _make_job(margin=(0, 0))
    _, manifest = prepare_job(sources, job)
    cert = shelf_certificate(manifest)
    cert["bins"][0]["items"][1]["x"] = cert["bins"][0]["items"][0]["x"]
    cert["bins"][0]["items"][1]["y"] = cert["bins"][0]["items"][0]["y"]
    with pytest.raises(ValueError, match="Overlapping|Insufficient piece gap"):
        validate_job_certificate(manifest, cert)
    cert = shelf_certificate(manifest)
    cert["bins"][0]["items"][0]["angle"] = 90
    with pytest.raises(ValueError, match="Disallowed rotation"):
        validate_job_certificate(manifest, cert)
    cert = shelf_certificate(manifest)
    cert["bins"][0]["items"][0]["mirror"] = True
    with pytest.raises(ValueError, match="Mirroring"):
        validate_job_certificate(manifest, cert)


def test_validator_detects_pairwise_gap_violation_even_when_no_overlap():
    sources, job = _make_job(copies=(2, 0), margin=(0.25, 0))
    _, manifest = prepare_job(sources, job)
    cert = shelf_certificate(manifest)
    a, b = cert["bins"][0]["items"]
    # Two squares are 2in wide. Deliberately leave only a 0.2in edge gap.
    a.update({"x": 0, "y": 0})
    b.update({"x": 2.2, "y": 0})
    with pytest.raises(ValueError, match="Insufficient piece gap"):
        validate_job_certificate(manifest, cert)


def test_width_and_length_reserves_are_counted():
    sources, job = _make_job(copies=(1, 0), fabric_width=10)
    job["fabric"]["fabric_left_margin_in"] = 1
    job["fabric"]["fabric_right_margin_in"] = 1
    job["fabric"]["fabric_start_margin_in"] = 2
    job["fabric"]["fabric_end_margin_in"] = 3
    result = run_experiments(sources, job, ["shelf"])["candidates"][0]
    assert result["status"] == "FEASIBLE"
    report = result["report"]
    assert report["fabric_width_in"] == 10
    assert report["usable_width_in"] == 8
    assert report["fabric_length_consumed_in"] >= 7
    assert min(p["x_in"] for p in report["placements"]) >= 1


def test_max_length_baseline_reports_not_found_not_infeasible():
    sources, job = _make_job(
        copies=(2, 1), fabric_width=5, max_length=5, margin=(0.2, 0.1),
    )
    # The simple shelf might not find a layout although a general polygon
    # solver could: never mislabel this as a proof of mathematical infeasibility.
    result = run_experiments(sources, job, ["shelf"])["candidates"][0]
    assert result["status"] in {"NOT_FOUND", "FEASIBLE"}


def test_invalid_algo_and_large_jobs_rejected_before_running():
    sources, job = _make_job()
    with pytest.raises(ValueError, match="Choose"):
        run_experiments(sources, job, [])
    with pytest.raises(ValueError, match="Unknown"):
        run_experiments(sources, job, ["made-up"])
    job["patterns"][0]["copies"] = MAX_RUN_PIECES + 1
    with pytest.raises(ValueError, match="reduce copies"):
        prepare_job(sources, job)


def test_native_solver_contract_or_explicit_unavailable():
    sources, job = _make_job(copies=(1, 0), margin=(0, 0), fabric_width=10)
    job["fabric"]["time_limit_seconds"] = 3
    result = run_experiments(sources, job, ["native"])["candidates"][0]
    if result["status"] == "UNAVAILABLE":
        assert "PackingSolver" in result["message"]
    else:
        assert result["status"] == "FEASIBLE", result
        assert result["report"]["placed_pieces"] == 1


def test_invalid_candidate_does_not_block_comparison():
    sources, job = _make_job(copies=(1, 0), margin=(0, 0))
    result = run_experiments(sources, job, ["shelf", "native"])
    assert result["candidates"]
    assert result["best_algorithm"] in {"shelf", "native"}
    assert all(c["status"] in {"FEASIBLE", "UNAVAILABLE", "NOT_FOUND", "ERROR"}
               for c in result["candidates"])
