"""Project CLI. Geometry import and nesting are planned for later phases."""

import argparse

from garment_nesting import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Constrained garment nesting")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
