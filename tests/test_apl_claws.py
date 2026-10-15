"""The APL claw lock is locked, removes APL output only in arm off and scores as written."""

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from flymsg import apl_claws, draws, evidence, odors, sim

OCT, MCH = "3-octanol", "4-methylcyclohexanol"


def test_locked_on_the_kc_sparseness_protocol_with_fresh_seeds():
    doc = apl_claws.assert_matches_code()
    assert doc["protocol"]["odors"] == [OCT, MCH]
    assert evidence.check_lock(doc, evidence.load(), "apl_claws") == [
        "apl_claw_odor_contrast"
    ]
    jobs = apl_claws.jobs(doc)
    assert len(jobs) == 2 * 2 * 5 and jobs[0] == ("on", OCT, 420)
    assert "apl-claws v1" in apl_claws.summary(doc)
    edited = apl_claws.load()
    edited["protocol"]["seeds"] = [95, 421, 422, 423, 424]
    with pytest.raises(apl_claws.AplClawsError, match="without a bump"):
        apl_claws.assert_locked(edited)
    edited["content_sha256"] = apl_claws.content_hash(edited)
    with pytest.raises(apl_claws.AplClawsError, match="disjoint"):
        apl_claws.assert_matches_code(edited)
    edited = apl_claws.load()
    edited["protocol"]["rate_at_response_1_hz"] = 150.0
    with pytest.raises(apl_claws.AplClawsError, match="KC sparseness"):
        apl_claws.assert_matches_code(edited)


# toy network: 0, 1 stimulated; 2-5 KCs; 6 APL; 7 ALPN
KCS, APL, PNS = np.arange(2, 6), np.array([6]), np.array([7])


def _toy() -> sparse.csc_matrix:
    post, pre, w = [], [], []

    def syn(a, b, mv):
        pre.append(a)
        post.append(b)
        w.append(mv)

    for k in KCS:
        syn(0, k, 8.0)
        syn(1, k, 2.0)
        syn(k, 6, 8.0)
        syn(6, k, -3.0)
    syn(0, 7, 6.0)
    syn(1, 7, 3.0)
    syn(6, 7, -1.0)
    return sparse.csc_matrix((w, (post, pre)), shape=(8, 8), dtype=np.float32)


def test_off_removes_every_apl_output_and_on_is_unchanged():
    W = _toy()
    w = apl_claws.arms(W, APL)
    assert w["on"] is W
    off = w["off"].toarray()
    assert not off[:, APL].any()  # no synapse from the APL
    keep = np.setdiff1d(np.arange(8), APL)
    assert (off[:, keep] == W.toarray()[:, keep]).all()  # its inputs and the rest stay
    assert W.toarray()[:, APL].any()  # the default is not touched


