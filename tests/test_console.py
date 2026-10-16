"""The console backend builds the runtimes sim.run steps, and reads outputs back as results."""

import numpy as np
from scipy import sparse

from flymsg import console, sim


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


def test_portal_error_retains_http_status_without_credentials(monkeypatch, tmp_path):
    import subprocess

    import pytest

    portal = console.Portal.__new__(console.Portal)
    portal.base = "https://private-address"
    portal.config = 'user = "secret:password"'
    portal.pin = None
    portal.jar = str(tmp_path / "cookies")
    for status, code, category in [
        (401, 22, "authentication"),
        (404, 22, "missing-file"),
        (0, 7, "transport"),
    ]:
        monkeypatch.setattr(
            console.subprocess,
            "run",
            lambda *a, code=code, status=status, **kw: subprocess.CompletedProcess(
                [], code, f"\nFLYMSG_HTTP_STATUS:{status:03d}", "secret stderr"
            ),
        )
        with pytest.raises(console.PortalError) as caught:
            portal.curl("GET", "/api/files?token=private")
        assert caught.value.http_status == status
        assert category in str(caught.value)
        assert "private" not in str(caught.value)
        assert "secret" not in str(caught.value)
    monkeypatch.setattr(
        console.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            [], 0, '{"ok":true}\nFLYMSG_HTTP_STATUS:200', ""
        ),
    )
    assert portal.curl("GET", "/api/files") == '{"ok":true}'
