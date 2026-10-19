"""Synthetic DN arena on the full MaleCNS (issue #263). The YAML file is the lock.

On the full connectome in a closed loop with a kinematic planar body, an engineered
descending-neuron readout and the graded visual pathway of T4/T5 version 4, driven
by a lateral dark sphere: whether the intact graph's change in yaw over the locked
window lies outside the range of 39 degree-preserving shuffles, at every pathway
configuration. A difference is synthetic, not a biological or connectome-derived
mechanism. The run builds the loop once, then runs every job. Version 1 results
stay with their source commit.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import (
    arena_controls,
    closedloop,
    data,
    draws,
    eye,
    locks,
    manifest,
    optics,
    parallel,
    pose,
    runstore,
    sim,
    t4t5,
    visual_pathway,
)
from flymsg.arena import Arena
from flymsg.dn_decoder import SIDES, TYPES, Decoder
from flymsg.embodiment import Clock
from flymsg.paths import repository_root, require_repository_path
from flymsg.runtime import CpuRuntime

ROOT = repository_root()
PATH = ROOT / "validation" / "dn_arena.yaml"
INVENTORY = ROOT / "docs" / "dn-arena-inventory.md"

# Version 1 names that source commit (docs/replication.md). The maintainer fills
# version 2 with the lock's content_sha256; until then the placeholder is not a digest.
VERSION_HASHES = {
    1: "9ba9a69c8397fae5c6aa9ee60cd48147d4898110c2dbb22a2d461254b4583aa3",
    2: "1426386c66041510812bdcd6b3bfebb91d05a0811c5bfe33f9c191f3cd9a3ac7",
}

_PAIRS = tuple((kind, side) for kind in TYPES for side in SIDES)
_SETUP = None
_HEX = frozenset("0123456789abcdef")


class DNArenaError(ValueError):
    """The DN arena protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(doc, VERSION_HASHES, DNArenaError, "DN arena protocol")


def assert_matches_code(doc: dict | None = None) -> dict:
    doc = assert_locked() if doc is None else doc
    if doc["version"] != 2:
        raise DNArenaError("this module implements DN arena version 2")
    model = doc["model"]
    for name in ("neural_us", "body_us", "control_us", "latency_us", "duration_us"):
        if type(model[name]) is not int:
            raise DNArenaError(f"{name} is not an integer")
    if model["input_encoding"] != "kick_equivalent":
        raise DNArenaError("input_encoding is not kick_equivalent")
    p = sim.Params()
    if model["neural_us"] != round(p.dt * 1000):
        raise DNArenaError("neural_us is not the model's step")
    if model["params"] != "sim.Params() defaults" or model["dataset"] != "malecns":
        raise DNArenaError("the model is not sim.Params() on MaleCNS")
    clock = Clock(
        neural_us=model["neural_us"],
        body_us=model["body_us"],
        control_us=model["control_us"],
        latency_us=model["latency_us"],
    )
    clock.validate()
    if model["duration_us"] % clock.control_us:
        raise DNArenaError("duration must be a multiple of the control period")
    _window("score", doc["score"]["window_us"], model["duration_us"], clock.body_us)
    _window("decoder", doc["decoder"]["window_us"], model["duration_us"], clock.body_us)
    _score_ok(doc)
    if doc["arms"] != list(closedloop.ARMS):
        raise DNArenaError("arms are not the closed-loop arms in order")
    wn = doc["controls"]["wiring_null"]
    if (wn["seed0"], wn["seeds"]) != (7300, 39):
        raise DNArenaError("wiring-null seeds are not 7300-7338")
    if wn["rule"] != (
        "wiring.shuffle_targets on the MaleCNS edges, then the intact loop at "
        "that configuration: the pathway is rebuilt on the shuffled graph by the "
        "same builder (timing scale and lamina to medulla gain by type, graded "
        "release by type) and dark-anchored on it; the photoreceptor release rate "
        "and the drive gain are those of the intact graph, a calibration of the "
        "stimulus, not of the network"
    ):
        raise DNArenaError("the wiring-null rule changed")
    if doc["controls"]["script"]["rule"] != (
        "yaw +100 deg/s toward the eye with the larger summed coverage "
        "(left positive), 0 when equal; forward 10 mm/s; "
        "from the previous control tick's sample"
    ):
        raise DNArenaError("the script rule changed")
    if neurons(doc) != _mapped_inventory(
        require_repository_path(INVENTORY).read_text(encoding="utf-8")
    ):
        raise DNArenaError("decoder neurons are not the mapped inventory rows")
    if doc["decoder"]["yaw_rule"] != (
        "yaw rad/s = g_yaw * ((DNa01 L - DNa01 R) + (DNa02 L - DNa02 R)) "
        "spikes/s; positive yaw turns left (counterclockwise about world z)"
    ):
        raise DNArenaError("the yaw rule changed")
    if doc["decoder"]["forward_rule"] != (
        "forward m/s = g_forward * (oDN1 L + oDN1 R) spikes/s"
    ):
        raise DNArenaError("the forward rule changed")
    _gains_ok(doc)
    if doc["silenced"] != "the six decoder neurons":
        raise DNArenaError("silenced is not the six decoder neurons")
    _pathway_ok(doc)
    eye_doc, stim = doc["eye"], doc["stimulus"]
    if eye_doc["registration"] != (
        "test-only identity, eyemap frame = body frame; "
        "no sourced registration exists (#179)"
    ):
        raise DNArenaError("the registration is not the test-only identity")
    if eye_doc["mounts"] != (
        "pose.flygym_eye_mounts(): FlyGym 2.1.0 NeuroMechFly vision cameras"
    ):
        raise DNArenaError("the eye mounts are not FlyGym's")
    if eye_doc["acceptance_deg"] != 8.23:
        raise DNArenaError("acceptance is not 8.23 deg")
    if stim["sphere"] != "lateral":
        raise DNArenaError("the sphere is not the lateral one")
    if stim["center_z"] != "the mean world height of the two eye mounts at reset":
        raise DNArenaError("the sphere height is not the eye mounts at reset")
    if stim["center_rule"] != (
        "y +10 mm is the fly's left at heading 0; static in the world"
    ):
        raise DNArenaError("the sphere is not static at the fly's left")
    _sphere_ok(stim)
    _body_ok(doc["body"])
    if (
        eye_doc["registration_evidence"] != "unmapped"
        or stim["evidence"] != "engineered"
        or doc["decoder"]["evidence"] != "engineered"
        or doc["body"]["evidence"] != "synthetic"
        or doc["controls"]["script"]["evidence"] != "synthetic"
    ):
        raise DNArenaError("a component status is not the one this loop implements")
    if type(doc["seed"]) is not int:
        raise DNArenaError("the seed is not an integer")
    if type(doc["smoke"]) is not str or not doc["smoke"]:
        raise DNArenaError("smoke is empty")
    if doc["claim"]["scored"] is not False:
        raise DNArenaError("the claim must not be scored")
    if doc["defaults_changed"] is not False:
        raise DNArenaError("the test never changes the defaults")
    if doc["evidence"] != "none":
        raise DNArenaError("evidence is not none")
    return doc


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    model, wn = doc["model"], doc["controls"]["wiring_null"]
    return (
        f"dn_arena v{doc['version']} (issue #{doc['issue']}): "
        f"{len(configurations(doc))} configurations, {len(doc['arms'])} arms, "
        f"{wn['seeds']} nulls, seeds {wn['seed0']}-{wn['seed0'] + wn['seeds'] - 1}, "
        f"duration {model['duration_us']} us, {model['input_encoding']}"
    )