def _cells(claw, bouton, seeds=range(420, 425)):
    """`claw[arm][odor]` and `bouton[odor]`: one value or one per seed."""

    def at(x, i):
        return x[i] if isinstance(x, list) else x

    rows = []
    for arm in ("on", "off"):
        for odor in (OCT, MCH):
            for i, seed in enumerate(seeds):
                rows.append(
                    {
                        "arm": arm,
                        "odor": odor,
                        "seed": seed,
                        "claw_mv": at(claw[arm][odor], i),
                        "bouton_spikes": at(bouton[odor], i),
                        "kc_spiking": 0.05,
                    }
                )
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    "claw, bouton, expected",
    [
        # c_on 0, c_off 1/3 = c_pn: raises and restores
        (
            {"on": {OCT: 2.0, MCH: 2.0}, "off": {OCT: 4.0, MCH: 2.0}},
            {OCT: 40, MCH: 20},
            "pass",
        ),
        # c_off 0.6 overshoots c_pn 0.1 further than c_on 0: raises only
        (
            {"on": {OCT: 2.0, MCH: 2.0}, "off": {OCT: 8.0, MCH: 2.0}},
            {OCT: 55, MCH: 45},
            "partial",
        ),
        # c_off < c_on
        (
            {"on": {OCT: 3.0, MCH: 2.0}, "off": {OCT: 2.0, MCH: 2.0}},
            {OCT: 40, MCH: 20},
            "fail",
        ),
        # PN contrast not positive
        (
            {"on": {OCT: 2.0, MCH: 2.0}, "off": {OCT: 4.0, MCH: 2.0}},
            {OCT: 20, MCH: 20},
            "uninformative",
        ),
        # zero claw depolarization for one odor in one arm
        (
            {"on": {OCT: 2.0, MCH: 0.0}, "off": {OCT: 4.0, MCH: 2.0}},
            {OCT: 40, MCH: 20},
            "uninformative",
        ),
        # KCs held below rest for one odor in one arm
        (
            {"on": {OCT: 2.0, MCH: 2.0}, "off": {OCT: 4.0, MCH: -0.5}},
            {OCT: 40, MCH: 20},
            "uninformative",
        ),
    ],
)
def test_the_verdict_is_the_locks(claw, bouton, expected):
    doc = apl_claws.load()
    judged = apl_claws.judge(_cells(claw, bouton), doc)
    assert apl_claws.verdict(judged) == expected
    assert list(judged["seed"]) == ["420", "421", "422", "423", "424", "median"]


def test_relations_are_scored_on_the_medians_and_shared_per_seed():
    doc = apl_claws.load()
    # c_off per seed: 1/3 in three seeds, below c_on = 0 in two
    off_oct = [4.0, 4.0, 4.0, 1.0, 1.0]
    cells = _cells(
        {"on": {OCT: 2.0, MCH: 2.0}, "off": {OCT: off_oct, MCH: 2.0}},
        {OCT: 40, MCH: 20},
    )
    judged = apl_claws.judge(cells, doc)
    med = judged.iloc[-1]
    assert med["c_off"] == pytest.approx(1 / 3) and med["c_pn"] == pytest.approx(1 / 3)
    assert apl_claws.verdict(judged) == "pass"
    assert "raises True (3/5 seeds), restores True (3/5 seeds)" in apl_claws.describe(
        judged
    )


def _echo(job):
    return [{"job": list(job)}]


def test_the_jobs_pass_through_the_checkpointed_map(tmp_path):
    jobs = apl_claws.jobs(apl_claws.load())[:3]
    rows = draws.map_jobs(_echo, jobs, 1, None, tmp_path / "ck", {"v": 1})
    assert [tuple(r["job"]) for r in rows] == jobs


def test_one_job_runs_on_a_toy_network(tmp_path):
    doc = apl_claws.load()
    W = _toy()
    stimuli = {
        OCT: (np.array([0, 1]), np.array([150.0, 50.0])),
        MCH: (np.array([0, 1]), np.array([50.0, 150.0])),
    }
    ctx = (apl_claws.arms(W, APL), stimuli, KCS, PNS, doc)
    jobs = [("on", OCT, 420), ("off", OCT, 420)]
    rows = draws.map_jobs(apl_claws._job, jobs, 1, ctx, tmp_path / "ck", {"v": 1})
    on, off = rows
    assert on["claw_mv"] > 0 and 0 <= on["kc_spiking"] <= 1
    # same kicks: without APL output the KCs sit higher
    assert off["claw_mv"] > on["claw_mv"]
    # the ALPN count is the batch simulator's on the same kicks
    p, proto = sim.Params(), doc["protocol"]
    k = odors.kicks(stimuli[OCT][1], 420, p.dt, round(proto["odor_ms"] / p.dt))
    r = sim.run(W, stimuli[OCT][0], duration_ms=proto["duration_ms"], p=p, kicks=k)
    window = round(proto["odor_ms"] / r.bin_ms)
    assert on["bouton_spikes"] == int(r.counts[:window, PNS].sum())
    assert on["kc_spiking"] == float((r.counts[:window, KCS].sum(0) > 0).mean())
