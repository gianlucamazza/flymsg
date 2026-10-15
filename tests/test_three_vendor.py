"""The narrow renderer extension must not conceal unrelated vendor changes."""

import subprocess
import sys
from pathlib import Path


def test_three_extension_recovers_exact_upstream():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, str(root / "scripts/patch_three_line_ranges.py"), "--check"],
        check=True,
        capture_output=True,
    )
