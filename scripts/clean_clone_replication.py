"""Same-machine SF5 reproduction; opt-in execution, never a held-out scoring runner.

Use --help. Each invocation reserves a new directory and preserves all evidence on failure.
"""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHOICES = {
    "positive": "results/convergence/v1.executions/be1ac2741e08d8f0432fd49fed5ebd74fab5062d79cb280a39637f49ae31997c/output",
    "negative": "results/jump3d/v1",
    "no-go": "results/gf_looming/v1",
}

# Python audit hooks execute before open, including scipy's held-out file readers.
# Presence-only stat calls remain available to the historical GF CLI preflight.
GUARD = """import os
import sys
from pathlib import Path
root = Path(os.environ["SF5_INPUT_ROOT"]).resolve()
allowed = {root / "neurons.parquet", root / "edges.parquet"}
def guard(event, args):
    if event != "open" or isinstance(args[0], int):
        return
    lexical = Path(os.path.abspath(os.fsdecode(args[0])))
    path = lexical.resolve()
    if (lexical.is_relative_to(root) or path.is_relative_to(root)) and path not in allowed:
        raise PermissionError("SF5 forbids opening non-compact input: " + str(path))
sys.addaudithook(guard)
"""


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compare(entry, output):
    actual = {
        p.relative_to(output).as_posix(): sha256(p)
        for p in output.rglob("*")
        if p.is_file() and p != output / "manifest.json"
    }
    manifest = json.loads((output / "manifest.json").read_text())
    verdict = manifest.get("extra", {}).get("verdict")
    return {
        "outputs_sha256": actual,
        "hashes_match": actual == entry["outputs_sha256"],
        "verdict": verdict,
        "verdict_matches": verdict == entry["verdict"],
        "config_matches": manifest["config"] == entry["config"],
        "seeds_match": manifest["seeds"] == entry["seeds"],
        "source_matches": manifest["git"]["commit"] == entry["source_commit"]
        and manifest["git"]["dirty"] is False,
    }


def reproduce(args):
    entry = next(
        e
        for e in json.loads(
            (ROOT / "docs/evidence/replication-index.json").read_text()
        )["results"]
        if e["result"] == CHOICES[args.result]
    )
    if entry["dirty"] is not False:
        raise ValueError("source must be reconstructible from a clean commit")
    if args.source_commit is not None and args.source_commit != entry["source_commit"]:
        raise ValueError("given source commit differs from the selected index entry")
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    clone = destination / "repo"
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "VIRTUAL_ENV",
            "PYTHONPATH",
            "PYTHONHOME",
            "UV_PROJECT_ENVIRONMENT",
            "UV_CACHE_DIR",
            "UV_NO_SYNC",
            "UV_FROZEN",
            "UV_OFFLINE",
        }
    }
    env.update(
        UV_PROJECT_ENVIRONMENT=str(destination / "venv"),
        UV_CACHE_DIR=str(destination / "uv-cache"),
        UV_LINK_MODE="copy",
        NUMBA_CACHE_DIR=str(destination / "numba-cache"),
        FLYMSG_DATA=str(args.data.resolve()),
        SF5_INPUT_ROOT=str(args.data.resolve()),
    )
    guard = destination / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(GUARD)
    env["PYTHONPATH"] = str(guard)
    commands = []

    def run(command, cwd):
        commands.append(command)
        with (destination / "commands.json").open("w") as stream:
            json.dump(commands, stream, indent=2)
        with (destination / "process.log").open("ab") as log:
            subprocess.run(
                command, cwd=cwd, env=env, stdout=log, stderr=log, check=True
            )

    run(["git", "clone", "--no-local", args.repository, str(clone)], destination)
    run(["git", "checkout", "--detach", entry["source_commit"]], clone)
    # The selected historical entries read only the two compact tables before no-go.
    if set(entry["inputs_sha256"]) != {"neurons.parquet", "edges.parquet"}:
        raise ValueError("unexpected input inventory for the restricted protocol")
    for name, expected in entry["inputs_sha256"].items():
        if sha256(args.data / name) != expected:
            raise ValueError(f"dataset checksum mismatch: {name}")
    # Ignore inherited uv state and caches: this directory and environment are new.
    run(["uv", "sync", "--frozen", "--python", entry["python"]], clone)
    run(["uv", "run", "--frozen", "flymsg", *shlex.split(entry["command"])], clone)
    manifests = list((clone / "runs").rglob("manifest.json"))
    if len(manifests) != 1:
        raise ValueError(f"expected exactly one fresh result, found {len(manifests)}")
    result = compare(entry, manifests[0].parent)
    for name, expected in entry["inputs_sha256"].items():
        if sha256(args.data / name) != expected:
            raise ValueError(f"dataset changed during run: {name}")
    report = {
        "schema": "flymsg.clean-clone-replication/v1",
        "scope": "same-machine, same-operator; no independent sign-off",
        "expected": entry,
        "output": str(manifests[0].parent),
        **result,
    }
    report["passed"] = all(
        result[k]
        for k in (
            "hashes_match",
            "verdict_matches",
            "config_matches",
            "seeds_match",
            "source_matches",
        )
    )
    (destination / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise ValueError(f"replication mismatch: {destination / 'comparison.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", choices=CHOICES, required=True)
    parser.add_argument(
        "--data", type=Path, required=True, help="existing MaleCNS data directory"
    )
    parser.add_argument(
        "--destination", type=Path, required=True, help="must not exist"
    )
    parser.add_argument(
        "--repository", default=str(ROOT), help="local repository or GitHub URL"
    )
    parser.add_argument(
        "--source-commit",
        help="optional full commit; must equal the selected index source",
    )
    args = parser.parse_args()
    if shutil.which("uv") is None:
        parser.error("uv is required")
    reproduce(args)


if __name__ == "__main__":
    main()
