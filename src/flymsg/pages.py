"""Build the GitHub Pages site from the README and the docs.

Pages sit next to each other: the README is ``index.html``, ``docs/validation.md``
is ``validation.html``. Heading anchors follow GitHub's rule (punctuation other
than hyphens drops out, spaces become hyphens, a repeated heading gets ``-1``),
so the links already written in the markdown still resolve.
"""

from __future__ import annotations

import html
import posixpath
import re
import shutil
from pathlib import Path

import markdown

from flymsg import viz

ROOT = Path(__file__).resolve().parents[2]
REPO = "https://github.com/gianlucamazza/flymsg"
BLOB = f"{REPO}/blob/main"

# Copied into the Pages output next to the HTML; everything else is a blob link.
_SITE_PREFIXES = ("docs/img/", "docs/live/")

# (output stem, source path, nav label). Order is the site nav.
PAGES = (
    ("index", "README.md", "Overview"),
    ("data", "docs/reference/data.md", "Data"),
    ("architecture", "docs/architecture.md", "Architecture"),
    ("adr-module-boundaries", "docs/adr-module-boundaries.md", "Module boundaries ADR"),
    ("catalog", "docs/catalog.md", "Documentation catalog"),
    ("model", "docs/model.md", "Model"),
    ("embodiment", "docs/embodiment.md", "Embodiment"),
    ("eye", "docs/reference/eye.md", "Eye"),
    ("runtime", "docs/runtime.md", "Runtime"),
    ("validation", "docs/validation.md", "Validation"),
    ("benchmarks", "docs/result/benchmarks.md", "Benchmarks"),
    ("m4-v2-proposal", "docs/plan/m4-v2-proposal.md", "M4 v2 proposal"),
    ("baker-crossmatch", "docs/baker-crossmatch.md", "Baker correspondence"),
    (
        "jo-measured-input-design",
        "docs/jo-measured-input-design.md",
        "Measured JO input",
    ),
    ("adr-measured-jo-input", "docs/adr-measured-jo-input.md", "Measured JO ADR"),
    ("behavior", "docs/result/behavior.md", "Behavior"),
    ("nulls", "docs/nulls.md", "Nulls"),
    ("provenance", "docs/reference/provenance.md", "Provenance"),
    ("comparison", "docs/result/comparison.md", "Comparison"),
    ("dimorphism", "docs/result/dimorphism.md", "Dimorphism"),
    ("dn-arena", "docs/result/dn-arena.md", "DN arena"),
    ("related", "docs/reference/related.md", "Related"),
    ("viz", "docs/reference/viz.md", "3D view"),
    ("vee-qualification", "docs/plan/vee-qualification.md", "VEE qualification"),
    ("issue-resolution", "docs/report/issue-resolution.md", "Issue resolution"),
    ("observer-rendering", "docs/report/observer-rendering.md", "Observer rendering"),
    (
        "quest-paged-pipeline",
        "docs/report/quest-paged-pipeline.md",
        "GPU page candidate",
    ),
    (
        "quest-rendering-diagnosis",
        "docs/report/quest-rendering-diagnosis.md",
        "Quest diagnosis",
    ),
    ("adr-observer-rendering", "docs/adr-observer-rendering.md", "Rendering ADR"),
    (
        "adr-exact-observer-performance",
        "docs/adr-exact-observer-performance.md",
        "Exact fidelity ADR",
    ),
    (
        "quest-exact-performance",
        "docs/report/quest-exact-performance.md",
        "Exact Quest work",
    ),
    ("quest-wifi-trials", "docs/plan/quest-wifi-trials.md", "Quest Wi-Fi protocol"),
    ("milestones", "docs/plan/milestones.md", "Milestones"),
    ("roadmap", "docs/roadmap.md", "Roadmap"),
    ("approximations", "docs/reference/approximations.md", "Approximations"),
    ("leads", "docs/leads.md", "Leads"),
    ("scientific-fidelity", "docs/plan/scientific-fidelity.md", "Scientific fidelity"),
    ("replication", "docs/replication.md", "Replication"),
    (
        "sensorimotor-environment-plan",
        "docs/plan/sensorimotor-environment-plan.md",
        "Sensorimotor plan",
    ),
    (
        "integrity-audit",
        "docs/report/integrity-audit-2026-10-13.md",
        "Integrity audit",
    ),
    ("adr-gap-refractory", "docs/adr-gap-refractory.md", "Electrical ADR"),
    ("adr-run-integrity", "docs/adr-run-integrity.md", "Run integrity ADR"),
    (
        "adr-virtual-experimental-environment",
        "docs/adr-virtual-experimental-environment.md",
        "WebXR ADR",
    ),
    ("adr-body-wiring", "docs/adr-body-wiring.md", "Body wiring ADR"),
    ("run-integrity", "docs/reference/run-integrity.md", "Run integrity"),
    ("changelog", "CHANGELOG.md", "Changelog"),
)

