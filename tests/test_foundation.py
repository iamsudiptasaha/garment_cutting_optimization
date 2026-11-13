"""Phase 0 smoke tests; these do not validate geometry or nesting."""

import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

from garment_nesting import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_cli_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "garment_nesting.cli", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "0.1.0" in result.stdout


def test_fixture_is_parseable_svg() -> None:
    fixture = ROOT / "samples" / "FC_HH_Full_Pyjama.svg"
    root = ElementTree.parse(fixture).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
