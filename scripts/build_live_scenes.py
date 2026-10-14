"""Rebuild the scenes the Pages site serves live.

Usage: python scripts/build_live_scenes.py [NAME ...]

Runs the gallery exports on the local MaleCNS tables (`flymsg fetch` and
`flymsg build` first) and keeps scene.json, activity.bin, partners.json and manifest.json in
docs/live/<name>/ (graded.bin too for an eye replay). The page itself is copied by the site build, not stored here. With
names, only those scenes and comparisons are rebuilt, so the others keep their manifests.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# exported even when silent, so a comparison shows them at zero, not "not exported"
KEEP_LOOMING = ["--keep", "TTMn_R", "DNp01", "DNp02", "DNp06"]
KEEP_SIDES = ["--keep", "TTMn", "DNp01", "DNp02", "DNp06"]
SCENES = {
    "looming": ["--sim", "LC4_R", *KEEP_LOOMING],
    "song": ["--sim", "pIP10"],
    "anatomy": ["--types", "pIP10", "dPR1", "dMS9"],
    "looming-dnp01-silenced": ["--sim", "LC4_R", "--silence", "DNp01", *KEEP_LOOMING],
    "looming-dnp01-dnp02-silenced": [
        "--sim",
        "LC4_R",
        "--silence",
        "DNp01",
        "DNp02",
        *KEEP_LOOMING,
    ],
    "looming-dnp01-dnp06-silenced": [
        "--sim",
        "LC4_R",
        "--silence",
        "DNp01",
        "DNp06",
        *KEEP_LOOMING,
    ],
    "looming-left": ["--sim", "LC4_L", *KEEP_SIDES],
    "looming-bilateral": ["--sim", "LC4", *KEEP_SIDES],
    # an ON edge of the locked T4/T5 protocol at its strongest lamina gain (configuration 11:
    # gain 16, LMC and medulla 200 Hz); graded neurons glow by their potential
    "eye-on": ["--eye", "on", "front_to_back", "--eye-config", "11"],
}
# Pairs shown by flymsg viz-compare: (A, B, labels, statuses, notes)
COMPARISONS = {
    "looming-vs-dnp01": (
        "looming",
        "looming-dnp01-silenced",
        ("LC4_R", "LC4_R, both DNp01 silenced"),
        ("exploratory", "failed"),
        (
            "seed 0 replay, not the scored battery",
            "behavior v1 silence check fails: TTMn_R still fires with both DNp01 silenced",
        ),
    ),
    "dnp01-vs-dnp02": (
        "looming-dnp01-silenced",
        "looming-dnp01-dnp02-silenced",
        ("LC4_R, both DNp01 silenced", "LC4_R, DNp01 and DNp02 silenced"),
        ("failed", "exploratory"),
        (
            "behavior v1 silence check fails: TTMn_R still fires with both DNp01 silenced",
            "residual scan v2 names DNp02 and DNp06 (seeds 0-2, 20-22); this is the seed 0 replay",
        ),
    ),
    "dnp01-vs-dnp06": (
        "looming-dnp01-silenced",
        "looming-dnp01-dnp06-silenced",
        ("LC4_R, both DNp01 silenced", "LC4_R, DNp01 and DNp06 silenced"),
        ("failed", "exploratory"),
        (
            "behavior v1 silence check fails: TTMn_R still fires with both DNp01 silenced",
            "residual scan v2 names DNp02 and DNp06 (seeds 0-2, 20-22); this is the seed 0 replay",
        ),
    ),
    "right-vs-left": (
        "looming",
        "looming-left",
        ("LC4_R (looming from the right)", "LC4_L (looming from the left)"),
        ("exploratory", "exploratory"),
        (
            "seed 0 replay",
            "seed 0 replay of the mirrored arm; MaleCNS is not left-right symmetric",
        ),
    ),
}
KEEP = ("scene.json", "activity.bin", "graded.bin", "partners.json", "manifest.json")


def main(names=()) -> None:
    live = ROOT / "docs" / "live"
    unknown = set(names) - set(SCENES) - set(COMPARISONS)
    if unknown:
        sys.exit(f"unknown scene: {', '.join(sorted(unknown))}")
    scenes = {k: v for k, v in SCENES.items() if not names or k in names}
    comparisons = {k: v for k, v in COMPARISONS.items() if not names or k in names}
    with tempfile.TemporaryDirectory() as tmp:
        # every export runs before docs/live changes, so each manifest sees a clean tree
        for name, args in scenes.items():
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from flymsg.cli import main; main()",
                    "viz",
                    *args,
                    "--out",
                    str(Path(tmp) / name),
                ],
                cwd=ROOT,
                check=True,
            )
        for name in scenes:
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
        for name, (a, b, labels, statuses, notes) in comparisons.items():
            dst = live / name
            shutil.rmtree(dst, ignore_errors=True)
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from flymsg.cli import main; main()",
                    "viz-compare",
                    str(live / a),
                    str(live / b),
                    "--labels",
                    *labels,
                    "--status",
                    *statuses,
                    "--notes",
                    *notes,
                    "--out",
                    str(dst),
                ],
                cwd=ROOT,
                check=True,
            )
            for f in dst.iterdir():  # the page is copied by the site build
                if f.name not in (
                    "scene.json",
                    "activity.bin",
                    "activity_b.bin",
                    "partners.json",
                    "manifest_a.json",
                    "manifest_b.json",
                ):
                    shutil.rmtree(f) if f.is_dir() else f.unlink()
            print(f"{name} -> {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