# Repo-relative source path → built page. Stems stay stable when sources move later.
_PAGE_HTML = {rel: f"{stem}.html" for stem, rel, _ in PAGES}
# Old top-level docs/ landing paths keep resolving after a category move.
_MOVED = [(stem, rel) for stem, rel, _ in PAGES if rel.count("/") > 1]
_OLD_HTML = {f"docs/{Path(rel).name}": f"{stem}.html" for stem, rel in _MOVED}
if len(_OLD_HTML) != len(_MOVED) or _OLD_HTML.keys() & _PAGE_HTML.keys():
    raise RuntimeError("an old landing path collides with another page")
_PAGE_HTML.update(_OLD_HTML)

_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")
_ATTR = re.compile(r'\b(href|src)="([^"]*)"')
_HEADING = re.compile(r"<h([1-6])>(.*?)</h\1>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")

_MD = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])


def slugify(text: str) -> str:
    """GitHub's heading anchor for ``text`` (no duplicate suffix)."""
    text = html.unescape(text).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", "-", text)


def _ids(body: str) -> str:
    seen: dict[str, int] = {}

    def one(match: re.Match[str]) -> str:
        level, inner = match.group(1), match.group(2)
        plain = _TAG.sub("", inner)
        base = slugify(plain)
        n = seen.get(base, 0)
        seen[base] = n + 1
        anchor = base if n == 0 else f"{base}-{n}"
        return f'<h{level} id="{anchor}">{inner}</h{level}>'

    return _HEADING.sub(one, body)


def rewrite(url: str, *, source: str) -> str:
    """Resolve ``url`` against the Markdown source path, then retarget for Pages.

    Links stay written relative to the source tree (``adr-dn-arena.md``,
    ``../validation/x.yaml``). Built pages become ``stem.html``; ``docs/img`` and
    ``docs/live`` stay site-relative; everything else becomes a GitHub blob URL.
    """
    if url.startswith(("http://", "https://", "mailto:", "#")):
        return url
    path, _, frag = url.partition("#")
    suffix = f"#{frag}" if frag else ""
    if not path:
        return suffix
    base = Path(source).parent.as_posix()
    resolved = posixpath.normpath(path if base in ("", ".") else f"{base}/{path}")
    if resolved.startswith("../") or resolved == "..":
        return url
    if resolved in _PAGE_HTML:
        return _PAGE_HTML[resolved] + suffix
    if resolved.startswith(_SITE_PREFIXES):
        return resolved.removeprefix("docs/") + suffix
    return f"{BLOB}/{resolved}" + suffix


def _rewrite_attrs(body: str, *, source: str) -> str:
    return _ATTR.sub(
        lambda m: f'{m.group(1)}="{rewrite(m.group(2), source=source)}"',
        body,
    )


def render(text: str, *, source: str) -> str:
    text = _AUTOLINK.sub(r"[\1](\1)", text)
    _MD.reset()
    return _rewrite_attrs(_ids(_MD.convert(text)), source=source)


def _page(stem: str, body: str, title: str) -> str:
    links = "\n".join(
        f'<a href="{name}.html"'
        f"{' aria-current="page"' if name == stem else ''}>{label}</a>"
        for name, _, label in PAGES
    )
    # index is served as index.html; the nav href index.html is correct there too.
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#1c1916">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
<p class="name"><a href="index.html">flymsg</a></p>
<nav>{links}</nav>
<p class="repo"><a href="{REPO}">source</a></p>
</header>
<main>
{body}
</main>
</body>
</html>
"""


def _title(body: str, label: str) -> str:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.DOTALL)
    if not match:
        return label
    return _TAG.sub("", match.group(1)).strip() or label


def build(out: Path, root: Path = ROOT) -> None:
    """Replace ``out`` with the site. ``root`` is the flymsg checkout."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copy(Path(__file__).with_name("pages.css"), out / "style.css")
    img = root / "docs" / "img"
    if img.is_dir():
        shutil.copytree(img, out / "img")
    live = root / "docs" / "live"
    for scene in sorted(live.iterdir()) if live.is_dir() else ():
        dst = out / "live" / scene.name
        shutil.copytree(scene, dst)
        if (scene / "scene.json").is_file():  # cns/ holds shared layers, not a scene
            viz.copy_page(dst)
    for stem, rel, label in PAGES:
        body = render((root / rel).read_text(encoding="utf-8"), source=rel)
        heading = _title(body, label)
        title = "flymsg" if stem == "index" else f"{heading} — flymsg"
        (out / f"{stem}.html").write_text(_page(stem, body, title), encoding="utf-8")
