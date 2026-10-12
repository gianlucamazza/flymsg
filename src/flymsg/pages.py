"""Build the GitHub Pages site from the README and the docs.

Pages sit next to each other: the README is ``index.html``, ``docs/validation.md``
is ``validation.html``. Heading anchors follow GitHub's rule (punctuation other
than hyphens drops out, spaces become hyphens, a repeated heading gets ``-1``),
so the links already written in the markdown still resolve.
"""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

import markdown

from flymsg import viz

ROOT = Path(__file__).resolve().parents[2]
REPO = "https://github.com/gianlucamazza/flymsg"
BLOB = f"{REPO}/blob/main"

# Files that are not prose pages. The site links to them on GitHub.
EXTERNAL = {
    "LICENSE": f"{BLOB}/LICENSE",
    "NOTICE": f"{BLOB}/NOTICE",
    "CITATION.cff": f"{BLOB}/CITATION.cff",
    "validation/preregistration.yaml": f"{BLOB}/validation/preregistration.yaml",
    "../validation/preregistration.yaml": f"{BLOB}/validation/preregistration.yaml",
    "validation/benchmarks.yaml": f"{BLOB}/validation/benchmarks.yaml",
    "../validation/benchmarks.yaml": f"{BLOB}/validation/benchmarks.yaml",
    "validation/behavior.yaml": f"{BLOB}/validation/behavior.yaml",
    "../validation/behavior.yaml": f"{BLOB}/validation/behavior.yaml",
    "validation/motor_map.yaml": f"{BLOB}/validation/motor_map.yaml",
    "../validation/motor_map.yaml": f"{BLOB}/validation/motor_map.yaml",
    "validation/silence_scan.yaml": f"{BLOB}/validation/silence_scan.yaml",
    "../validation/silence_scan.yaml": f"{BLOB}/validation/silence_scan.yaml",
}

# (output stem, source path, nav label). Order is the site nav.
PAGES = (
    ("index", "README.md", "Overview"),
    ("data", "docs/data.md", "Data"),
    ("model", "docs/model.md", "Model"),
    ("embodiment", "docs/embodiment.md", "Embodiment M0"),
    ("runtime", "docs/runtime.md", "Runtime"),
    ("validation", "docs/validation.md", "Validation"),
    ("benchmarks", "docs/benchmarks.md", "Benchmarks"),
    ("behavior", "docs/behavior.md", "Behavior"),
    ("nulls", "docs/nulls.md", "Nulls"),
    ("provenance", "docs/provenance.md", "Provenance"),
    ("comparison", "docs/comparison.md", "Comparison"),
    ("dimorphism", "docs/dimorphism.md", "Dimorphism"),
    ("related", "docs/related.md", "Related"),
    ("viz", "docs/viz.md", "3D view"),
    ("changelog", "CHANGELOG.md", "Changelog"),
)

# Markdown file name → built page. README.md and CHANGELOG.md differ in case from the stem.
_HTML = {Path(rel).name: f"{stem}.html" for stem, rel, _ in PAGES}

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


def rewrite(url: str) -> str:
    """Point a markdown URL at a built page, an image, or the GitHub blob."""
    if url.startswith(("http://", "https://", "mailto:", "#")):
        return url
    path, _, frag = url.partition("#")
    if path in EXTERNAL:
        return EXTERNAL[path]
    if path.startswith("docs/"):
        path = path.removeprefix("docs/")
    path = _HTML.get(path, path)
    return path + (f"#{frag}" if frag else "")


def _rewrite_attrs(body: str) -> str:
    return _ATTR.sub(lambda m: f'{m.group(1)}="{rewrite(m.group(2))}"', body)


def render(source: str) -> str:
    text = _AUTOLINK.sub(r"[\1](\1)", source)
    _MD.reset()
    return _rewrite_attrs(_ids(_MD.convert(text)))


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
        viz.copy_page(dst)
    for stem, rel, label in PAGES:
        body = render((root / rel).read_text(encoding="utf-8"))
        heading = _title(body, label)
        title = "flymsg" if stem == "index" else f"{heading} — flymsg"
        (out / f"{stem}.html").write_text(_page(stem, body, title), encoding="utf-8")