def configurations(doc: dict) -> list[dict]:
    """The lock's pathway configurations, in order, in the shape `build` expects."""
    path = doc["pathway"]
    return [
        {
            "index": i,
            "photoreceptor_mv": path["photoreceptor_response_mv"],
            "lmc_mv": path["lmc_hyperpolarisation_mv"],
            "lmc_rate_hz": path["lmc_rate_hz"],
            "medulla_rate_hz": path["medulla_rate_hz"],
            "lamina_medulla_gain": gain,
        }
        for i, gain in enumerate(path["lamina_medulla_gain"])
    ]


def neurons(doc: dict) -> dict[int, tuple[str, str]]:
    """`<bodyId> <type> <side>` rows from the lock."""
    out: dict[int, tuple[str, str]] = {}
    for raw in doc["decoder"]["neurons"]:
        parts = str(raw).split()
        if len(parts) != 3 or not parts[0].isdigit():
            raise DNArenaError(
                f"decoder neuron {raw!r} is not '<bodyId> <type> <side>'"
            )
        body = int(parts[0])
        if body in out:
            raise DNArenaError(f"decoder bodyId {body} is repeated")
        out[body] = (parts[1], parts[2])
    return out


def jobs(doc: dict) -> list[dict]:
    """Arms job, then that configuration's wiring-null jobs; the script job is last."""
    order = _arm_order()
    wn = doc["controls"]["wiring_null"]
    seeds = range(wn["seed0"], wn["seed0"] + wn["seeds"])
    out = []
    for cfg in configurations(doc):
        index = cfg["index"]
        out.append(
            {
                "key": _key("arms", index),
                "kind": "arms",
                "configuration": cfg,
                "arms": list(order),
            }
        )
        for seed in seeds:
            out.append(
                {
                    "key": _key("wiring-null", index, seed),
                    "kind": "wiring-null",
                    "configuration": cfg,
                    "seed": seed,
                }
            )
    out.append({"key": "script", "kind": "script"})
    return out


def pathway(W, neurons_df, cfg: dict, lit, proto: dict, p: sim.Params, *, rate=None):
    """`prepare` then `build` on `W`. `dark` is T4/T5 version 4's.

    Zero float32 kicks of shape `(settle_steps, 1)` land on the first
    photoreceptor, `sim.run` uses `proto["seed"]`, and the anchor is `graded_v[-1]`.
    `rate`, when given, is the intact graph's `(rate_hz, receiving)`.
    """
    try:
        static = visual_pathway.prepare(W, neurons_df, proto, p)

        def dark(Wc, graded):
            kicks = np.zeros((static.settle_steps, 1), dtype=np.float32)
            return sim.run(
                Wc,
                static.receptors_all[:1],
                duration_ms=static.settle_steps * p.dt,
                p=p,
                seed=proto["seed"],
                kicks=kicks,
                graded=graded,
                membrane=static.membrane,
            ).graded_v[-1]

        built = visual_pathway.build(static, cfg, proto, lit, p, dark, rate=rate)
    except visual_pathway.PathwayError as err:
        raise DNArenaError(str(err)) from err
    return static, built


