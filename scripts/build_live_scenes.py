"""Rebuild the scenes the Pages site serves live. Usage: python scripts/build_live_scenes.py

Runs the three gallery exports on the local MaleCNS tables (`flymsg fetch` and
`flymsg build` first) and keeps scene.json, activity.bin and manifest.json in
docs/live/<name>/. The page itself is copied by the site build, not stored here.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENES = {
    "looming": ["--sim", "LC4_R"],
    "song": ["--sim", "pIP10"],
    "anatomy": ["--types", "pIP10", "dPR1", "dMS9"],
}
KEEP = ("scene.json", "activity.bin", "manifest.json")


def main() -> None:
    live = ROOT / "docs" / "live"
    with tempfile.TemporaryDirectory() as tmp:
        # every export runs before docs/live changes, so each manifest sees a clean tree
        for name, args in SCENES.items():
            subprocess.run(
                [sys.executable, "-c", "from flymsg.cli import main; main()",
                 "viz", *args, "--out", str(Path(tmp) / name)],
                cwd=ROOT,
                check=True,
            )  # fmt: skip
        for name in SCENES:
            src, dst = Path(tmp) / name, live / name
            shutil.rmtree(dst, ignore_errors=True)
            dst.mkdir(parents=True)
            for f in KEEP:
                if (src / f).is_file():
                    shutil.copy(src / f, dst / f)
            manifest = json.loads((dst / "manifest.json").read_text())
            manifest.pop("cwd", None)  # a local path, not provenance
            (dst / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            print(f"{name} -> {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
