import re
from html.parser import HTMLParser
from pathlib import Path

from flymsg.pages import BLOB, build, rewrite, slugify

ROOT = Path(__file__).resolve().parents[1]

_MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def test_slugs_match_the_anchors_already_used_in_the_docs():
    assert slugify("Findings log") == "findings-log"
    assert slugify("Compaction (`flymsg build`)") == "compaction-flymsg-build"
    assert (
        slugify("Reconstruction completeness (`flymsg audit`, `runs/audit.txt`)")
        == "reconstruction-completeness-flymsg-audit-runsaudittxt"
    )
    assert (
        slugify("Female brain: FlyWire FAFB v783 (`--dataset fafb`)")
        == "female-brain-flywire-fafb-v783---dataset-fafb"
    )
    assert (
        slugify("N1 — specific checks need the measured partners")
        == "n1-specific-checks-need-the-measured-partners"
    )


def test_rewrite_maps_source_paths_to_pages_assets_or_blob():
    assert rewrite("validation.md", source="docs/architecture.md") == "validation.html"
    assert rewrite("docs/validation.md", source="README.md") == "validation.html"
    assert (
        rewrite("../validation/preregistration.yaml", source="docs/validation.md")
        == f"{BLOB}/validation/preregistration.yaml"
    )
    assert rewrite("LICENSE", source="README.md") == f"{BLOB}/LICENSE"
    assert rewrite("img/replay.png", source="docs/validation.md") == "img/replay.png"
    assert rewrite("docs/img/replay.png", source="README.md") == "img/replay.png"


def test_rewrite_keeps_fragments():
    assert (
        rewrite("validation.md#protocol", source="docs/architecture.md")
        == "validation.html#protocol"
    )
    assert (
        rewrite("docs/validation.md#findings-log", source="README.md")
        == "validation.html#findings-log"
    )
    assert (
        rewrite("adr-dn-arena.md#decision", source="docs/catalog.md")
        == f"{BLOB}/docs/adr-dn-arena.md#decision"
    )


def test_rewrite_keeps_old_landing_paths_after_category_move():
    assert rewrite("milestones.md", source="docs/catalog.md") == "milestones.html"
    assert rewrite("plan/milestones.md", source="docs/catalog.md") == "milestones.html"
    assert rewrite("docs/milestones.md", source="README.md") == "milestones.html"
    assert rewrite("docs/plan/milestones.md", source="README.md") == "milestones.html"
    assert (
        rewrite("../roadmap.md#completion-plan", source="docs/plan/milestones.md")
        == "roadmap.html#completion-plan"
    )
    assert rewrite("issue-resolution.md", source="docs/catalog.md") == (
        "issue-resolution.html"
    )
    assert rewrite("report/issue-resolution.md", source="docs/catalog.md") == (
        "issue-resolution.html"
    )
    assert rewrite("docs/issue-resolution.md", source="README.md") == (
        "issue-resolution.html"
    )
    assert rewrite("docs/report/issue-resolution.md", source="README.md") == (
        "issue-resolution.html"
    )
    assert (
        rewrite(
            "../validation.md#protocol",
            source="docs/report/issue-resolution.md",
        )
        == "validation.html#protocol"
    )
    assert rewrite("data.md", source="docs/catalog.md") == "data.html"
    assert rewrite("reference/data.md", source="docs/catalog.md") == "data.html"
    assert rewrite("docs/data.md", source="README.md") == "data.html"
    assert rewrite("docs/reference/data.md", source="README.md") == "data.html"
    assert (
        rewrite("../model.md#lif", source="docs/reference/data.md") == "model.html#lif"
    )
    assert rewrite("benchmarks.md", source="docs/catalog.md") == "benchmarks.html"
    assert (
        rewrite("result/benchmarks.md", source="docs/catalog.md") == "benchmarks.html"
    )
    assert rewrite("docs/benchmarks.md", source="README.md") == "benchmarks.html"
    assert rewrite("docs/result/benchmarks.md", source="README.md") == "benchmarks.html"
    assert (
        rewrite("../validation.md#findings-log", source="docs/result/comparison.md")
        == "validation.html#findings-log"
    )
    assert (
        rewrite("../img/looming-jump.svg", source="docs/result/behavior.md")
        == "img/looming-jump.svg"
    )


def test_rewrite_sends_unlisted_docs_to_the_blob():
    assert (
        rewrite("adr-dn-arena.md", source="docs/catalog.md")
        == f"{BLOB}/docs/adr-dn-arena.md"
    )
    assert rewrite("reference/claims.md", source="docs/catalog.md") == (
        f"{BLOB}/docs/reference/claims.md"
    )


def test_rewrite_resolves_images_and_evidence():
    assert rewrite("img/kc-sparseness.svg", source="docs/model.md") == (
        "img/kc-sparseness.svg"
    )
    evidence = "../evidence/quest2-qualification-2026-10-16.json"
    assert rewrite(evidence, source="docs/report/quest-paged-pipeline.md") == (
        f"{BLOB}/docs/evidence/quest2-qualification-2026-10-16.json"
    )


def test_all_markdown_relative_links_in_docs_resolve():
    broken: list[str] = []
    for md in sorted((ROOT / "docs").rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        for match in _MD_LINK.finditer(text):
            url = match.group(1)
            if url.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path, _, _ = url.partition("#")
            if not path:
                continue
            target = (md.parent / path).resolve()
            try:
                target.relative_to(ROOT)
            except ValueError:
                broken.append(f"{md.relative_to(ROOT)} → {url} (escapes repo)")
                continue
            if not target.exists():
                broken.append(f"{md.relative_to(ROOT)} → {url}")
    assert broken == []


class _Refs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.refs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        got = dict(attrs)
        if (id_ := got.get("id")) is not None:
            self.ids.add(id_)
        for key in ("href", "src"):
            if key in got and got[key] is not None:
                self.refs.append((key, got[key]))


def test_built_site_resolves_its_own_links(tmp_path: Path):
    build(tmp_path, ROOT)
    pages = list(tmp_path.glob("*.html"))
    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "img" / "replay.png").is_file()
    ids_of = {}
    for page in pages:
        parser = _Refs()
        parser.feed(page.read_text(encoding="utf-8"))
        ids_of[page.name] = parser.ids
        for kind, url in parser.refs:
            if url.startswith(("http://", "https://", "mailto:", "#")):
                if url.startswith("#"):
                    assert url[1:] in parser.ids, f"{page.name} missing {url}"
                continue
            path, _, frag = url.partition("#")
            target = tmp_path / path
            assert target.is_file(), f"{page.name} {kind} {url}"
            if frag:
                assert frag in _ids(target), f"{page.name} → {url}"
    for name in ("looming", "song", "anatomy"):
        scene = tmp_path / "live" / name
        assert (scene / "index.html").is_file(), name
        assert (scene / "scene.json").is_file(), name
        assert (scene / "vendor").is_dir(), name
    # The documentation table's deep links are the ones that have to survive.
    validation = ids_of["validation.html"]
    assert {"findings-log", "protocol", "references"} <= validation


def _ids(path: Path) -> set[str]:
    return set(re.findall(r'\bid="([^"]*)"', path.read_text(encoding="utf-8")))
