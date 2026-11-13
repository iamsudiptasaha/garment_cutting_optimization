"""CLI: wire independent input, processor and output components."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from garment_nesting import __version__


def _write_json(path: str | Path, data: dict) -> None:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _summary(report: dict) -> None:
    print(json.dumps({key: value for key, value in report.items() if key != "placements"}, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixed-width garment nesting (inches)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")

    audit = commands.add_parser("audit", help="Inspect SVG geometry")
    audit.add_argument("svg")
    audit.add_argument("--tolerance-mm", type=float, default=0.25)
    audit.add_argument("--output")
    verify = commands.add_parser("verify", help="Compare polygon approximations")
    verify.add_argument("svg")
    verify.add_argument("--tolerance-mm", type=float, default=0.25)
    verify.add_argument("--output")

    prepare = commands.add_parser("prepare", help="Convert an SVG to a solver instance")
    prepare.add_argument("svg")
    prepare.add_argument("--fabric-width-in", type=float, required=True)
    prepare.add_argument("--clearance-in", type=float, default=0.04)
    prepare.add_argument("--one-way", action="store_true")
    prepare.add_argument("--output-prefix", default="output/nesting")

    nest = commands.add_parser("nest", help="Optimize and export SVG, PDF and JSON")
    nest.add_argument("svg")
    nest.add_argument("--fabric-width-in", type=float, required=True)
    nest.add_argument("--clearance-in", type=float, default=0.04)
    nest.add_argument("--one-way", action="store_true")
    nest.add_argument("--time-limit", type=int, default=30)
    nest.add_argument("--output-prefix", default="output/nesting")

    evaluate = commands.add_parser("evaluate", help="Validate a solver certificate")
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--certificate", required=True)
    evaluate.add_argument("--output", default="output/nesting.report.json")
    evaluate.add_argument("--svg", help="Also export SVG and PDF if result is feasible")
    evaluate.add_argument("--output-prefix", default="output/nesting")

    render = commands.add_parser("render", help="Create SVG and PDF from validated JSON")
    render.add_argument("svg", help="Original SVG used for solving")
    render.add_argument("--manifest", required=True)
    render.add_argument("--report", required=True)
    render.add_argument("--output-prefix", default="output/nesting")

    args = parser.parse_args(argv)
    if args.command in ("audit", "verify"):
        if args.command == "audit":
            from garment_nesting.geometry.audit import audit_svg

            result = audit_svg(args.svg, args.tolerance_mm)
            data = result.to_dict()
            passed = all(piece.valid for piece in result.pieces)
        else:
            from garment_nesting.geometry.verify import verify_svg

            result = verify_svg(args.svg, args.tolerance_mm)
            data = result.to_dict()
            passed = result.passed
        if args.output:
            _write_json(args.output, data)
        else:
            print(json.dumps(data, indent=2))
        return 0 if passed else 2

    if args.command in ("prepare", "nest", "evaluate", "render"):
        from garment_nesting.output import export_layouts
        from garment_nesting.processor.packing import prepare_instance, validate_certificate

        if args.command == "render":
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            report = json.loads(Path(args.report).read_text(encoding="utf-8"))
            svg, pdf = export_layouts(args.svg, manifest, report, args.output_prefix)
            print(f"SVG: {svg}\nPDF: {pdf}")
            return 0

        if args.command == "evaluate":
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            certificate = json.loads(Path(args.certificate).read_text(encoding="utf-8"))
            report = validate_certificate(manifest, certificate)
            _write_json(args.output, report)
            _summary(report)
            if report["status"] != "FEASIBLE":
                return 2
            if args.svg:
                svg, pdf = export_layouts(args.svg, manifest, report, args.output_prefix)
                print(f"SVG: {svg}\nPDF: {pdf}")
            return 0

        instance, manifest = prepare_instance(
            args.svg,
            args.fabric_width_in,
            clearance_in=args.clearance_in,
            one_way=args.one_way,
        )
        prefix = args.output_prefix
        instance_path = f"{prefix}.instance.json"
        manifest_path = f"{prefix}.manifest.json"
        _write_json(instance_path, instance)
        _write_json(manifest_path, manifest)
        print(
            f"Prepared {manifest['required_pieces']} pieces; "
            f"fabric width {manifest['fabric_width_in']} in"
        )
        if args.command == "prepare":
            return 0

        from garment_nesting.processor.run import solve_instance

        certificate_path = f"{prefix}.solution.json"
        for suffix in (".nested.svg", ".nested.pdf"):
            Path(f"{prefix}{suffix}").unlink(missing_ok=True)
        if args.time_limit <= 0:
            parser.error("--time-limit must be positive")
        try:
            solve_instance(instance_path, certificate_path, args.time_limit)
        except RuntimeError as exc:
            parser.error(str(exc))
        if not Path(certificate_path).exists():
            print("NOT_FOUND: solver produced no complete solution certificate")
            return 2
        certificate = json.loads(Path(certificate_path).read_text(encoding="utf-8"))
        report = validate_certificate(manifest, certificate)
        _write_json(f"{prefix}.report.json", report)
        _summary(report)
        if report["status"] != "FEASIBLE":
            return 2
        svg, pdf = export_layouts(args.svg, manifest, report, prefix)
        print(f"SVG: {svg}\nPDF: {pdf}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
