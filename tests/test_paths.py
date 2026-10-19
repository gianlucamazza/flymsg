"""Repository identity and wheel resources must not depend on the caller's cwd."""

import hashlib
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from flymsg import paths

ROOT = Path(__file__).resolve().parents[1]


def run(command, *, cwd, env=None):
    result = subprocess.run(
        command, cwd=cwd, env=env, check=False, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def source_env():
    env = os.environ.copy()
    env.pop("FLYMSG_ROOT", None)
    env["PYTHONPATH"] = str(ROOT / "src")
    return env


def test_unavailable_source_ancestry_ignores_checkout_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("FLYMSG_ROOT", raising=False)
    monkeypatch.setattr(
        paths, "__file__", str(tmp_path / "site-packages/flymsg/paths.py")
    )
    monkeypatch.chdir(ROOT)
    with pytest.raises(paths.RepositoryUnavailableError, match="FLYMSG_ROOT"):
        paths.require_repository_path(
            paths.repository_root() / "validation/behavior.yaml"
        )


@pytest.mark.parametrize("explicit", [False, True])
def test_lock_from_other_cwd(tmp_path, explicit):
    env = source_env()
    if explicit:
        # A different valid checkout proves the setting takes precedence.
        checkout = tmp_path / "checkout"
        (checkout / "validation").mkdir(parents=True)
        (checkout / "pyproject.toml").write_text('[project]\nname = "flymsg"\n')
        (checkout / "validation/preregistration.yaml").write_bytes(
            (ROOT / "validation/preregistration.yaml").read_bytes()
        )
        env["FLYMSG_ROOT"] = str(checkout)
    expected = env.get("FLYMSG_ROOT", str(ROOT))
    run(
        [
            sys.executable,
            "-c",
            f"import flymsg; from flymsg import prereg; assert str(prereg.ROOT) == {expected!r}; assert prereg.load()['version'] == 1",
        ],
        cwd=tmp_path,
        env=env,
    )


@pytest.mark.parametrize("setting", ["missing", "relative", "wrong-project"])
def test_invalid_setting_imports_but_refuses(tmp_path, setting):
    env = source_env()
    candidate = tmp_path / setting
    if setting == "wrong-project":
        (candidate / "validation").mkdir(parents=True)
        (candidate / "pyproject.toml").write_text('[project]\nname = "other"\n')
    env["FLYMSG_ROOT"] = "relative" if setting == "relative" else str(candidate)
    run([sys.executable, "-c", REFUSAL], cwd=tmp_path, env=env)


REFUSAL = """
import flymsg
from flymsg import behavior, prereg, pages, paths
from pathlib import Path
for operation in (prereg.load, behavior.load, lambda: pages.build(Path('site'))):
    try:
        operation()
    except paths.RepositoryUnavailableError as error:
        assert 'FLYMSG_ROOT' in str(error)
    else:
        raise AssertionError('repository operation did not refuse')
assert not Path('site').exists()
"""


@pytest.mark.parametrize(
    "module, alias, relative",
    [
        ("prereg", "PREREG_PATH", "validation/preregistration.yaml"),
        ("manifest", "PREREG_PATH", "validation/preregistration.yaml"),
        ("behavior", "PATH", "validation/behavior.yaml"),
        ("dn_arena", "PATH", "validation/dn_arena.yaml"),
        ("dn_arena", "INVENTORY", "docs/dn-arena-inventory.md"),
    ],
)
def test_public_aliases(module, alias, relative):
    imported = importlib.import_module(f"flymsg.{module}")
    assert imported.ROOT == ROOT == paths.repository_root()
    assert getattr(imported, alias) == ROOT / relative


@pytest.mark.slow
def test_wheel_outside_checkout(tmp_path):
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "FLYMSG_ROOT", "VIRTUAL_ENV"):
        env.pop(key, None)
    dist = tmp_path / "dist"
    run(["uv", "build", "--wheel", "--out-dir", str(dist)], cwd=ROOT, env=env)
    venv = tmp_path / "venv"
    run(["uv", "venv", "--python", sys.executable, str(venv)], cwd=tmp_path, env=env)
    python = venv / "bin/python"
    run(
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--python",
            str(python),
            str(next(dist.glob("*.whl"))),
        ],
        cwd=tmp_path,
        env=env,
    )
    # Pin the expected inventory to the source tree, including every vendor file.
    assets = [p for p in (ROOT / "src/flymsg/viz_static").rglob("*") if p.is_file()]
    assets.append(ROOT / "src/flymsg/pages.css")
    inventory = {
        str(p.relative_to(ROOT / "src/flymsg")): hashlib.sha256(
            p.read_bytes()
        ).hexdigest()
        for p in assets
    }
    code = f"""
import hashlib, importlib, pkgutil
from importlib.resources import files
import flymsg
for module in pkgutil.walk_packages(flymsg.__path__, 'flymsg.'):
    importlib.import_module(module.name)
for name, digest in {inventory!r}.items():
    assert hashlib.sha256(files('flymsg').joinpath(name).read_bytes()).hexdigest() == digest, name
from flymsg import viz
viz.copy_page(__import__('pathlib').Path('view'))
"""
    run([str(python), "-c", code + REFUSAL], cwd=tmp_path, env=env)
