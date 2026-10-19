"""Exploratory diagnosis of the held-out ORN_DM1 case: why does activity outlast the stimulus?

Runs the scored corner (default parameters, 100 Hz for 300 ms, 600 ms, seed 0), lists the
cell types that still fire from 400 to 600 ms, records the states of one neuron of each of
the most persistent types with flymsg.tracing, and measures how much of each one's
excitatory input comes from neurons that are themselves persistent. It does not change the
scored result (docs/result/benchmarks.md).

    uv run python scripts/orn_persistence.py
"""

from pathlib import Path

import numpy as np

from flymsg import data, sim, tracing

STIM, TARGET, SEED = "ORN_DM1", "DM1_lPN", 0


def main() -> None:
    neurons, edges = data.load(Path("data"))
    p = sim.Params()
    W = sim.network(neurons, edges, p)
    stim = data.resolve(neurons, STIM)
    r = sim.run(W, stim, 100.0, 600.0, 300.0, p, SEED)
    late = r.rate(400.0, 600.0)
    persistent = np.flatnonzero(late > 0)
    persistent = persistent[~np.isin(persistent, stim)]
    types = neurons["type"].fillna("untyped").to_numpy()
    print(
        f"{persistent.size} neurons fire from 400 to 600 ms (stimulus ends at 300 ms)"
    )
    names, counts = np.unique(types[persistent], return_counts=True)
    order = np.argsort(-counts)
    print("most common persistent types:")
    for i in order[:12]:
        members = persistent[types[persistent] == names[i]]
        print(
            f"  {names[i]:<14} {counts[i]:>4} neurons, late rate {late[members].mean():6.1f} Hz,"
            f" superclass {neurons['superclass'].iat[members[0]]}"
        )
    # one neuron per top type: the most active one, plus the scored target
    watch = [int(data.resolve(neurons, TARGET)[0])]
    for i in order[:5]:
        members = persistent[types[persistent] == names[i]]
        watch.append(int(members[np.argmax(late[members])]))
    trace, _ = tracing.record(
        W,
        stim,
        np.array(watch),
        rate_hz=100.0,
        duration_ms=600.0,
        stim_ms=300.0,
        seed=SEED,
        p=p,
        every=10,
    )
    is_late = np.zeros(len(neurons), dtype=bool)
    is_late[persistent] = True
    sign = neurons["sign"].to_numpy()
    print("recorded neurons (states every 1 ms; late = 400-600 ms):")
    for j, i in enumerate(watch):
        e = edges[edges["post"].to_numpy() == i]
        pre, w = e["pre"].to_numpy(), e["weight"].to_numpy()
        exc = sign[pre] > 0
        share = w[exc & is_late[pre]].sum() / max(1, w[exc].sum())
        t = trace.times_ms
        on, after = (t <= 300), (t > 400)
        print(
            f"  {types[i]:<14} bodyId {neurons['bodyId'].iat[i]}:"
            f" spikes {int(trace.spikes[:3000, j].sum())} during / "
            f"{int(trace.spikes[4000:, j].sum())} late;"
            f" mean g {trace.g[on, j].mean():5.2f} during / {trace.g[after, j].mean():5.2f} mV late;"
            f" {100 * share:4.1f}% of excitatory input synapses come from persistent neurons"
        )


if __name__ == "__main__":
    main()
