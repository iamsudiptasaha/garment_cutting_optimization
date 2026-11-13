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
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
