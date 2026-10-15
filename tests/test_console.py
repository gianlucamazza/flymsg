"""The console backend builds the runtimes sim.run steps, and reads outputs back as results."""

import numpy as np
from scipy import sparse

from flymsg import console, native, sim


def _network():
    rng = np.random.default_rng(2)
    W = sparse.random(80, 80, density=0.12, random_state=rng, format="csc")
    W.data = rng.integers(-20, 80, W.data.size).astype(np.float32)
    return W.astype(np.float32)


def test_the_runtime_steps_as_sim_run_does():
    W, p = _network(), sim.Params()
    for stim, stim_ms, seed in (([0, 3, 5], 30.0, 7), ([11], None, 8)):
        expected = sim.run(W, np.array(stim), 300.0, 60.0, stim_ms, p, seed)
        rt = console.sim_runtime(W, np.array(stim), 300.0, 60.0, stim_ms, p, seed)
        rt.advance_to(rt.snapshot()["counts"].shape[0] * 100)
        snap = rt.snapshot()
        assert np.array_equal(snap["counts"], expected.counts)
        first = np.where(snap["first"] >= 0, snap["first"] * p.dt, np.nan)
        assert np.allclose(first, expected.first_spike_ms, equal_nan=True)


def test_outputs_read_back_as_the_results_sim_run_gives(tmp_path):
    W, p = _network(), sim.Params()
    specs = [([0, 3, 5], 30.0, 7), ([11], None, 8)]
    runtimes = [
        console.sim_runtime(W, np.array(s), 300.0, 60.0, ms, p, seed)
        for s, ms, seed in specs
    ]
    native.export_batch(runtimes, tmp_path / "base.bin", tmp_path / "batch.bin")
    outputs, fixtures = [], []
    for k, rt in enumerate(runtimes):
        fixture = tmp_path / f"fixture_{k}.bin"
        fixture.write_bytes(
            native.batch_fixture(
                tmp_path / "base.bin", tmp_path / "batch.bin", k
            ).tobytes()
        )
        rt.advance_to(600)
        outputs.append(rt.snapshot())  # what read_output decodes, from the oracle
        fixtures.append(fixture)
    results = console.as_results(outputs, fixtures, p.dt, [30.0, 60.0])
    for (s, ms, seed), r in zip(specs, results, strict=True):
        expected = sim.run(W, np.array(s), 300.0, 60.0, ms, p, seed)
        assert np.array_equal(r.counts, expected.counts)
        assert r.bin_ms == expected.bin_ms and r.stim_ms == expected.stim_ms