def drive(coverage, column_of_input, gain, steps) -> np.ndarray:
    """float32(gain * (1 - coverage[column])) on every neural step of one body tick.

    The product is float64, then one cast, as `(gain * lit).astype(np.float32)`.
    """
    cov = np.asarray(coverage, dtype=np.float64)
    lit = np.ravel(1.0 - cov[np.asarray(column_of_input)])
    row = (gain * lit).astype(np.float32)
    return np.broadcast_to(row, (steps, row.shape[0])).copy()


def cpu_runtime(
    built,
    input_rows,
    *,
    steps: int,
    p: sim.Params,
    per_bin: int,
    trace,
    silence: bool,
) -> CpuRuntime:
    """A fresh kick-equivalent runtime on one anchored pathway. Kicks start empty."""
    n = int(np.asarray(input_rows).size)
    return CpuRuntime(
        built.W,
        input_rows,
        steps=steps,
        kicks=np.zeros((0, n), np.float32),
        p=p,
        per_bin=per_bin,
        trace=trace,
        silence=trace if silence else None,
        graded=built.graded,
        membrane=built.membrane,
        input_encoding="kick_equivalent",
    )


def heading_rad(record, clock: Clock) -> np.ndarray:
    """Unwrapped heading after each body tick (`Arena.step`'s accumulation)."""
    dt = clock.body_us / 1e6
    yaw = 0.0
    out = np.empty(len(record.ticks), dtype=float)
    for i, tick in enumerate(record.ticks):
        if tick.time_us != i * clock.body_us:
            raise DNArenaError("the record is not one heading per body tick")
        omega = 0.0
        for name, _mujoco_id, value in tick.commands:
            if name == "yaw":
                omega = float(value)
        yaw = yaw + omega * dt
        out[i] = yaw
    return out


