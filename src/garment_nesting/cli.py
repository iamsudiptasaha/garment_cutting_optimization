"""Command-line entry point for SVG diagnostics."""

import argparse
import json

from garment_nesting import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Constrained garment nesting")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command")
    audit = subcommands.add_parser("audit", help="Approximate SVG paths and report geometry")
    audit.add_argument("svg", help="Input SVG file")
    audit.add_argument("--tolerance-mm", type=float, default=0.25)
    audit.add_argument("--output", help="Optional JSON output file")
    verify = subcommands.add_parser("verify", help="Cross-check SVG geometry approximations")
    verify.add_argument("svg", help="Input SVG file")
    verify.add_argument("--tolerance-mm", type=float, default=0.25)
    verify.add_argument("--output", help="Optional JSON output file")
    prepare = subcommands.add_parser("prepare", help="Build a solver instance in inches")
    prepare.add_argument("svg", help="Input SVG file")
    prepare.add_argument("--fabric-width-in", type=float, required=True)
    prepare.add_argument("--clearance-in", type=float, default=0.04)
    prepare.add_argument("--one-way", action="store_true")
    prepare.add_argument("--output-prefix", default="nesting")
    evaluate = subcommands.add_parser("evaluate", help="Validate a solver solution certificate")
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--certificate", required=True)
    evaluate.add_argument("--output", default="nesting-report.json")
    nest = subcommands.add_parser("nest", help="Optimize using an installed PackingSolver binary")
    nest.add_argument("svg", help="Input SVG file")
    nest.add_argument("--fabric-width-in", type=float, required=True)
    nest.add_argument("--clearance-in", type=float, default=0.04)
    nest.add_argument("--one-way", action="store_true")
    nest.add_argument("--time-limit", type=int, default=30)
    nest.add_argument("--solver-binary", default="packingsolver_irregular")
    nest.add_argument("--output-prefix", default="nesting")
    args = parser.parse_args(argv)
    if args.command == "audit":
        from pathlib import Path

        from garment_nesting.geometry.audit import audit_svg

        result = audit_svg(args.svg, args.tolerance_mm)
        payload = json.dumps(result.to_dict(), indent=2)
        if args.output:
            Path(args.output).write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)
        return 0 if all(piece.valid for piece in result.pieces) else 2
    if args.command == "verify":
        from pathlib import Path

        from garment_nesting.geometry.verify import verify_svg

        result = verify_svg(args.svg, args.tolerance_mm)
        payload = json.dumps(result.to_dict(), indent=2)
        if args.output:
            Path(args.output).write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)
        return 0 if result.passed else 2
    if args.command in ("prepare", "evaluate", "nest"):
        from pathlib import Path

        from garment_nesting.solvers.packing_solver import (
            prepare_instance,
            validate_certificate,
        )

        def write_json(path: str | Path, data: dict) -> None:
            Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        if args.command == "evaluate":
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            certificate = json.loads(Path(args.certificate).read_text(encoding="utf-8"))
            report = validate_certificate(manifest, certificate)
            write_json(args.output, report)
            print(json.dumps({k: v for k, v in report.items() if k != "placements"}, indent=2))
            return 0 if report["status"] == "FEASIBLE" else 2
        instance, manifest = prepare_instance(
            args.svg, args.fabric_width_in, clearance_in=args.clearance_in,
            one_way=args.one_way,
        )
        prefix = args.output_prefix
        instance_path = f"{prefix}.instance.json"
        manifest_path = f"{prefix}.manifest.json"
        write_json(instance_path, instance)
        write_json(manifest_path, manifest)
        print(f"Prepared {manifest['required_pieces']} pieces; width {manifest['fabric_width_in']} in")
        if args.command == "prepare":
            return 0
        import subprocess

        if args.time_limit <= 0:
            parser.error("--time-limit must be positive")
        certificate_path = f"{prefix}.solution.json"
        try:
            subprocess.run(
                [args.solver_binary, "--input", instance_path,
                 "--time-limit", str(args.time_limit), "--certificate", certificate_path],
                check=True, timeout=args.time_limit + 30,
            )
        except FileNotFoundError as exc:
            parser.error(f"PackingSolver not installed: {exc}. Use 'prepare' to export its JSON.")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            parser.error(f"Solver did not finish normally: {exc}")
        if not Path(certificate_path).exists():
            print("NOT_FOUND: solver produced no solution certificate")
            return 2
        report = validate_certificate(
            manifest, json.loads(Path(certificate_path).read_text(encoding="utf-8"))
        )
        write_json(f"{prefix}.report.json", report)
        print(json.dumps({k: v for k, v in report.items() if k != "placements"}, indent=2))
        return 0 if report["status"] == "FEASIBLE" else 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
