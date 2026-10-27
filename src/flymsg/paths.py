"""Resolve repository inputs independently of package assets and cwd.

FLYMSG_ROOT selects an absolute checkout containing pyproject.toml (project name
flymsg) and validation/. Otherwise only this module's source ancestry is searched.
"""

import os
import tomllib
from pathlib import Path

_UNAVAILABLE = Path("/__flymsg_repository_unavailable__")


class RepositoryUnavailableError(RuntimeError):
    """A repository operation needs an explicit flymsg checkout."""


def _is_repository(path: Path) -> bool:
    try:
        with (path / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream).get("project", {})
        return (
            isinstance(project, dict)
            and project.get("name") == "flymsg"
            and (path / "validation").is_dir()
        )
    except (OSError, ValueError):
        return False


def repository_root() -> Path:
    """Return a validated checkout or a deterministic unavailable location."""
    setting = os.environ.get("FLYMSG_ROOT")
    if setting is not None:
        candidate = Path(setting).expanduser()
        return (
            candidate.resolve()
            if candidate.is_absolute() and _is_repository(candidate)
            else _UNAVAILABLE
        )
    for candidate in Path(__file__).resolve().parents:
        if _is_repository(candidate):
            return candidate
    return _UNAVAILABLE


def require_repository_path(path: Path) -> Path:
    """Refuse unavailable defaults while allowing caller-supplied paths."""
    if path.is_relative_to(_UNAVAILABLE):
        raise RepositoryUnavailableError(
            "Repository unavailable: set FLYMSG_ROOT to an absolute flymsg checkout "
            "containing pyproject.toml (project.name = flymsg) and validation/."
        )
    return path