def yaw_change(heading, clock: Clock, window_us) -> float:
    """End heading minus start heading. Off-grid windows refuse."""
    start, end = window_us
    if type(start) is not int or type(end) is not int:
        raise DNArenaError("the window is not integers")
    if start % clock.body_us or end % clock.body_us:
        raise DNArenaError("the window is off the body grid")
    last = len(heading) * clock.body_us
    if not 0 <= start < end <= last:
        raise DNArenaError("the window is outside the record")

    def at(time_us: int) -> float:
        if time_us == 0:
            return 0.0
        return float(heading[time_us // clock.body_us - 1])

    return at(end) - at(start)


def record_names(row: dict) -> dict[str, str]:
    """The stored record name and canonical-JSON sha256 behind one job's result."""
    if row["kind"] == "arms":
        return {
            f"{row['key']}__{arm}": summary["record_sha256"]
            for arm, summary in row["arms"].items()
        }
    return {row["key"]: row["record_sha256"]}


def verify_records(out, rows: list[dict]) -> None:
    """Every result's record exists and decompresses to the JSON its sha256 names, also
    for jobs a checkpoint resumed: damaged evidence refuses, it is never recomputed."""
    for row in rows:
        for name, digest in record_names(row).items():
            path = Path(out) / "records" / f"{name.replace('/', '__')}.json.gz"
            if not path.is_file():
                raise DNArenaError(f"the record of {name} is missing")
            with gzip.open(path, "rb") as stream:
                text = stream.read().decode()
            if hashlib.sha256(text.encode()).hexdigest() != digest:
                raise DNArenaError(f"the record of {name} does not match its sha256")


def verdict(results: list[dict], doc: dict) -> dict:
    """Per configuration: no-go, or the inclusive null range; then the envelope."""
    by: dict[str, dict] = {}
    for row in results:
        if row["key"] in by:
            raise DNArenaError(f"duplicate job {row['key']}")
        by[row["key"]] = row
    script = _take(by, "script")
    script_yaw = float(script["yaw_change"])
    wn = doc["controls"]["wiring_null"]
    seeds = range(wn["seed0"], wn["seed0"] + wn["seeds"])
    ids = [str(body) for body in sorted(neurons(doc))]
    reported = []
    labels = []
    for cfg in configurations(doc):
        index = cfg["index"]
        arms_row = _take(by, _key("arms", index))
        if arms_row.get("replay_parity") is not True:
            raise DNArenaError("replay parity is required")
        digest = _sha256_hex(arms_row.get("pathway_sha256"))
        nulls = np.array(
            [
                float(_take(by, _key("wiring-null", index, seed))["yaw_change"])
                for seed in seeds
            ]
        )
        per_arm = arms_row["arms"]
        intact = float(per_arm["intact"]["yaw_change"])
        spikes = per_arm["intact"]["spikes"]
        if set(spikes) != set(ids):
            raise DNArenaError("intact spikes must name the six decoder neurons")
        lo, hi = float(nulls.min()), float(nulls.max())
        if sum(spikes.values()) == 0:
            label = "uninformative"
        elif lo <= intact <= hi:
            label = "null"
        else:
            label = "difference"
        labels.append(label)
        reported.append(
            {
                "index": index,
                "photoreceptor_mv": cfg["photoreceptor_mv"],
                "lmc_mv": cfg["lmc_mv"],
                "lmc_rate_hz": cfg["lmc_rate_hz"],
                "medulla_rate_hz": cfg["medulla_rate_hz"],
                "lamina_medulla_gain": cfg["lamina_medulla_gain"],
                "verdict": label,
                "intact": intact,
                "disconnected": float(per_arm["disconnected"]["yaw_change"]),
                "shuffled": float(per_arm["shuffled"]["yaw_change"]),
                "replay": float(per_arm["replay"]["yaw_change"]),
                "silenced": float(per_arm["silenced"]["yaw_change"]),
                "script": script_yaw,
                "intact_minus_script": intact - script_yaw,
                "wiring_null_minimum": lo,
                "wiring_null_median": float(np.median(nulls)),
                "wiring_null_maximum": hi,
                "spikes": {arm: per_arm[arm]["spikes"] for arm in _arm_order()},
                "pathway_sha256": digest,
                "replay_parity": True,
            }
        )
    if set(labels) == {"uninformative"}:
        envelope = "uninformative"
    elif len(set(labels)) == 1:
        envelope = f"robust: {labels[0]}"
    else:
        envelope = "depends"
    return {"configurations": reported, "envelope": envelope}


def run(data_dir, out, workers: int, checkpoint, execution_id: str) -> dict:
    """Assert the lock, build the loop once per process, then run every job."""
    doc = assert_matches_code()
    neurons_df, edges = data.load(data_dir)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "records").mkdir(exist_ok=True)
    packed = [_pack(job) for job in jobs(doc)]
    meta = {"version": doc["version"], "sha256": doc["content_sha256"]}
    in_process = workers <= 1 or len(packed) <= 1
    ctx = (
        build(doc, neurons_df, edges, data_dir, out, execution_id)
        if in_process
        else (doc, neurons_df, edges, data_dir, out, execution_id)
    )
    rows = draws.map_jobs(_job, packed, workers, ctx, checkpoint, meta)
    verify_records(out, rows)
    frame = pd.DataFrame([{k: _csv_value(v) for k, v in row.items()} for row in rows])
    frame.to_csv(out / "results.csv", index=False)
    found = verdict(rows, doc)
    runstore.atomic_json(out / "verdict.json", found)
    return found


@dataclass(frozen=True)
class Setup:
    doc: dict
    clock: Clock
    duration_us: int
    score_window: tuple[int, int]
    proto: dict
    evidence: dict
    provenance: pose.Provenance
    neurons: pd.DataFrame
    edges: pd.DataFrame
    params: sim.Params
    W: object
    input_rows: np.ndarray
    input_ids: tuple[int, ...]
    column_of_input: np.ndarray
    traced_rows: np.ndarray
    traced_ids: tuple[int, ...]
    stimulus: object
    optics_hash: str
    sides: tuple[str, ...]
    out: Path
    execution_id: str
    intact: dict


def build(doc, neurons_df, edges, data_dir, out, execution_id: str) -> Setup:
    """The loop shared by every job. The optical callable stays in this process."""
    data_dir, out = Path(data_dir), Path(out)
    eye.fetch(data_dir)
    ann = pd.read_feather(
        data_dir / "raw" / data.RAW["annotations"],
        columns=["bodyId", "type", "instance", "assignedOlHex1", "assignedOlHex2"],
    )
    cols = eye.columns(ann, eye.lenses(data_dir))
    receptors = eye.photoreceptors(neurons_df, edges, ann)
    columns = optics.Columns.from_frame(cols, _source_sha256(data_dir))
    azimuth = cols["azimuth_deg"].notna().to_numpy()
    elevation = cols["elevation_deg"].notna().to_numpy()
    has = azimuth & elevation
    mask = np.isfinite(columns.direction).all(axis=1)
    if not np.array_equal(has, mask):
        raise DNArenaError("column directions do not match the lens table")
    rank = np.full(len(cols), -1, dtype=np.int64)
    rank[has] = np.arange(int(has.sum()))
    joined = receptors.merge(
        pd.DataFrame(
            {
                "side": cols["side"].to_numpy(),
                "hex1": cols["hex1"].to_numpy(),
                "hex2": cols["hex2"].to_numpy(),
                "rank": rank,
            }
        ),
        on=["side", "hex1", "hex2"],
        how="inner",
    )
    joined = joined[joined["rank"] >= 0].sort_values("neuron", kind="mergesort")
    rows = joined["neuron"].to_numpy(np.int64)
    if rows.size == 0 or not np.array_equal(rows, np.unique(rows)):
        raise DNArenaError("photoreceptor rows are not strictly increasing")
    body_ids = tuple(int(v) for v in neurons_df["bodyId"].to_numpy()[rows])
    if any(body_ids[i] >= body_ids[i + 1] for i in range(len(body_ids) - 1)):
        raise DNArenaError("photoreceptor bodyIds are not aligned with row order")
    column_of_input = joined["rank"].to_numpy(np.int64)
    sides = tuple(side for side, keep in zip(columns.side, mask, strict=True) if keep)
    if column_of_input.min() < 0 or column_of_input.max() >= len(sides):
        raise DNArenaError("an input's column is outside the stimulus")
    mapping = neurons(doc)
    order = tuple(sorted(mapping))
    traced = []
    table = neurons_df["bodyId"].to_numpy()
    for body in order:
        hits = np.flatnonzero(table == body)
        if hits.size != 1:
            raise DNArenaError(f"decoder bodyId {body} is not one neuron")
        traced.append(int(hits[0]))
    traced_rows = np.asarray(traced, dtype=np.int64)
    if not np.array_equal(traced_rows, np.unique(traced_rows)):
        raise DNArenaError("decoder rows are not in CpuRuntime order")
    model = doc["model"]
    clock = Clock(
        neural_us=model["neural_us"],
        body_us=model["body_us"],
        control_us=model["control_us"],
        latency_us=model["latency_us"],
    )
    arena = _body(doc)
    state = arena.reset()
    mounts = pose.flygym_eye_mounts()
    z = float(np.mean([pose.eye_pose(state, mount).position_m[2] for mount in mounts]))
    xy = doc["stimulus"]["center_xy_m"]
    sphere = optics.Sphere(
        doc["stimulus"]["sphere"],
        (float(xy[0]), float(xy[1]), z),
        float(doc["stimulus"]["radius_m"]),
        (0.0, 0.0, 0.0),
    )
    registration = pose.Registration(
        pose.Pose("body", "eyemap", (0.0, 0.0, 0.0), pose.IDENTITY),
        doc["eye"]["registration"],
    )
    stimulus, optics_hash = closedloop.optical(
        columns,
        registration,
        mounts,
        (sphere,),
        float(doc["eye"]["acceptance_deg"]),
    )
    p = sim.Params()
    files = {
        "neurons": manifest.sha256_file(data_dir / "neurons.parquet"),
        "edges": manifest.sha256_file(data_dir / "edges.parquet"),
    }
    return Setup(
        doc,
        clock,
        model["duration_us"],
        tuple(doc["score"]["window_us"]),
        _proto(t4t5.assert_locked()),
        {
            "registration": doc["eye"]["registration_evidence"],
            "transducer": doc["pathway"]["evidence"],
            "motor_map": "unmapped",
            "body": doc["body"]["evidence"],
        },
        pose.Provenance(
            model["dataset"],
            runstore.digest(files),
            manifest.git_info()["commit"],
            doc["seed"],
        ),
        neurons_df,
        edges,
        p,
        sim.network(neurons_df, edges, p),
        rows,
        body_ids,
        column_of_input,
        traced_rows,
        order,
        stimulus,
        optics_hash,
        sides,
        out,
        execution_id,
        {},
    )


def _job(packed: tuple) -> list[dict]:
    setup = _resolve()
    key, kind, index, seed = packed
    if kind == "script":
        return [_script_job(setup)]
    cfg = configurations(setup.doc)[index]
    if kind == "arms":
        return [_arms_job(setup, key, cfg)]
    if kind == "wiring-null":
        return [_null_job(setup, key, cfg, seed)]
    raise DNArenaError(f"unknown job {kind}")


def _resolve() -> Setup:
    ctx, _checkpoint, _meta = parallel.context()
    if isinstance(ctx, Setup):
        return ctx
    global _SETUP
    if _SETUP is None:
        doc, neurons_df, edges, data_dir, out, execution_id = ctx
        _SETUP = build(doc, neurons_df, edges, data_dir, out, execution_id)
    return _SETUP


def _intact(setup: Setup, cfg: dict):
    """The intact graph's anchored pathway, once per configuration in this process."""
    index = cfg["index"]
    cached = setup.intact.get(index)
    if cached is None:
        static, built = pathway(
            setup.W, setup.neurons, cfg, setup.input_rows, setup.proto, setup.params
        )
        cached = (static, built, visual_pathway.config_hash(static, built))
        setup.intact[index] = cached
    return cached


def _arms_job(setup: Setup, key: str, cfg: dict) -> dict:
    _static, built, digest = _intact(setup, cfg)
    intact = None
    per_arm = {}
    for arm in _arm_order():
        record = _run_arm(
            setup, built, digest, arm, intact if arm == "replay" else None
        )
        if arm == "replay":
            closedloop.replay_parity(intact, record)
        per_arm[arm] = _closed_summary(setup, record, f"{key}__{arm}")
        if arm == "intact":
            intact = record
        else:
            del record
    del intact
    return _result(
        key=key,
        kind="arms",
        cfg=cfg,
        seed=None,
        yaw_change=None,
        spikes=None,
        record_sha256=None,
        arms=per_arm,
        replay_parity=True,
        pathway_sha256=digest,
    )


def _null_job(setup: Setup, key: str, cfg: dict, seed: int) -> dict:
    """Intact loop on a shuffled graph. Rate and drive gain stay the intact graph's."""
    _static, intact, _digest = _intact(setup, cfg)
    arena = _body(setup.doc)
    rate = (intact.rate_hz, intact.receiving)
    gain = intact.gain

    def runtime_from_edges(shuffled):
        weights = sim.network(setup.neurons, shuffled, setup.params)
        static, built = pathway(
            weights,
            setup.neurons,
            cfg,
            setup.input_rows,
            setup.proto,
            setup.params,
            rate=rate,
        )
        digest = visual_pathway.config_hash(static, built)
        runtime = cpu_runtime(
            built,
            setup.input_rows,
            steps=setup.duration_us // setup.clock.neural_us,
            p=setup.params,
            per_bin=setup.clock.control_us // setup.clock.neural_us,
            trace=setup.traced_rows,
            silence=False,
        )
        return runtime, digest

    control = arena_controls.wiring_null(
        arena,
        edges=setup.edges,
        seed=seed,
        runtime_from_edges=runtime_from_edges,
        decoder=_decoder(setup, arena),
        input_ids=setup.input_ids,
        traced_ids=setup.traced_ids,
        stimulus=setup.stimulus,
        transducer=_transducer(setup, gain),
        compiled=arena.compiled,
        clock=setup.clock,
        duration_us=setup.duration_us,
        mode="synthetic",
        evidence=setup.evidence,
        provenance=setup.provenance,
        optics_config_sha256=setup.optics_hash,
        run_identity_sha256=setup.execution_id,
        input_gap_steps=0,
        input_encoding="kick_equivalent",
    )
    summary_row = _closed_summary(setup, control.record, key, control)
    digest = control.record.pathway_sha256
    del control
    return _result(
        key=key,
        kind="wiring-null",
        cfg=cfg,
        seed=seed,
        yaw_change=summary_row["yaw_change"],
        spikes=summary_row["spikes"],
        record_sha256=summary_row["record_sha256"],
        arms=None,
        replay_parity=None,
        pathway_sha256=digest,
    )


def _script_job(setup: Setup) -> dict:
    arena = _body(setup.doc)
    record = arena_controls.script(
        arena,
        clock=setup.clock,
        duration_us=setup.duration_us,
        rule=_script_rule(setup.sides, arena.actuators),
        stimulus=setup.stimulus,
    )
    heading = np.array([tick.yaw_rad for tick in record.ticks], dtype=float)
    change = yaw_change(heading, setup.clock, setup.score_window)
    digest = _store(setup.out, "script", record)
    del record
    return _result(
        key="script",
        kind="script",
        cfg=None,
        seed=None,
        yaw_change=change,
        spikes=None,
        record_sha256=digest,
        arms=None,
        replay_parity=None,
        pathway_sha256=None,
    )


def _run_arm(setup: Setup, built, digest: str, arm: str, replay):
    arena = _body(setup.doc)
    return closedloop.run(
        cpu_runtime(
            built,
            setup.input_rows,
            steps=setup.duration_us // setup.clock.neural_us,
            p=setup.params,
            per_bin=setup.clock.control_us // setup.clock.neural_us,
            trace=setup.traced_rows,
            silence=(arm == "silenced"),
        ),
        arena,
        input_ids=setup.input_ids,
        traced_ids=setup.traced_ids,
        stimulus=setup.stimulus,
        transducer=_transducer(setup, built.gain),
        decoder=_decoder(setup, arena),
        compiled=arena.compiled,
        clock=setup.clock,
        duration_us=setup.duration_us,
        arm=arm,
        mode="synthetic",
        evidence=setup.evidence,
        provenance=setup.provenance,
        optics_config_sha256=setup.optics_hash,
        run_identity_sha256=setup.execution_id,
        input_gap_steps=0,
        input_encoding="kick_equivalent",
        pathway_sha256=digest,
        silenced_ids=setup.traced_ids if arm == "silenced" else (),
        replay=replay,
    )


def _decoder(setup: Setup, arena: Arena) -> Decoder:
    dec = setup.doc["decoder"]
    yaw = math.radians(dec["yaw_gain_deg_s_per_hz"])
    forward = dec["forward_gain_mm_s_per_hz"] / 1000.0
    return Decoder(
        gains={"DNa01": yaw, "DNa02": yaw, "oDN1": forward},
        window=tuple(dec["window_us"]),
        actuators=arena.actuators,
        clock=setup.clock,
        neurons=neurons(setup.doc),
    )


def _transducer(setup: Setup, gain: float):
    steps = setup.clock.body_us // setup.clock.neural_us
    return lambda coverage: drive(coverage, setup.column_of_input, gain, steps)


def _script_rule(sides, actuators):
    yaw_act, forward_act = actuators["yaw"], actuators["forward"]

    def rule(_time_us, _state, stim):
        left = right = 0.0
        for coverage, side in zip(stim, sides, strict=True):
            if side == "L":
                left += coverage
            elif side == "R":
                right += coverage
            else:
                raise DNArenaError(f"column side {side} is not L or R")
        if left > right:
            yaw = math.radians(100)
        elif right > left:
            yaw = -math.radians(100)
        else:
            yaw = 0.0
        return ((yaw_act, yaw), (forward_act, 0.01))

    return rule


def _closed_summary(setup: Setup, record, name: str, stored=None) -> dict:
    heading = heading_rad(record, setup.clock)
    kept = record if stored is None else stored
    return {
        "yaw_change": yaw_change(heading, setup.clock, setup.score_window),
        "spikes": _spike_counts(record, setup.traced_ids),
        "record_sha256": _store(setup.out, name, kept),
    }


def _spike_counts(record, body_ids: tuple[int, ...]) -> dict[str, int]:
    counts = {str(body): 0 for body in body_ids}
    for tick in record.ticks:
        for spike in tick.spikes:
            key = str(spike.neuron_id)
            if key not in counts:
                raise DNArenaError(
                    f"spike from {spike.neuron_id} is not a decoder neuron"
                )
            counts[key] += 1
    return counts


def _store(out: Path, name: str, record) -> str:
    """Write the record's canonical JSON gzipped (mtime 0, so the bytes are stable) and
    return the sha256 of that JSON."""
    encoded = record.to_json().encode()
    digest = hashlib.sha256(encoded).hexdigest()
    path = out / "records" / f"{name.replace('/', '__')}.json.gz"
    temporary = path.with_name(path.name + ".tmp")
    with (
        temporary.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream,
    ):
        stream.write(encoded)
    temporary.replace(path)
    return digest


def _result(
    *,
    key,
    kind,
    cfg,
    seed,
    yaw_change,
    spikes,
    record_sha256,
    arms,
    replay_parity,
    pathway_sha256,
):
    return {
        "key": key,
        "kind": kind,
        "index": None if cfg is None else cfg["index"],
        "photoreceptor_mv": None if cfg is None else cfg["photoreceptor_mv"],
        "lmc_mv": None if cfg is None else cfg["lmc_mv"],
        "lmc_rate_hz": None if cfg is None else cfg["lmc_rate_hz"],
        "medulla_rate_hz": None if cfg is None else cfg["medulla_rate_hz"],
        "lamina_medulla_gain": None if cfg is None else cfg["lamina_medulla_gain"],
        "seed": seed,
        "yaw_change": yaw_change,
        "spikes": spikes,
        "record_sha256": record_sha256,
        "arms": arms,
        "replay_parity": replay_parity,
        "pathway_sha256": pathway_sha256,
    }


def _body(doc: dict) -> Arena:
    body = doc["body"]
    return Arena(
        z_m=body["z_m"],
        roll_rad=body["roll_rad"],
        pitch_rad=body["pitch_rad"],
        source=body["source"],
    )


def _pack(job: dict) -> tuple:
    cfg = job.get("configuration")
    return (
        job["key"],
        job["kind"],
        None if cfg is None else cfg["index"],
        job.get("seed"),
    )


def _key(kind: str, index: int | None = None, seed: int | None = None) -> str:
    if kind == "script":
        return "script"
    if kind == "arms":
        return f"arms/{index}"
    if kind == "wiring-null":
        return f"wiring-null/{index}/{seed}"
    raise DNArenaError(f"unknown job {kind}")


def _arm_order() -> tuple[str, ...]:
    return tuple(arm for arm in closedloop.ARMS if arm != "replay") + ("replay",)


def _take(by: dict, key: str) -> dict:
    try:
        return by[key]
    except KeyError:
        raise DNArenaError(f"missing job {key}") from None


def _csv_value(value):
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def _window(name: str, window, duration: int, body_us: int) -> None:
    if type(window) is not list or len(window) != 2:
        raise DNArenaError(f"the {name} window is not a pair")
    start, end = window
    if type(start) is not int or type(end) is not int:
        raise DNArenaError(f"the {name} window is not integers")
    if not 0 <= start < end <= duration:
        raise DNArenaError(f"the {name} window is outside the duration")
    if start % body_us or end % body_us:
        raise DNArenaError(f"the {name} window is off the body grid")


def _gains_ok(doc: dict) -> None:
    dec = doc["decoder"]
    for name in ("yaw_gain_deg_s_per_hz", "forward_gain_mm_s_per_hz"):
        value = dec[name]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise DNArenaError(f"{name} is not one finite scalar")


def _score_ok(doc: dict) -> None:
    score = doc["score"]
    if score["metric"] != (
        "change in unwrapped heading (rad) from 200000 to 1000000 us"
    ):
        raise DNArenaError("the heading metric changed")
    if score["per_configuration"] != (
        "null if the intact change lies within the minimum and maximum of "
        "the 39 wiring-null changes at that configuration (inclusive); "
        "difference otherwise"
    ):
        raise DNArenaError("the per-configuration rule changed")
    if score["envelope"] != (
        "robust: <verdict> when every configuration has the same verdict; "
        "depends otherwise"
    ):
        raise DNArenaError("the envelope rule changed")
    if score["reported"] != (
        "per configuration: intact, disconnected, shuffled, replay, silenced "
        "and script changes, intact minus script, the wiring-null minimum, "
        "median and maximum, spikes of the six decoder neurons per arm, the "
        "pathway hash of the intact graph; replay parity is required"
    ):
        raise DNArenaError("the reported fields changed")
    if doc["no_go"] != (
        "a configuration is uninformative when the six decoder neurons fire "
        "no spike in its intact arm: the readout is then zero and the "
        "comparison empty. The envelope verdict is uninformative when every "
        "configuration is"
    ):
        raise DNArenaError("the no-go rule changed")


def _pathway_ok(doc: dict) -> None:
    path = doc["pathway"]
    try:
        locked = t4t5.assert_locked()
    except t4t5.T4T5Error as err:
        raise DNArenaError(str(err)) from err
    if locked["version"] != 4:
        raise DNArenaError("T4/T5 is not version 4")
    if path["t4t5_version"] != 4 or path["t4t5_sha256"] != t4t5.VERSION_HASHES[4]:
        raise DNArenaError("the pathway is not T4/T5 version 4")
    _proto(locked)
    env = locked["protocol"]["envelope"]
    photo = env["photoreceptor_response_mv"]
    hyper = env["lmc_hyperpolarisation_mv"]
    if (
        type(photo) is not list
        or len(photo) < 2
        or path["photoreceptor_response_mv"] != photo[1]
    ):
        raise DNArenaError("photoreceptor_response_mv is not the T4/T5 midpoint")
    if (
        type(hyper) is not list
        or len(hyper) < 2
        or path["lmc_hyperpolarisation_mv"] != hyper[1]
    ):
        raise DNArenaError("lmc_hyperpolarisation_mv is not the T4/T5 midpoint")
    if (
        type(env["lmc_rate_hz"]) is not list
        or path["lmc_rate_hz"] not in env["lmc_rate_hz"]
    ):
        raise DNArenaError("lmc_rate_hz is not in the T4/T5 envelope")
    if (
        type(env["medulla_rate_hz"]) is not list
        or path["medulla_rate_hz"] not in env["medulla_rate_hz"]
    ):
        raise DNArenaError("medulla_rate_hz is not in the T4/T5 envelope")
    if path["lamina_medulla_gain"] != env["lamina_medulla_gain"]:
        raise DNArenaError("lamina_medulla_gain is not the T4/T5 list")
    if path["drive_rule"] != (
        "drive per input and neural step = float32(gain * (1 - coverage of "
        "its column)), gain = visual_pathway.photoreceptor_gain("
        "photoreceptor_response_mv); constant over a body tick, from that "
        "tick's stimulus sample"
    ):
        raise DNArenaError("the drive rule changed")
    if path["dark_anchor"] != (
        "once per configuration and graph, open loop, before any closed-loop "
        "run on that graph: dark_anchor_passes passes of settle_ms in darkness "
        "(zero drive) through sim.run, exactly as T4/T5 version 4; the five "
        "arms share the intact graph's anchored pathway, each wiring-null run "
        "anchors on its own shuffled graph; every loop starts from a fresh "
        "state with the anchored release curve"
    ):
        raise DNArenaError("the dark anchor changed")
    if path["evidence"] != "engineered":
        raise DNArenaError("the pathway is not engineered")


def _proto(locked: dict) -> dict:
    """The T4/T5 version 4 fields the builder and the dark anchor read."""
    protocol = locked["protocol"]
    names = (
        "graded_lmc",
        "graded_medulla",
        "medulla_mv",
        "timing",
        "dark_anchor_passes",
        "settle_ms",
        "seed",
    )
    try:
        return {name: protocol[name] for name in names}
    except KeyError as err:
        raise DNArenaError(f"T4/T5 protocol is missing {err.args[0]}") from None


def _sha256_hex(value) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in _HEX for c in value):
        raise DNArenaError("the pathway hash is not sha256")
    return value


