"""Gate vee1-1 (ADR Decision 3): hash the locked T4/T5 protocol's sim.run arguments.

One JSON object per configuration (``config``, ``dark_calls``, ``stimulus``), then
``{"digest": ...}``, the sha256 of those lines joined by newlines. Imports only
``flymsg.t4t5``, ``flymsg.sim`` and ``flymsg.data`` names that exist before and
after the visual-pathway extraction, so the same file runs on both commits.

Each configuration is a deep copy of the locked document whose version-4 envelope
lists hold that configuration alone. Directions and polarities stay, so the lit
photoreceptors match the full protocol. Dark passes (kicks all zero, settle
length, one column, float32) call the real ``sim.run``. The first stimulus call
is hashed and aborted.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np

from flymsg import data, sim, t4t5


class _Stimulus(Exception):
    """The first stimulus call of a configuration; carries its argument hash."""

    def __init__(self, digest: str) -> None:
        super().__init__(digest)
        self.digest = digest


def _feed(h, blob: bytes) -> None:
    h.update(np.uint64(len(blob)).tobytes())
    h.update(blob)


def _feed_array(h, a: np.ndarray) -> None:
    a = np.ascontiguousarray(a)
    _feed(h, a.dtype.str.encode("ascii"))
    _feed(h, np.asarray(a.shape, dtype=np.int64).tobytes())
    _feed(h, a.tobytes())


def _feed_graded(h, graded) -> None:
    if graded is None:
        _feed(h, b"")
        return
    for name in ("idx", "v_lo", "span", "rate_hz"):
        _feed_array(h, getattr(graded, name))


def _feed_membrane(h, membrane) -> None:
    if membrane is None:
        _feed(h, b"")
        return
    for name in ("idx", "tau_m", "tau_syn", "v_rest", "v_th"):
        _feed_array(h, getattr(membrane, name))


def _call_hash(arg: dict) -> str:
    """sha256 of one sim.run call.

    Order: W shape, W.data, W.indices, W.indptr; stim; duration_ms; each Params
    field (name, float64); seed; kicks; graded idx, v_lo, span, rate_hz; membrane
    idx, tau_m, tau_syn, v_rest, v_th. Arrays carry dtype.str, shape and bytes.
    """
    h = hashlib.sha256()
    W = arg["W"].tocsc()
    _feed(h, np.asarray(W.shape, dtype=np.int64).tobytes())
    for part in (W.data, W.indices, W.indptr):
        _feed_array(h, part)
    _feed_array(h, np.asarray(arg["stim"]))
    _feed(h, np.float64(arg["duration_ms"]).tobytes())
    p = arg["p"]
    if p is None:
        _feed(h, b"")
    else:
        for field in dataclasses.fields(p):
            _feed(h, field.name.encode("ascii"))
            _feed(h, np.float64(getattr(p, field.name)).tobytes())
    _feed(h, np.int64(arg["seed"]).tobytes())
    kicks = arg["kicks"]
    if kicks is None:
        _feed(h, b"")
    else:
        _feed_array(h, np.asarray(kicks))
    _feed_graded(h, arg["graded"])
    _feed_membrane(h, arg["membrane"])
    return h.hexdigest()


def _is_dark(kicks, settle_steps: int) -> bool:
    if kicks is None:
        return False
    k = np.asarray(kicks)
    return (
        k.shape == (settle_steps, 1) and k.dtype == np.float32 and bool(np.all(k == 0))
    )


def _chosen(grid: list[dict], text: str | None) -> list[dict]:
    if text is None:
        return grid
    want = [int(part) for part in text.split(",") if part.strip() != ""]
    found = {cfg["config"]: cfg for cfg in grid}
    missing = [i for i in want if i not in found]
    if missing:
        raise SystemExit(f"unknown configuration(s): {missing}")
    return [found[i] for i in want]


def _isolate(doc: dict, cfg: dict) -> dict:
    """One version-4 configuration; every direction and polarity kept."""
    reduced = copy.deepcopy(doc)
    env = reduced["protocol"]["envelope"]
    for key in ("lamina_medulla_gain", "lmc_rate_hz", "medulla_rate_hz"):
        env[key] = [cfg[key]]
    got = t4t5.configurations(reduced)
    same = len(got) == 1 and all(
        got[0][k] == v for k, v in cfg.items() if k != "config"
    )
    if not same:
        raise SystemExit(
            f"configuration {cfg['config']} cannot be isolated in the locked document"
        )
    return reduced


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--configs",
        default=None,
        help="comma-separated configuration indices (default: every configuration)",
    )
    args = parser.parse_args(argv)
    doc = t4t5.assert_matches_code()
    grid = _chosen(t4t5.configurations(doc), args.configs)
    neurons, edges = data.load(args.data_dir)
    settle_steps = round(doc["protocol"]["settle_ms"] / sim.Params().dt)
    real = sim.run
    dark_calls: list[str] = []

    def wrapped(*pos, **kw):
        bound = inspect.signature(real).bind(*pos, **kw)
        bound.apply_defaults()
        digest = _call_hash(bound.arguments)
        if _is_dark(bound.arguments["kicks"], settle_steps):
            dark_calls.append(digest)
            return real(*pos, **kw)
        raise _Stimulus(digest)

    sim.run = wrapped
    lines: list[str] = []
    try:
        if t4t5.sim.run is not wrapped:
            raise SystemExit("t4t5.sim.run is not flymsg.sim.run")
        for cfg in grid:
            dark_calls.clear()
            try:
                t4t5.run(neurons, edges, args.data_dir, doc=_isolate(doc, cfg))
            except _Stimulus as caught:
                stimulus = caught.digest
            else:
                raise SystemExit(f"configuration {cfg['config']} made no stimulus call")
            line = json.dumps(
                {
                    "config": cfg["config"],
                    "dark_calls": list(dark_calls),
                    "stimulus": stimulus,
                },
                separators=(",", ":"),
            )
            print(line, flush=True)
            lines.append(line)
    finally:
        sim.run = real
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    print(json.dumps({"digest": digest}, separators=(",", ":")))


if __name__ == "__main__":
    main()
