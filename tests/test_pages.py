import re
from html.parser import HTMLParser
from pathlib import Path

from flymsg.pages import build, slugify

ROOT = Path(__file__).resolve().parents[1]


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
    # The documentation table's deep links are the ones that have to survive.
    validation = ids_of["validation.html"]
    assert {"findings-log", "protocol", "references"} <= validation


def _ids(path: Path) -> set[str]:
    return set(re.findall(r'\bid="([^"]*)"', path.read_text(encoding="utf-8")))
