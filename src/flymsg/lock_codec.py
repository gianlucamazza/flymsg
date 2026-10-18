"""Restricted YAML parsing and canonical content identity for lock files."""

from __future__ import annotations

import hashlib
import json

SKIP_HASH_KEYS = frozenset({"version", "content_sha256"})


class PreregistrationError(ValueError):
    """A confirmatory run or the live code drifted from the locked file."""

    # Preserve the historical exception path, including pickled exceptions.
    __module__ = "flymsg.prereg"


def _parse_scalar(text: str):
    text = text.strip()
    if text in ("true", "True"):
        return True
    if text in ("false", "False"):
        return False
    if text in ("null", "None", "~"):
        return None
    if _is_quoted(text):
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in _split_top(inner, ",")]
    try:
        if any(ch in text for ch in ".eE"):
            return float(text)
        return int(text)
    except ValueError:
        return text


def _split_top(text: str, sep: str) -> list[str]:
    parts, buf, depth, quote = [], [], 0, None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch in "[":
            depth += 1
        elif ch in "]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf or parts:
        parts.append("".join(buf))
    return parts


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _opens_scalar(before: str) -> bool:
    """A quote opens a quoted scalar only where a value starts."""
    head = before.rstrip()
    return head == "" or head[-1] in ":-[,"


def _strip_comment(raw: str) -> str:
    """Cut a ` #` comment that starts outside quotes (no escapes in the subset)."""
    quote = None
    for i, ch in enumerate(raw):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'" and _opens_scalar(raw[:i]):
            quote = ch
        elif ch == "#" and i > 0 and raw[i - 1] == " ":
            return raw[:i]
    return raw


def _is_quoted(text: str) -> bool:
    return len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'"


def _one_quoted(text: str) -> bool:
    """The whole text is one quoted string: its quote does not close earlier."""
    return _is_quoted(text) and text[0] not in text[1:-1]


def _subset(text: str) -> int:
    for raw in text.splitlines():
        if raw.startswith("yaml_subset:"):
            value = _parse_scalar(_strip_comment(raw).partition(":")[2])
            if value != 2:
                raise PreregistrationError(f"unknown yaml_subset {value!r}")
            return 2
    return 1


def load_yaml(text: str) -> dict:
    """Load the restricted YAML subset used by the preregistration file.

    Subset 1 cuts ` #` even inside quotes and reads a quoted list item holding `:` as a
    one-key map (#159); registered locks keep it, since their hashes were taken on it. A
    file with the top-level key `yaml_subset: 2` gets quote-aware comments and quoted
    list items as plain strings, and refuses a repeated key.
    """
    subset = _subset(text)
    lines = []
    for raw in text.splitlines():
        cut = (_strip_comment(raw) if subset == 2 else raw.split(" #", 1)[0]).rstrip()
        if not cut.strip() or cut.lstrip().startswith("#"):
            continue
        lines.append(cut)

    def parse_block(index: int, indent: int):
        mapping, sequence = {}, []
        kind = None
        while index < len(lines):
            line = lines[index]
            level = _indent(line)
            if level < indent:
                break
            if level > indent:
                raise PreregistrationError(f"unexpected indent: {line!r}")
            body = line[level:]
            if body.startswith("- "):
                if kind == "map":
                    raise PreregistrationError("mixed map and list")
                kind = "list"
                item = body[2:].strip()
                index += 1
                quoted = subset == 2 and _one_quoted(item)
                if subset == 2 and item.startswith(('"', "'")) and not quoted:
                    raise PreregistrationError(f"not one quoted string: {item!r}")
                if item and ":" in item and not item.startswith("[") and not quoted:
                    key, _, rest = item.partition(":")
                    nested, index = parse_block(index, indent + 2)
                    nested = {key.strip(): _parse_scalar(rest), **nested}
                    sequence.append(nested)
                elif item:
                    sequence.append(_parse_scalar(item))
                else:
                    value, index = parse_block(index, indent + 2)
                    sequence.append(value)
                continue
            if kind == "list":
                break
            kind = "map"
            key, _, rest = body.partition(":")
            rest = rest.strip()
            index += 1
            if subset == 2 and key in mapping:
                raise PreregistrationError(f"duplicate key {key!r}")
            if rest:
                mapping[key] = _parse_scalar(rest)
            else:
                mapping[key], index = parse_block(index, indent + 2)
        if kind == "list":
            return sequence, index
        return mapping, index

    doc, end = parse_block(0, 0)
    if end != len(lines):
        raise PreregistrationError("unparsed preregistration lines")
    if not isinstance(doc, dict):
        raise PreregistrationError("preregistration root must be a mapping")
    return doc


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_payload(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in SKIP_HASH_KEYS}


def content_hash(doc: dict) -> str:
    return hashlib.sha256(canonical(content_payload(doc)).encode()).hexdigest()
