"""Exact steps for continuously clamped refractory membranes: bounded dense step maps, or the
truncated Taylor action of the same exponential (#155)."""

import hashlib
import math
import threading
import time
from collections import OrderedDict
from itertools import pairwise

import numpy as np
from scipy import sparse
from scipy.linalg import expm

SEMANTICS = "flymsg.gap/continuous-clamp-v1"
BOUNDARY_SEMANTICS = "flymsg.gap/boundary-reset-v1"
TAYLOR_SEMANTICS = "flymsg.gap/continuous-clamp-taylor-v1"
# Truncation bound of the Taylor action, relative to the 1-norm of the step's input
# [x, g, s]: the float64 unit roundoff.
TAYLOR_TOL = 2.0**-53
# Above this step norm the series needs more terms than it saves; use the dense maps.
TAYLOR_MAX_NORM = 0.5


def taylor_terms(norm: float) -> int:
    """Fewest terms K with norm^(K+1) / (K+1)! * e^norm <= TAYLOR_TOL: the remainder of
    exp(B dt) u after K terms, in the 1-norm, relative to |u|_1, for |B dt|_1 <= norm."""
    if not norm <= TAYLOR_MAX_NORM:
        raise ValueError(
            f"electrical step norm {norm:.3g} exceeds {TAYLOR_MAX_NORM}: "
            "use the dense solver"
        )
    k = 1
    while norm ** (k + 1) / math.factorial(k + 1) * math.exp(norm) > TAYLOR_TOL:
        k += 1
    return k


def step_norm(G, p) -> float:
    """|B dt|_1 of a component's block [A, I/tau_m, C/tau_m; 0, -I/tau_syn, 0; 0, 0, 0].
    Every refractory mask's reduced block is a principal submatrix, with no larger norm."""
    m = len(G)
    A, C = G[:, :m], G[:, m:]
    columns = np.r_[
        np.abs(A).sum(axis=0),
        1.0 / p.tau_m + 1.0 / p.tau_syn,
        np.abs(C).sum(axis=0) / p.tau_m,
    ]
    return float(columns.max() * p.dt)


CACHE_BYTES = 64 * 1024 * 1024
_maps = OrderedDict()
_bytes = 0
_lock = threading.RLock()
_counts = {"hits": 0, "misses": 0, "evictions": 0, "build_seconds": 0.0}


def cache_info():
    """Measured map events for this process, including its current memory budget."""
    with _lock:
        return {
            **_counts,
            "cached_bytes": _bytes,
            "budget_bytes": CACHE_BYTES,
            "maps": len(_maps),
        }


def generators(gap, nodes, offsets, p):
    """Component generators and SHA-256 keys, in the engine's ordered node layout."""
    values, keys, norm = [], [], 0.0
    if nodes.size:
        i = np.asarray(gap.i, dtype=np.int64).reshape(-1)
        j = np.asarray(gap.j, dtype=np.int64).reshape(-1)
        c = np.broadcast_to(np.asarray(gap.coupling, dtype=np.float64), i.shape)
        keep = c > 0
        back = (
            c
            if gap.coupling_back is None
            else np.broadcast_to(
                np.asarray(gap.coupling_back, dtype=np.float64), c.shape
            )
        )
        i, j, c, back = i[keep], j[keep], c[keep], back[keep]
        K = sparse.coo_matrix(
            (np.r_[c, back], (np.r_[i, j], np.r_[j, i])),
            shape=(int(nodes.max()) + 1,) * 2,
        ).tocsr()
        for a, b in pairwise(offsets):
            C = K[nodes[a:b]][:, nodes[a:b]].toarray()
            A = (C - np.diag(1.0 + C.sum(axis=1))) / p.tau_m
            G = np.hstack([A, C])
            norm = max(norm, step_norm(G, p))
            values.append(G.ravel())
            digest = hashlib.sha256(G.tobytes()).digest()
            keys.append(np.frombuffer(digest, dtype=np.uint64).copy())
    taylor = gap is not None and gap.solver == "taylor" and nodes.size
    return (
        np.concatenate(values) if values else np.empty(0, np.float64),
        np.array(keys, dtype=np.uint64).reshape(-1, 4),
        np.array(
            [
                p.dt,
                p.tau_m,
                p.tau_syn,
                float(gap is not None and gap.refractory_mode == "boundary"),
                float(taylor_terms(norm)) if taylor else 0.0,
            ],
            dtype=np.float64,
        ),
    )


def clamped_map(G, frozen, clock, digest):
    """[P | Q] for free cells; clamped columns/rows are zero, sink diagonals retained.

    This host call runs only for components with refractory cells. The cache stores at
    most CACHE_BYTES of maps; a larger single map is computed but never cached.
    """
    global _bytes
    key = (tuple(int(x) for x in digest), frozen.tobytes(), tuple(clock))
    with _lock:
        if key in _maps:
            _counts["hits"] += 1
            _maps.move_to_end(key)
            return _maps[key]
        _counts["misses"] += 1
    started = time.monotonic()
    free = np.flatnonzero(~frozen)
    m, f = len(G), len(free)
    A, C = G[:, :m], G[:, m:]
    result = np.zeros((m, 3 * m), dtype=np.float64)
    if f:
        dt, tau_m, tau_syn = clock[:3]
        block = np.zeros((2 * f + m, 2 * f + m), dtype=np.float64)
        block[:f, :f] = A[np.ix_(free, free)]
        block[:f, f : 2 * f] = np.eye(f) / tau_m
        block[:f, 2 * f :] = C[free] / tau_m
        block[f : 2 * f, f : 2 * f] = -np.eye(f) / tau_syn
        E = expm(block * dt)
        result[np.ix_(free, free)] = E[:f, :f]
        result[np.ix_(free, m + free)] = E[:f, f : 2 * f]
        result[np.ix_(free, 2 * m + np.arange(m))] = E[:f, 2 * f :]
    if not np.isfinite(result).all():
        raise ValueError("nonfinite clamped electrical step")
    with _lock:
        _counts["build_seconds"] += time.monotonic() - started
        if result.nbytes <= CACHE_BYTES:
            while _maps and _bytes + result.nbytes > CACHE_BYTES:
                _, old = _maps.popitem(last=False)
                _bytes -= old.nbytes
                _counts["evictions"] += 1
            if key not in _maps:
                _maps[key] = result
                _bytes += result.nbytes
    return result
