"""Versioned, bounded fixtures for the native ordered LIF executor."""

import struct
from pathlib import Path

import numpy as np

from flymsg.runtime import CpuRuntime

MAGIC = 0x314E4D46  # FMN1, little endian
OUTPUT = 0x314F4D46  # FMO1
HEADER_WORDS = 40
MAX_BYTES = 512 * 1024 * 1024


class NativeCapabilityError(ValueError):
    """A numerical mode has no qualified native implementation."""


def export_fixture(runtime: CpuRuntime, path: Path) -> dict:
    """Export a fresh initialized CPU runtime; scientific authority stays Python.

    This qualification format is intentionally separate from the run manifest.
    Kicks are converted to double counts, matching the kernel's kick arithmetic.
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
    sources = np.repeat(np.arange(n), np.diff(runtime._indptr))
    order = np.argsort(runtime._indices, kind="stable")
    counts = np.bincount(runtime._indices, minlength=n)
    add(16, np.r_[0, np.cumsum(counts)])
    add(17, sources[order])
    add(18, runtime._data[order], "<f4")
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
    header[34:37] = [cursor, state_cursor, len(order)]
    if (cursor + state_cursor) * 4 > MAX_BYTES:
        raise ValueError("fixture exceeds native qualification memory cap")
    path = Path(path)
    path.write_bytes(header.tobytes() + b"".join(chunks))
    return {
        "schema": f"flymsg.native_fixture/v{2 if extended else 1}",
        "input_bytes": cursor * 4,
        "state_bytes": state_cursor * 4,
        "precision": "ordered-f32-double-kicks",
        "steps": steps,
    }


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
