"""Versioned, bounded fixtures for the native ordered LIF executor."""

import struct
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from flymsg import sim
from flymsg.runtime import CpuRuntime

MAGIC = 0x314E4D46  # FMN1, little endian
OUTPUT = 0x314F4D46  # FMO1
COUNTS = 0x31534D46  # FMS1: sparse counts and first spikes
HEADER_WORDS = 40
MAX_BYTES = 512 * 1024 * 1024


class NativeCapabilityError(ValueError):
    """A numerical mode has no qualified native implementation."""


def edge_chunks(runtime: CpuRuntime) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Incoming edges as the fixture stores them: row pointers, sources (stable by
    source, then original CSC position) and weights. The costly part of an export on a
    whole connectome; a batch computes it once for its network."""
    n = runtime._n
    sources = np.repeat(np.arange(n), np.diff(runtime._indptr))
    order = np.argsort(runtime._indices, kind="stable")
    counts = np.bincount(runtime._indices, minlength=n)
    return (
        np.r_[0, np.cumsum(counts)].astype("<u4"),
        sources[order].astype("<u4"),
        runtime._data[order].astype("<f4"),
    )


def export_fixture(
    runtime: CpuRuntime,
    path: Path,
    edges: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
) -> dict:
    """Export a fresh initialized CPU runtime; scientific authority stays Python.
    See `fixture_bytes`."""
    raw, meta = fixture_bytes(runtime, edges)
    Path(path).write_bytes(raw)
    return meta


def fixture_bytes(
    runtime: CpuRuntime,
    edges: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
) -> tuple[bytes, dict]:
    """A fresh initialized CPU runtime's fixture, in memory, and its description.

    This qualification format is intentionally separate from the run manifest.
    Kicks are converted to double counts, matching the kernel's kick arithmetic.
    `edges` is `edge_chunks(runtime)` when the caller already has it.
    """
    if runtime.step != 0:
        raise ValueError("native fixtures require fresh state")
    coupled = runtime._gap[0]
    never_refractory = runtime._graded[-1] | runtime._silent | runtime._is_stim
    if (
        coupled.size
        and runtime._electrical_mode == "continuous"
        and runtime._ref_steps > 1
        and not never_refractory[coupled].all()
    ):
        # The native fixed map is equivalent only when the refractory mask is always
        # empty. Do not export a dynamic clamp as the older boundary-reset model.
        raise NativeCapabilityError(
            "native continuous-clamp electrical coupling with refractory cells is unqualified"
        )
    if runtime._membrane is not None:
        # the fixture header carries one set of membrane constants
        raise NativeCapabilityError(
            "native per-neuron membrane parameters are unqualified"
        )
    if np.any(runtime._kicks > 2**53):
        raise ValueError("native double-count fixtures require counts <= 2**53")
    n, steps, d = runtime._n, runtime._steps, runtime._d
    header = np.zeros(HEADER_WORDS, dtype="<u4")
    g_idx, g_lo, g_span, g_scale, _ = runtime._graded
    gap_nodes, gap_off, gap_mat, gap_moff, _, gap_width, gap_amp = runtime._gap
    extended = bool(g_idx.size or gap_nodes.size)
    header[:9] = [
        MAGIC,
        2 if extended else 1,
        n,
        steps,
        runtime._per_bin,
        d,
        runtime._ref_steps,
        runtime._stim.size,
        runtime._trace.size,
    ]
    header[9:16] = np.asarray(runtime._constants, dtype="<f4").view("<u4")
    chunks = []
    cursor = HEADER_WORDS

    def add(slot, values, dtype="<u4"):
        nonlocal cursor
        raw = np.asarray(values, dtype=dtype).tobytes()
        header[slot] = cursor
        chunks.append(raw)
        cursor += len(raw) // 4

    # Incoming edges, stable by source then original CSC edge position.
    ptr, sources, weights = edge_chunks(runtime) if edges is None else edges
    add(16, ptr)
    add(17, sources)
    add(18, weights, "<f4")
    add(19, runtime._is_stim)
    add(20, runtime._silent)
    add(21, runtime._jump, "<f4")
    add(22, runtime._trace_col, "<i4")
    stimulus_col = np.full(n, -1, dtype=np.int32)
    stimulus_col[runtime._stim] = np.arange(runtime._stim.size)
    add(23, stimulus_col, "<i4")
    add(24, runtime._kicks, "<f8")
    state_cursor = 0
    sizes = [
        n,
        n,
        n,
        n,
        d * n,
        steps // runtime._per_bin * n,
        n,
        steps * runtime._trace.size,
        n,
    ]
    for slot, size in zip(range(25, 34), sizes, strict=True):
        header[slot] = state_cursor
        state_cursor += size
    if extended:
        # version 2: graded neurons and electrically coupled groups (see native/lif.h)
        ng, nc, ncomp = g_idx.size, gap_nodes.size, gap_off.size - 1
        header[37], header[38] = cursor, state_cursor
        graded_col = np.full(n, -1, dtype=np.int32)
        graded_col[g_idx] = np.arange(ng)
        gap_pos = np.full(n, -1, dtype=np.int32)
        gap_pos[gap_nodes] = np.arange(nc)
        ext = np.array([ng, nc, ncomp, gap_mat.size, gap_width], dtype="<u4")
        chunks.append(ext.tobytes())
        cursor += ext.size
        for values, dtype in (
            (graded_col, "<i4"),
            (g_lo, "<f4"),
            (g_span, "<f4"),
            (g_scale, "<f4"),
            (gap_pos, "<i4"),
            (gap_nodes, "<u4"),
            (gap_off, "<u4"),
            (gap_moff, "<u4"),
            (gap_mat, "<f8"),
            (gap_amp, "<f8"),
        ):
            raw = np.asarray(values, dtype=dtype).tobytes()
            chunks.append(raw)
            cursor += len(raw) // 4
        bins = steps // runtime._per_bin
        # graded release ring, release of this step, voltage sums (f64), gap buffer, steps
        # left of each coupled neuron's spike term
        state_cursor += d * ng + ng + 2 * bins * ng + nc + nc
    header[34:37] = [cursor, state_cursor, len(sources)]
    if (cursor + state_cursor) * 4 > MAX_BYTES:
        raise ValueError("fixture exceeds native qualification memory cap")
    return header.tobytes() + b"".join(chunks), {
        "schema": f"flymsg.native_fixture/v{2 if extended else 1}",
        "input_bytes": cursor * 4,
        "state_bytes": state_cursor * 4,
        "precision": "ordered-f32-double-kicks",
        "steps": steps,
    }


BATCH = 0x314E4246  # FBN1: several runs of one network


def export_batch(runtimes: Iterable[CpuRuntime], base: Path, batch: Path) -> list[dict]:
    """Export runs that share one network (the same W, parameters, horizon and
    recording) as one base fixture and a batch of exact patches, so a worker uploads the
    network once.

    A version-1 fixture ends with its kicks (slot 24); every word before them is the
    network or a per-neuron mask. Each run's patch lists the words before the kicks that
    differ from the base (stimulated rows, their threshold jumps and columns, the
    stimulus count and the input size) and then the run's own kicks. The patch rebuilds
    that run's fixture word for word, which is checked here before anything is written.
    Runs are exported one at a time, so memory holds the base and one run, not all;
    `runtimes` may be a generator that builds each run when it is asked for.
    """
    metas, parts, first, cut = [], [], None, 0
    edges = net = None
    # no enumerate: it would hold the previous run while the next one is built
    for rt in runtimes:
        k = len(metas)
        if net is None:
            edges, net = edge_chunks(rt), rt
        same = all(
            np.array_equal(getattr(rt, a), getattr(net, a))
            for a in ("_indptr", "_indices", "_data")
        )
        # the edges are the network's: computed once, reused while it is the same
        raw, meta = fixture_bytes(rt, edges if same else None)
        metas.append(meta)
        del rt
        w = np.frombuffer(raw, dtype="<u4")
        if first is None:
            if int(w[1]) != 1:
                raise NativeCapabilityError("batches cover version-1 fixtures only")
            first, cut = w.copy(), int(w[24])  # the kicks start at `cut`
        if int(w[1]) != 1 or int(w[24]) != cut:
            raise ValueError(f"run {k} does not share the base's network layout")
        changed = np.flatnonzero(w[:cut] != first[:cut]).astype("<u4")
        kicks = w[cut:]
        rebuilt = first[:cut].copy()
        rebuilt[changed] = w[changed]
        if not (np.array_equal(rebuilt, w[:cut]) and kicks.size == w.size - cut):
            raise AssertionError(f"run {k} does not rebuild exactly")
        pairs = np.empty(2 * changed.size, dtype="<u4")
        pairs[0::2], pairs[1::2] = changed, w[changed]
        parts += [
            np.array([changed.size], dtype="<u4").tobytes(),
            pairs.tobytes(),
            np.array([kicks.size], dtype="<u4").tobytes(),
            kicks.tobytes(),
        ]
        del w, raw, rebuilt, kicks
    if first is None:
        raise ValueError("a batch needs at least one run")
    parts.insert(0, np.array([BATCH, 1, len(metas), cut], dtype="<u4").tobytes())
    if sum(len(x) for x in parts) > MAX_BYTES:
        raise ValueError("batch exceeds the native memory cap")
    Path(base).write_bytes(first.tobytes())
    Path(batch).write_bytes(b"".join(parts))
    return metas


def batch_fixture(base: Path, batch: Path, run: int) -> np.ndarray:
    """The words of one run's fixture, rebuilt from a base and its batch (as the native
    side does)."""
    first = np.frombuffer(Path(base).read_bytes(), dtype="<u4")
    b = np.frombuffer(Path(batch).read_bytes(), dtype="<u4")
    if int(b[0]) != BATCH or int(b[1]) != 1 or not 0 <= run < int(b[2]):
        raise ValueError("invalid batch or run")
    cut, at = int(b[3]), 4
    for k in range(run + 1):
        npairs = int(b[at])
        pairs = b[at + 1 : at + 1 + 2 * npairs]
        at += 1 + 2 * npairs
        nk = int(b[at])
        kicks = b[at + 1 : at + 1 + nk]
        at += 1 + nk
        if k == run:
            words = first[:cut].copy()
            words[pairs[0::2]] = pairs[1::2]
            return np.concatenate([words, kicks])
    raise AssertionError("unreachable")


def stimulated(fixture: Path) -> np.ndarray:
    """Rows of the fixture's stimulated neurons (those with an input column)."""
    words = np.frombuffer(Path(fixture).read_bytes(), dtype="<u4")
    n = int(words[2])
    cols = words[int(words[23]) : int(words[23]) + n].view("<i4")
    return np.flatnonzero(cols >= 0)