def _sphere_ok(stim: dict) -> None:
    xy, radius = stim["center_xy_m"], stim["radius_m"]
    if (
        type(xy) is not list
        or len(xy) != 2
        or any(type(v) not in (int, float) or not math.isfinite(float(v)) for v in xy)
    ):
        raise DNArenaError("the sphere centre is not a finite pair")
    if type(radius) not in (int, float) or not math.isfinite(radius) or radius <= 0:
        raise DNArenaError("the sphere radius is not positive")


def _body_ok(body: dict) -> None:
    if type(body["source"]) is not str or not body["source"]:
        raise DNArenaError("the body needs its kinematic source")
    for name in ("z_m", "roll_rad", "pitch_rad"):
        value = body[name]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise DNArenaError(f"body {name} is not finite")


def _mapped_inventory(text: str) -> dict[int, tuple[str, str]]:
    out: dict[int, tuple[str, str]] = {}
    header = None
    for line in text.splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells:
            continue
        if header is None:
            if cells[0] == "Type":
                header = cells
            continue
        if set(cells[0]) <= set("-: "):
            continue
        kind, status, male, body_s, side = (
            cells[0],
            cells[2],
            cells[3],
            cells[4],
            cells[5],
        )
        if status != "mapped" or kind not in ("DNa01", "DNa02", "oDN1"):
            continue
        if kind == "oDN1":
            if male != "DNg97":
                raise DNArenaError("oDN1 is not MaleCNS type DNg97")
        elif male != kind:
            raise DNArenaError(f"{kind} is not its MaleCNS type")
        if side not in ("L", "R"):
            raise DNArenaError(f"inventory side {side} is not L or R")
        body = int(body_s)
        if body in out:
            raise DNArenaError(f"inventory bodyId {body} is repeated")
        out[body] = (kind, side)
    if set(out.values()) != set(_PAIRS) or len(out) != len(_PAIRS):
        raise DNArenaError("the inventory does not map the six decoder neurons")
    return out


def _source_sha256(data_dir: Path) -> str:
    """Hash of the annotation table and the eyemap files, not the column frame."""
    names = {
        "annotations": data_dir / "raw" / data.RAW["annotations"],
        **{name: eye.raw_dir(data_dir) / name for name in eye.EYEMAP_FILES},
    }
    hashed = {name: manifest.sha256_file(path) for name, path in names.items()}
    return runstore.digest(hashed)
