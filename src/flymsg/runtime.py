"""Incremental CPU execution of the existing LIF semantics; no GPU claims."""

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Protocol

import numpy as np
from scipy import sparse

from flymsg import sim

SCHEMA = "flymsg.neural_checkpoint/v1"


def _state_digest(
    state: dict[str, np.ndarray], identity: str, step: int, input_end: int
) -> str:
    digest = hashlib.sha256(json.dumps([identity, step, input_end]).encode())
    for name, array in sorted(state.items()):
        digest.update(name.encode())
        digest.update(str((array.shape, array.dtype.str)).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


SEMANTICS = "flymsg.lif/ordered-f32-v1"


class NeuralRuntime(Protocol):
    """Absolute, exclusive step boundaries; snapshots never alias live state."""

    def advance_to(self, step: int) -> None: ...

    def schedule_inputs(self, counts: np.ndarray) -> None: ...

    def snapshot(self) -> dict[str, np.ndarray]: ...

    def checkpoint(self, path: Path) -> None: ...

    def restore(self, path: Path) -> None: ...


class CpuRuntime:
    """Known-horizon runtime with explicit Poisson kicks and bounded recording.

    Inputs are copied. RNG is owned by the caller: checkpoint identity includes
    the complete kick schedule. All arrays are private implementation state.
    """

    def __init__(
        self,
        W: sparse.csc_matrix,
        stim: np.ndarray,
        *,
        steps: int,
        kicks: np.ndarray,
        p: sim.Params | None = None,
        per_bin: int = 100,
        silence: np.ndarray | None = None,
        trace: np.ndarray | None = None,
    ):
        if type(steps) is not int or steps <= 0 or steps >= 2**31:
            raise ValueError("steps must be a positive int below 2**31")
        if type(per_bin) is not int or per_bin <= 0 or steps % per_bin:
            raise ValueError("steps must be divisible by positive per_bin")
        if per_bin > np.iinfo(np.uint16).max:
            raise ValueError("per_bin would permit spike count overflow")
        self._p = replace(p or sim.Params())
        if not all(np.isfinite(v) for v in asdict(self._p).values()):
            raise ValueError("parameters must be finite")
        if (
            min(self._p.dt, self._p.tau_m, self._p.tau_syn, self._p.tau_th) <= 0
            or self._p.tau_m == self._p.tau_syn
        ):
            raise ValueError("invalid integration constants")
        if min(self._p.delay, self._p.t_ref) < 0:
            raise ValueError("delay and refractory period must be nonnegative")
        W = W.copy().tocsc()
        if W.shape[0] != W.shape[1] or W.shape[0] == 0 or not np.isfinite(W.data).all():
            raise ValueError("network must be nonempty, square and finite")
        self._n = W.shape[0]

        def ids(value):
            raw = np.asarray(value)
            if raw.size and raw.dtype.kind not in "iu":
                raise ValueError("indices must be integers")
            result = raw.astype(np.int64).reshape(-1)
            if np.any(result < 0) or np.any(result >= self._n):
                raise ValueError("indices outside network")
            return result

        self._stim = np.unique(ids(stim))
        raw = np.asarray(kicks)
        if (
            raw.ndim != 2
            or raw.shape[1] != self._stim.size
            or raw.shape[0] > steps
            or raw.dtype.kind not in "iu"
            or np.any(raw < 0)
        ):
            raise ValueError(
                "kicks must be nonnegative integer counts (steps, unique stim)"
            )
        if raw.dtype.kind == "u" and np.any(raw > np.iinfo(np.int64).max):
            raise ValueError("kick count exceeds int64")
        self._stim_steps = raw.shape[0]
        self._kicks = np.zeros((steps, self._stim.size), dtype=np.int64)
        self._kicks[: self._stim_steps] = raw
        self._steps, self._per_bin, self._step = steps, per_bin, 0
        self._indptr = W.indptr.astype(np.int64)
        self._indices = W.indices.astype(np.int64)
        self._data = W.data.astype(np.float32)
        if not np.isfinite(self._data).all():
            raise ValueError("weights exceed float32 range")
        self._silent = np.zeros(self._n, dtype=np.bool_)
        if silence is not None:
            self._silent[ids(silence)] = True
        self._is_stim = np.zeros(self._n, dtype=np.bool_)
        self._is_stim[self._stim] = True
        self._jump = np.full(self._n, self._p.th_jump, dtype=np.float32)
        self._jump[self._stim] = 0
        requested = ids([] if trace is None else trace)
        _, first_at = np.unique(requested, return_index=True)
        self._trace = requested[np.sort(first_at)]
        self._trace_col = np.full(self._n, -1, dtype=np.int32)
        self._trace_col[self._trace] = np.arange(self._trace.size, dtype=np.int32)
        self._d, self._ref_steps = sim._delays(self._p)
        if self._ref_steps + steps >= 2**31:
            raise ValueError("refractory deadlines exceed int32")
        self._constants = sim._constants(self._p)
        n = self._n
        self._state = {
            "v": np.full(n, self._p.v_rest, dtype=np.float32),
            "g": np.zeros(n, dtype=np.float32),
            "th": np.zeros(n, dtype=np.float32),
            "ref_until": np.zeros(n, dtype=np.int32),
            "ring": np.zeros((self._d, n), dtype=np.int32),
            "ring_len": np.zeros(self._d, dtype=np.int64),
            "counts": np.zeros((steps // per_bin, n), dtype=np.uint16),
            "first": np.full(n, -1, dtype=np.int64),
            "traced": np.zeros((steps, max(1, self._trace.size)), dtype=np.uint8),
        }
        config = json.dumps(
            {
                "semantics": SEMANTICS,
                "params": asdict(self._p),
                "steps": steps,
                "per_bin": per_bin,
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(config.encode())
        for array in (
            self._indptr,
            self._indices,
            self._data,
            self._stim,
            self._kicks,
            self._silent,
            self._trace,
        ):
            digest.update(str((array.shape, array.dtype.str)).encode())
            digest.update(array.tobytes())
        digest.update(str(self._stim_steps).encode())
        self._identity = digest.hexdigest()
        self._state["input_counts"] = self._kicks
        self._scratch = (
            np.zeros(n, dtype=np.float32),
            np.empty(n, dtype=np.int32),
            np.zeros(n, dtype=np.bool_),
            np.empty(n, dtype=np.int32),
        )

    @property
    def step(self) -> int:
        return self._step

    @property
    def tick_us(self) -> int:
        """The neural step in microseconds, from `p.dt`."""
        return round(self._p.dt * 1000)

    @property
    def n_inputs(self) -> int:
        """Columns of an input block: the stimulated neurons, deduplicated."""
        return int(self._stim.size)

    def advance_to(self, step: int) -> None:
        if type(step) is not int or not self._step <= step <= self._steps:
            raise ValueError("advance target must be monotonic and within horizon")
        s = self._state
        sim._advance(
            self._step,
            step,
            self._indptr,
            self._indices,
            self._data,
            self._n,
            self._per_bin,
            self._d,
            self._ref_steps,
            self._stim,
            self._kicks,
            self._is_stim,
            self._silent,
            self._jump,
            *self._constants,
            self._trace_col,
            s["traced"],
            s["v"],
            s["g"],
            s["th"],
            s["ref_until"],
            s["ring"],
            s["ring_len"],
            s["counts"],
            s["first"],
            *self._scratch,
        )
        self._step = step

    def schedule_inputs(self, counts: np.ndarray) -> None:
        """Replace upcoming Poisson-count inputs at the current exclusive boundary.

        This is explicit input delivery, not forced output spikes. The existing
        kernel applies kicks after thresholding, preserving its phase semantics.
        """
        values = np.asarray(counts)
        if (
            values.ndim != 2
            or values.shape[1] != self._stim.size
            or values.dtype.kind not in "iu"
            or np.any(values < 0)
        ):
            raise ValueError("inputs must be nonnegative integer counts")
        end = self._step + values.shape[0]
        if end > self._steps or (
            values.dtype.kind == "u" and np.any(values > np.iinfo(np.int64).max)
        ):
            raise ValueError("input block exceeds horizon or count range")
        self._kicks[self._step : end] = values
        self._stim_steps = max(self._stim_steps, end)

    def snapshot(self) -> dict[str, np.ndarray]:
        return {name: value.copy() for name, value in self._state.items()}

    def read(self, idx: np.ndarray) -> dict[str, np.ndarray]:
        """Copies of `v`, `g`, `th` and the refractory flag of neurons `idx` at the current
        boundary; cheaper than `snapshot` when only a few neurons are watched."""
        idx = np.asarray(idx, dtype=np.int64)
        s = self._state
        return {
            "v": s["v"][idx].copy(),
            "g": s["g"][idx].copy(),
            "th": s["th"][idx].copy(),
            # refractory at the next step: the kernel holds a neuron while step < ref_until
            "refractory": s["ref_until"][idx] > self._step,
        }

    def result(self) -> sim.Result:
        if self._step != self._steps:
            raise ValueError(
                "result requires completed horizon; use snapshot during execution"
            )
        s = self.snapshot()
        return sim.Result(
            s["counts"],
            np.where(s["first"] >= 0, s["first"] * self._p.dt, np.nan),
            self._per_bin * self._p.dt,
            self._stim_steps * self._p.dt,
            s["traced"] if self._trace.size else None,
        )

    def checkpoint(self, path: Path) -> None:
        """Atomic NPZ replacement, without pickle; callers record artifact hash."""
        path = Path(path)
        temporary = path.with_name(path.name + ".tmp")
        metadata = json.dumps(
            {
                "schema": SCHEMA,
                "semantics": SEMANTICS,
                "identity": self._identity,
                "step": self._step,
                "state_sha256": _state_digest(
                    self._state, self._identity, self._step, self._stim_steps
                ),
                "input_end": self._stim_steps,
            },
            sort_keys=True,
        )
        try:
            with temporary.open("wb") as stream:
                np.savez(stream, metadata=np.array(metadata), **self._state)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def restore(self, path: Path) -> None:
        """Validate all fields before replacing state; inputs must match exactly."""
        with np.load(path, allow_pickle=False) as document:
            meta = json.loads(str(document["metadata"]))
            if (
                meta.get("schema") != SCHEMA
                or meta.get("semantics") != SEMANTICS
                or meta.get("identity") != self._identity
            ):
                raise ValueError("incompatible checkpoint")
            step = meta.get("step")
            if type(step) is not int or not 0 <= step <= self._steps:
                raise ValueError("invalid checkpoint step")
            input_end = meta.get("input_end")
            if type(input_end) is not int or not 0 <= input_end <= self._steps:
                raise ValueError("invalid input horizon")
            if set(document.files) != {"metadata", *self._state}:
                raise ValueError("invalid checkpoint fields")
            state = {}
            for name, expected in self._state.items():
                value = document[name]
                if (
                    value.shape != expected.shape
                    or value.dtype != expected.dtype
                    or not np.isfinite(value).all()
                ):
                    raise ValueError(f"invalid checkpoint array: {name}")
                state[name] = value.copy()
            if (
                np.any(state["ring_len"] < 0)
                or np.any(state["ring_len"] > self._n)
                or np.any(state["ring"] < 0)
                or np.any(state["ring"] >= self._n)
            ):
                raise ValueError("invalid delayed spike queue")
            if (
                np.any(state["first"] < -1)
                or np.any(state["first"] >= step)
                or np.any(state["ref_until"] < 0)
            ):
                raise ValueError("invalid temporal state")
            if np.any(state["input_counts"] < 0):
                raise ValueError("invalid input counts")
            if meta.get("state_sha256") != _state_digest(
                state, self._identity, step, input_end
            ):
                raise ValueError("checkpoint integrity mismatch")
            self._state, self._step = state, step
            self._kicks = state["input_counts"]
            self._stim_steps = input_end