def input_ms(fixture: Path, dt_ms: float) -> float:
    """How long the fixture's input lasts: up to its last step with a kick."""
    words = np.frombuffer(Path(fixture).read_bytes(), dtype="<u4")
    steps, stim = int(words[3]), int(words[7])
    at = int(words[24])
    kicks = words[at : at + 2 * steps * stim].view("<f8").reshape(steps, stim)
    driven = np.flatnonzero(kicks.any(axis=1))
    return (int(driven[-1]) + 1) * dt_ms if driven.size else 0.0


def as_result(
    out: dict, fixture: Path, dt_ms: float, stim_ms: float | None = None
) -> sim.Result:
    """A decoded native output as a `sim.Result`: its spike counts per bin and first
    spikes, for the viewer. `stim_ms` defaults to the whole run."""
    h = np.frombuffer(Path(fixture).read_bytes(), dtype="<u4")[:HEADER_WORDS]
    bin_ms = int(h[4]) * dt_ms
    duration = out["counts"].shape[0] * bin_ms
    first = np.asarray(out["first"], dtype=float)
    return sim.Result(
        counts=np.asarray(out["counts"], dtype=np.int64),
        first_spike_ms=np.where(first >= 0, first * dt_ms, np.nan),
        bin_ms=bin_ms,
        stim_ms=duration if stim_ms is None else stim_ms,  # as sim.run reports it
    )


