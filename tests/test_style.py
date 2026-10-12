"""The code carries no lint or formatter suppressions: it is written to pass as is."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPRESSION = re.compile(
    r"#\s*(noqa|fmt:\s*(skip|off|on)|type:\s*ignore|pragma:\s*no\s*cover)"
    r"|eslint-disable|prettier-ignore"
)


def test_no_suppressions():
    files = [
        p
        for d in ("src", "tests", "scripts")
        for p in (ROOT / d).rglob("*")
        if p.suffix in (".py", ".js", ".mjs")
        and "vendor" not in p.parts
        and p.name != "test_style.py"
    ]
    hits = [
        f"{p.relative_to(ROOT)}:{i}"
        for p in files
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if SUPPRESSION.search(line)
    ]
    assert not hits, hits
