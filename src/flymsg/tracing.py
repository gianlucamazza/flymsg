"""Selective state recording (#26): why a neuron spikes, stays silent or keeps firing.

For chosen neurons, at the end of every recorded step: membrane potential `v` (mV),
synaptic drive `g` (mV), adaptive threshold offset `th` (mV), whether the neuron is
refractory at the next step, its spikes at every step, and the Poisson input counts it
received. These are model states, not measured physiology.

The recording drives `CpuRuntime`, which advances the same compiled step loop as `sim.run`
and matches it bit for bit when run in blocks, so recording cannot change a spike. Off by
default: nothing else calls it.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from scipy import sparse

from flymsg import sim
from flymsg.runtime import CpuRuntime

WARN_VALUES = 10_000_000  # recorded values per state array above which a request warns
MAX_VALUES = 100_000_000  # ... and above which it is refused (400 MB of float32)


@dataclass(frozen=True)
class StateTrace:
    neurons: np.ndarray  # rows of the network, in the order requested
    step_ms: float  # time between recorded samples
    dt_ms: float  # neural step
    v: np.ndarray  # (samples, k) float32, mV, at the end of each recorded step
    g: np.ndarray  # (samples, k) float32
    th: np.ndarray  # (samples, k) float32
    refractory: np.ndarray  # (samples, k) bool, refractory at the following step
    spikes: np.ndarray  # (steps, k) bool, every neural step
    input_counts: (
        np.ndarray
    )  # (steps, k) int64, Poisson kicks received (0 if not stimulated)

    @property
    def times_ms(self) -> np.ndarray:
        """End time of each recorded sample."""
        return (np.arange(self.v.shape[0]) + 1) * self.step_ms


def record(
    W: sparse.csc_matrix,
    stim: np.ndarray,
    neurons: np.ndarray,
    *,
    rate_hz: float,
    duration_ms: float,
    stim_ms: float | None,
    seed: int,
    p: sim.Params | None = None,
    bin_ms: float = 10.0,
    silence: np.ndarray | None = None,
    every: int = 1,
) -> tuple[StateTrace, sim.Result]:
    """Run one simulation as `sim.run` would and record `neurons` every `every` steps.

    The Poisson input is `sim.poisson_kicks(seed, ...)`, the draw `sim.run` makes, so the
    returned `Result` equals `sim.run(W, stim, rate_hz, duration_ms, stim_ms, p, seed,
    bin_ms, silence)`.
    """
    p = p or sim.Params()
    stim = np.unique(stim)
    neurons = np.asarray(neurons, dtype=np.int64).reshape(-1)
    if neurons.size == 0:
        raise ValueError("no neurons to record")
    if type(every) is not int or every < 1:
        raise ValueError("every must be a positive int")
    steps = int(duration_ms / p.dt)
    per_bin = max(1, round(bin_ms / p.dt))
    if steps % every:
        raise ValueError(f"the run ({steps} steps) is not a multiple of every={every}")
    samples = steps // every
    values = samples * neurons.size
    if values > MAX_VALUES:
        raise ValueError(
            f"{values:,} values per state array exceed the {MAX_VALUES:,} limit; "
            "record fewer neurons or a larger `every`"
        )
    if values > WARN_VALUES:
        warnings.warn(
            f"recording {values:,} values per state array "
            f"(~{4 * values * 3 / 1e6:,.0f} MB)",
            stacklevel=2,
        )
    stim_steps = steps if stim_ms is None else int(stim_ms / p.dt)
    kicks = sim.poisson_kicks(seed, rate_hz, p.dt, stim_steps, stim.size)
    rt = CpuRuntime(
        W,
        stim,
        steps=steps,
        kicks=kicks,
        p=p,
        per_bin=per_bin,
        silence=silence,
        trace=neurons,
    )
    out = {k: [] for k in ("v", "g", "th", "refractory")}
    for t in range(every, steps + 1, every):
        rt.advance_to(t)
        for k, value in rt.read(neurons).items():
            out[k].append(value)
    result = rt.result()
    # input per watched neuron: its column of the kick matrix, zero if not stimulated
    col = {int(s): j for j, s in enumerate(stim)}
    inputs = np.zeros((steps, neurons.size), dtype=np.int64)
    for j, n in enumerate(neurons):
        if int(n) in col:
            inputs[:stim_steps, j] = kicks[:, col[int(n)]]
    # result.traced has one column per distinct neuron, in order of first appearance
    distinct = {int(n): j for j, n in enumerate(dict.fromkeys(neurons.tolist()))}
    spikes = result.traced[:, [distinct[int(n)] for n in neurons]].astype(bool)
    trace = StateTrace(
        neurons=neurons,
        step_ms=every * p.dt,
        dt_ms=p.dt,
        v=np.stack(out["v"]),
        g=np.stack(out["g"]),
        th=np.stack(out["th"]),
        refractory=np.stack(out["refractory"]),
        spikes=spikes,
        input_counts=inputs,
    )
    return trace, result