def read_counts(path: Path, fixture: Path) -> dict[str, np.ndarray | int]:
    """Decode a sparse counts output (`--counts`, a batch with `"output": "counts"`)
    against its fixture's header: the spike counts per bin and the first spikes, as
    `read_output` gives them."""
    h = np.frombuffer(Path(fixture).read_bytes(), dtype="<u4")[:HEADER_WORDS]
    n, bins = int(h[2]), int(h[3]) // int(h[4])
    w = np.frombuffer(Path(path).read_bytes(), dtype="<u4")
    if w.size < 6 or int(w[0]) != COUNTS:
        raise ValueError("invalid sparse counts output")
    step, nnz = int(w[1]), int(w[4])
    if int(w[2]) != n or int(w[3]) != bins or step > h[3]:
        raise ValueError("sparse counts output does not match its fixture")
    at = 5 + 2 * nnz
    if w.size < at + 1 or w.size != at + 1 + 2 * int(w[at]):
        raise ValueError("truncated sparse counts output")
    pairs, fp = w[5:at], w[at + 1 :]
    index, neuron, f = pairs[0::2], fp[0::2], fp[1::2].view("<i4")
    if (
        np.any(index >= bins * n)
        or np.any(neuron >= n)
        or np.any((f < 0) | (f > step))
        or np.unique(index).size != index.size
        or np.unique(neuron).size != neuron.size
    ):
        raise ValueError("invalid sparse counts output")
    counts = np.zeros(bins * n, dtype="<u4")
    counts[index] = pairs[1::2]
    first = np.full(n, -1, dtype="<i4")
    first[neuron] = f
    return {"step": step, "counts": counts.reshape(bins, n), "first": first}


