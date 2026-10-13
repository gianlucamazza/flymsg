"""Bounded exact step maps for continuously clamped refractory membranes."""

import hashlib
import threading
from collections import OrderedDict
from itertools import pairwise

import numpy as np
from scipy import sparse
from scipy.linalg import expm

SEMANTICS = "flymsg.gap/continuous-clamp-v1"
CACHE_BYTES = 64 * 1024 * 1024
_maps = OrderedDict()
_bytes = 0
_lock = threading.RLock()


def generators(gap, nodes, offsets, p):
    """Component generators and SHA-256 keys, in the engine's ordered node layout."""
    values, keys = [], []
    if nodes.size:
        i = np.asarray(gap.i, dtype=np.int64).reshape(-1)
        j = np.asarray(gap.j, dtype=np.int64).reshape(-1)
        c = np.broadcast_to(np.asarray(gap.coupling, dtype=np.float64), i.shape)
        keep = c > 0
        i, j, c = i[keep], j[keep], c[keep]
        K = sparse.coo_matrix(
            (np.r_[c, c], (np.r_[i, j], np.r_[j, i])),
            shape=(int(nodes.max()) + 1,) * 2,
        ).tocsr()
        for a, b in pairwise(offsets):
            C = K[nodes[a:b]][:, nodes[a:b]].toarray()
            A = (C - np.diag(1.0 + C.sum(axis=1))) / p.tau_m
            values.append(A.ravel())
            digest = hashlib.sha256(A.tobytes()).digest()
            keys.append(np.frombuffer(digest, dtype=np.uint64).copy())
    return (
        np.concatenate(values) if values else np.empty(0, np.float64),
        np.array(keys, dtype=np.uint64).reshape(-1, 4),
        np.array([p.dt, p.tau_m, p.tau_syn], dtype=np.float64),
    )


def clamped_map(A, frozen, clock, digest):
    """[P | Q] for free cells; clamped columns/rows are zero, sink diagonals retained.

    This host call runs only for components with refractory cells. The cache stores at
    most CACHE_BYTES of maps; a larger single map is computed but never cached.
    """
    global _bytes
    key = (tuple(int(x) for x in digest), frozen.tobytes(), tuple(clock))
    with _lock:
        if key in _maps:
            _maps.move_to_end(key)
            return _maps[key]
    free = np.flatnonzero(~frozen)
    m, f = len(A), len(free)
    result = np.zeros((m, 2 * m), dtype=np.float64)
    if f:
        dt, tau_m, tau_syn = clock
        block = np.zeros((2 * f, 2 * f), dtype=np.float64)
        block[:f, :f] = A[np.ix_(free, free)]
        block[:f, f:] = np.eye(f) / tau_m
        block[f:, f:] = -np.eye(f) / tau_syn
        E = expm(block * dt)
        result[np.ix_(free, free)] = E[:f, :f]
        result[np.ix_(free, m + free)] = E[:f, f:]
    if not np.isfinite(result).all():
        raise ValueError("nonfinite clamped electrical step")
    with _lock:
        if result.nbytes <= CACHE_BYTES:
            while _maps and _bytes + result.nbytes > CACHE_BYTES:
                _, old = _maps.popitem(last=False)
                _bytes -= old.nbytes
            if key not in _maps:
                _maps[key] = result
                _bytes += result.nbytes
    return result