def read_output(path: Path, fixture: Path) -> dict[str, np.ndarray | int]:
    """Decode native snapshot arrays; use acceptance comparator for parity."""
    h = np.frombuffer(Path(fixture).read_bytes(), dtype="<u4")[:HEADER_WORDS]
    raw = Path(path).read_bytes()
    if len(raw) < 12:
        raise ValueError("truncated native output")
    magic, step, size = struct.unpack_from("<III", raw)
    if (
        magic != OUTPUT
        or size != int(h[35])
        or len(raw) != 12 + size * 4
        or step > h[3]
    ):
        raise ValueError("invalid native output")
    state = np.frombuffer(raw, dtype="<u4", offset=12)
    n, steps, d, per_bin, ntrace = map(int, (h[2], h[3], h[5], h[4], h[8]))

    def take(slot, count, dtype="<u4"):
        return state[int(h[slot]) : int(h[slot]) + count].view(dtype).copy()

    out = {
        "step": step,
        "v": take(25, n, "<f4"),
        "g": take(26, n, "<f4"),
        "th": take(27, n, "<f4"),
        "ref_until": take(28, n, "<i4"),
        "ring_mask": take(29, d * n).reshape(d, n),
        "counts": take(30, steps // per_bin * n).reshape(steps // per_bin, n),
        "first": take(31, n, "<i4"),
        "traced": take(32, steps * ntrace).reshape(steps, ntrace),
    }
    if int(h[1]) == 2:
        words = np.frombuffer(Path(fixture).read_bytes(), dtype="<u4")
        ng = int(words[int(h[37])])
        base, bins = int(h[38]), steps // per_bin
        out["graded_ring"] = (
            state[base : base + d * ng].view("<f4").reshape(d, ng).copy()
        )
        at = base + d * ng + ng
        out["graded_vsum"] = (
            state[at : at + 2 * bins * ng].view("<f8").reshape(bins, ng).copy()
        )
        nc = int(words[int(h[37]) + 1])
        at += 2 * bins * ng + nc
        out["gap_pulse"] = state[at : at + nc].view("<i4").copy()
    return out
