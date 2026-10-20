"""Synthetic DN arena on the full MaleCNS (issue #263). The YAML file is the lock.

On the full connectome in a closed loop with a kinematic planar body, an engineered
descending-neuron readout and the graded visual pathway of T4/T5 version 4, driven
by a moving dark bar and its mirror: whether the intact graph's mirrored contrast
lies outside the range of 39 degree-preserving shuffles, at every pathway
configuration of the full input set. The paired-column set is the same score,
reported outside that claim. A difference is synthetic, not a biological or
connectome-derived mechanism. Versions 1 and 2 stay with their source commits.
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
    wiring,
)
from flymsg.arena import Arena
from flymsg.dn_decoder import SIDES, TYPES, Decoder
from flymsg.embodiment import Clock
from flymsg.paths import repository_root, require_repository_path
from flymsg.runtime import CpuRuntime

ROOT = repository_root()
PATH = ROOT / "validation" / "dn_arena.yaml"
INVENTORY = ROOT / "docs" / "dn-arena-inventory.md"

# Versions 1 and 2 name their source commits (docs/replication.md). This module
# implements version 3.
VERSION_HASHES = {
    1: "9ba9a69c8397fae5c6aa9ee60cd48147d4898110c2dbb22a2d461254b4583aa3",
    2: "1426386c66041510812bdcd6b3bfebb91d05a0811c5bfe33f9c191f3cd9a3ac7",
    3: "7ed0e04de84b9a584080021da2c5d4748d062e5af92327deab049b15ffbbea1c",
}

_PAIRS = tuple((kind, side) for kind in TYPES for side in SIDES)
_SETUP = None
_HEX = frozenset("0123456789abcdef")
_SIDES = ("left", "mirror")

content_hash = locks.content_hash


class DNArenaError(ValueError):
    """The DN arena protocol drifted from the locked version."""


def load(path: Path = PATH) -> dict:
    return locks.load(path)


def assert_locked(doc: dict | None = None) -> dict:
    doc = load() if doc is None else doc
    return locks.check(doc, VERSION_HASHES, DNArenaError, "DN arena protocol")


def assert_matches_code(doc: dict | None = None) -> dict:
    doc = assert_locked() if doc is None else doc
    if doc["version"] != 3:
        raise DNArenaError("this module implements DN arena version 3")
    _bind_lock(doc)
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
    _bar_consistent(doc["stimulus"], model["duration_us"])
    if doc["arms"] != list(closedloop.ARMS):
        raise DNArenaError("arms are not the closed-loop arms in order")
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
    eye_doc = doc["eye"]
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
    _body_ok(doc["body"])
    if (
        eye_doc["registration_evidence"] != "unmapped"
        or doc["stimulus"]["evidence"] != "engineered"
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


def _at(doc: dict, path: tuple[str, ...]):
    got = doc
    for key in path:
        got = got[key]
    return got


def _bind(doc: dict, path: tuple[str, ...], expected) -> None:
    if _at(doc, path) != expected:
        raise DNArenaError(f"{'.'.join(path)} changed")


def _bind_lock(doc: dict) -> None:
    """Every version-3 lock field, verbatim."""
    _bind(doc, ("seed",), 7210)
    _bind(
        doc,
        ("seed_note",),
        "the drive is deterministic (no Poisson draw); the seed orders the "
        "shuffled arm's ticks and is recorded",
    )
    _bind(
        doc,
        ("claim", "text"),
        "On the full MaleCNS v1.0 connectome in a closed loop with a kinematic "
        "planar body, an engineered descending-neuron readout and the graded "
        "visual pathway of T4/T5 version 4 driven by the moving dark bar of "
        "Collie et al.: does the intact graph's mirrored contrast, half the "
        "change in yaw under a bar sweeping on the left minus the change under "
        "its mirror image on the right, lie outside the range of the same "
        "contrast on 39 degree-preserving shuffles of the same graph, at every "
        "configuration of the pathway envelope? The contrast cancels turning "
        "that does not depend on the bar's side. A contrast outside that range "
        "is a synthetic difference, not a biological or connectome-derived "
        "mechanism.",
    )
    _bind(
        doc,
        ("seen_before_lock",),
        "Versions 1 and 2 of this lock ran (results/dn-arena/v1 uninformative, "
        "results/dn-arena/v2 depends; docs/result/dn-arena.md) and were read, "
        "with the version 2 post-verdict diagnostics (scripts/dn_arena_v2_*.py): "
        "the intact readout is switched on by light but barely follows a static "
        "sphere's side, the reconstruction has 2,251 right-eye and 1,652 "
        "left-eye input photoreceptors, the wiring nulls fire decoder neurons in "
        "darkness, and at lamina-to-medulla gain 1 the intact readout was "
        "silent. This version's score, stimulus, configurations and "
        "paired-column sensitivity set are chosen from that reading and from "
        "docs/plan/dn-arena-v3.md (accepted by the owner, #293). No bar stimulus "
        "has run on the full connectome before this lock except the timing smoke "
        "runs named in smoke, whose spikes, commands and heading were not read "
        "and whose records were deleted unread.",
    )
    _bind(doc, ("smoke",), "pending: timing only, filled in before owner approval")
    _bind(doc, ("stimulus", "object"), "bar")
    _bind(
        doc,
        ("stimulus", "source"),
        "Collie et al. 2025, bioRxiv 10.1101/2025.04.23.650240 v1 (Neuron 2026), "
        "STAR Methods: 'each pixel subtending ~1.5° of the animal's visual field "
        "and covering 48° in height and 336° in azimuth'; 'For visual object "
        "pursuit, the visual stimulus was a dark vertical bar (10.5°) on a "
        "bright background.'; 'an object appearing randomly every 3 s, sweeping "
        "22.5° at 25°/s or 75°/s, then disappearing (“motion pulses”), with "
        "motion paths tiling the front 100° of the visual field (for AOTU019) "
        "or the front 180° of the visual field (for AOTU025 and for behavior "
        "experiments in intact flies)'. Male flies walking on a ball; DNa02 "
        "right minus left responses (Fig. 2e, n = 11) predict rotational "
        "velocity (Fig. 2f, Fig. S4)",
    )
    _bind(doc, ("stimulus", "width_deg"), 10.5)
    _bind(doc, ("stimulus", "height_deg"), 48.0)
    _bind(
        doc,
        ("stimulus", "height_from"),
        "the panorama's 48° height; the bar's own height is not stated, so it "
        "is taken to span the panorama (an inference)",
    )
    _bind(doc, ("stimulus", "sweep_deg"), 22.5)
    _bind(doc, ("stimulus", "speed_deg_s"), 25.0)
    _bind(
        doc,
        ("stimulus", "speed_from"),
        "the slower of Collie et al.'s two speeds, the only one whose 22.5° "
        "sweep (0.9 s) fits the 1 s loop",
    )
    _bind(doc, ("stimulus", "visible_us"), [100000, 1000000])
    _bind(doc, ("stimulus", "left_sweep_body_azimuth_deg"), [-56.25, -33.75])
    _bind(doc, ("stimulus", "sides"), ["left", "mirror"])
    _bind(
        doc,
        ("stimulus", "side_rule"),
        "left: the bar's centre sweeps rightward (toward the midline) from body "
        "azimuth -56.25 to -33.75 degrees (left negative, as in optics) at the "
        "reset heading; mirror: the same sweep reflected across the sagittal "
        "plane, from +56.25 to +33.75 degrees moving leftward. Both are centred "
        "45 degrees off the midline, away from the zone where Collie et al.'s "
        "flies 'tended to follow the direction of motion' (Fig. 3a legend)",
    )
    _bind(
        doc,
        ("stimulus", "screen"),
        "optics.Bar on a vertical cylinder whose axis passes through the body's "
        "reset position; the bar moves in world coordinates, so the body's turns "
        "change its retinal position",
    )
    _bind(doc, ("stimulus", "screen_radius_m"), 0.1)
    _bind(
        doc,
        ("stimulus", "screen_radius_from"),
        "engineered: Collie et al. give angles, not a distance; 0.1 m keeps the "
        "eye mounts' parallax under 1 degree",
    )
    _bind(
        doc,
        ("stimulus", "vertical_centre"),
        "the mean world height of the two eye mounts at reset; the bar spans "
        "that height plus and minus screen_radius_m * tan(24 degrees)",
    )
    _bind(doc, ("stimulus", "quadrature"), [16, 24, 4.0])
    _bind(
        doc,
        ("stimulus", "quadrature_from"),
        "optics.bar_coverage: within the tested tolerance of a brute-force grid "
        "(tests/test_optics.py)",
    )
    _bind(
        doc,
        ("stimulus", "evidence_note"),
        "the bar's angles, speed and sweep are sourced (Collie et al.); its "
        "screen distance, vertical centre and the side positions are engineered",
    )
    _bind(doc, ("pathway", "input_sets"), ["all", "paired"])
    _bind(
        doc,
        ("pathway", "paired_rule"),
        "sensitivity set, reported outside the verdict: only the inputs whose "
        "column (side, hex1, hex2) has a mirror column (other side, same hex1 "
        "and hex2) with a viewing direction and at least one input; the mirror "
        "convention is eye.columns' (azimuth negated, elevation unchanged), a "
        "symmetry assumption (docs/reference/eye.md). The release rate is "
        "calibrated on that set",
    )
    _bind(
        doc,
        ("pathway", "imbalance"),
        "kept, not compensated: MaleCNS v1.0 reconstructs 2,474 right-eye and "
        "1,733 left-eye photoreceptors, a sample artefact per Berg et al. 2025 "
        "(bioRxiv 10.1101/2025.10.09.680999); no per-eye or per-column gain is "
        "applied",
    )
    _bind(
        doc,
        ("pathway", "inputs"),
        "every photoreceptor (R1-R6, R7, R8) that eye.photoreceptors assigns to "
        "a column with a viewing direction, both eyes; graded, non-spiking",
    )
    _bind(
        doc,
        ("pathway", "lit"),
        "the same inputs: the photoreceptor release rate is calibrated on all of "
        "them (visual_pathway.photoreceptor_rate), where T4/T5 version 4 "
        "calibrates on its stimulus window",
    )
    _bind(doc, ("pathway", "lamina_medulla_gain"), [4.0, 16.0])
    _bind(
        doc,
        ("pathway", "configurations_from"),
        "two of version 2's three configurations: gain 1 is left out because "
        "version 2's intact readout fired no spike there (results/dn-arena/v2); "
        "in T4/T5 version 4, T4 fired 35586 and 350264 spikes at gains 4 and 16 "
        "with LMC and medulla release 200 Hz (results/t4t5/v4 spikes.csv); "
        "response and hyperpolarisation at version 4's midpoints",
    )
    _bind(doc, ("controls", "wiring_null", "seed0"), 7400)
    _bind(doc, ("controls", "wiring_null", "seeds"), 39)
    _bind(
        doc,
        ("controls", "wiring_null", "rule"),
        "wiring.shuffle_targets on the MaleCNS edges, then the intact loop at "
        "that configuration and input set, once per side: the pathway is rebuilt "
        "on the shuffled graph by the same builder (timing scale and lamina to "
        "medulla gain by type, graded release by type) and dark-anchored on it "
        "once, shared by both sides; the photoreceptor release rate and the "
        "drive gain are those of the intact graph with the same input set, a "
        "calibration of the stimulus, not of the network",
    )
    _bind(
        doc,
        ("controls", "script", "rule"),
        "yaw +100 deg/s toward the eye with the larger summed coverage "
        "(left positive), 0 when equal; forward 10 mm/s; "
        "from the previous control tick's sample; run for each side",
    )
    _bind(
        doc,
        ("score", "metric"),
        "change in unwrapped heading (rad) from 200000 to 1000000 us",
    )
    _bind(
        doc,
        ("score", "contrast"),
        "per graph, configuration and input set: (change under left - change "
        "under mirror) / 2, both runs from fresh states on the same anchored "
        "pathway",
    )
    _bind(
        doc,
        ("score", "expected_sign"),
        "positive: toward the bar, a left turn for the left side ('flies turned "
        "toward the object's position', Collie et al. Fig. 3a legend); a "
        "difference with a negative contrast is reported as a difference of the "
        "wrong sign",
    )
    _bind(
        doc,
        ("score", "per_configuration"),
        "null if the intact contrast lies within the minimum and maximum of "
        "the 39 wiring-null contrasts at that configuration and input set "
        "(inclusive); difference otherwise",
    )
    _bind(
        doc,
        ("score", "envelope"),
        "on the all input set: robust: <verdict> when every configuration has "
        "the same verdict; depends otherwise. The paired set gets the same "
        "verdicts, reported as a sensitivity analysis outside the claim",
    )
    _bind(
        doc,
        ("score", "reported"),
        "per configuration, input set and side: intact, disconnected, shuffled, "
        "replay, silenced and script changes, spikes of the six decoder neurons "
        "per arm; per configuration and input set: the intact contrast, the "
        "wiring-null contrasts' minimum, median and maximum, the pathway hash "
        "of the intact graph; replay parity is required",
    )
    _bind(
        doc,
        ("no_go",),
        "a configuration is uninformative for an input set when the six decoder "
        "neurons fire no spike in its intact arm on either side. The envelope "
        "verdict is uninformative when every configuration is",
    )
    _bind(
        doc,
        ("limits",),
        [
            (
                "Synthetic: every component carries its status from the DN-arena ADR "
                "and graded eye ADR evidence tables; a biological run still refuses."
            ),
            (
                "The graded pathway is T4/T5 version 4's, whose own verdict is "
                "robust neither: graded transport is not visual selectivity."
            ),
            (
                "Eyemap to body registration is a test-only identity (#179); eye "
                "mounts are NeuroMechFly's."
            ),
            "A planar kinematic body: no legs, no physics, no flight.",
            (
                "One bar sweep per side, one decoder cell and one duration; two "
                "pathway configurations chosen from read results."
            ),
            (
                "Collie et al.'s flies were aroused by optogenetic P1 activation; "
                "the model has no arousal state."
            ),
            (
                "The graded pathway has no direction selectivity (T4/T5 version 4): "
                "the bar can act through position and luminance only."
            ),
            (
                "Host only: kick_equivalent input does not run on the console "
                "(graded eye ADR Decision 5)."
            ),
        ],
    )
    _bind(
        doc,
        ("content_sha256",),
        "7ed0e04de84b9a584080021da2c5d4748d062e5af92327deab049b15ffbbea1c",
    )
    _bind(doc, ("yaml_subset",), 2)
    _bind(
        doc,
        ("evidence_none",),
        "A synthetic milestone (DN-arena ADR, graded eye ADR): no recording is "
        "scored and validation/evidence.yaml is not edited. The sources behind "
        "the decoder's sign are cited under decoder and in docs/leads.md; the "
        "graded pathway's sources are those of validation/t4t5.yaml version 4.",
    )
    _bind(doc, ("issue",), 263)
    _bind(doc, ("model", "body_us"), 1000)
    _bind(doc, ("model", "control_us"), 10000)
    _bind(doc, ("model", "latency_us"), 0)
    _bind(doc, ("model", "duration_us"), 1000000)
    _bind(
        doc,
        ("model", "input_encoding_from"),
        "graded eye ADR Decision 1: the photoreceptor drive is the real-valued "
        "kick-equivalent of T4/T5 version 4, no Poisson draw; the input dead "
        "time does not apply (input_gap_steps 0)",
    )
    _bind(
        doc,
        ("body", "source"),
        "flymsg.arena kinematic planar body (DN-arena ADR)",
    )
    _bind(doc, ("body", "z_m"), 0.0)
    _bind(doc, ("body", "roll_rad"), 0.0)
    _bind(doc, ("body", "pitch_rad"), 0.0)
    _bind(
        doc,
        ("eye", "acceptance_from"),
        "Gonzalez-Bellido, Wardill & Juusola 2011, PNAS 108:4224, Fig 3A (as "
        "in validation/t4t5.yaml)",
    )
    _bind(
        doc,
        ("pathway", "source"),
        "validation/t4t5.yaml version 4: graded_lmc, graded_medulla, "
        "medulla_mv, timing, dark_anchor_passes and settle_ms are taken from "
        "that lock; the code refuses to run when it is not that version or its "
        "hash differs",
    )
    _bind(
        doc,
        ("pathway", "builder"),
        "flymsg.visual_pathway.prepare and build (vee1-1), bit-identical to "
        "T4/T5 version 4 for its own configurations",
    )
    _bind(doc, ("pathway", "lmc_rate_hz"), 200.0)
    _bind(doc, ("pathway", "medulla_rate_hz"), 200.0)
    _bind(
        doc,
        ("decoder", "neurons"),
        [
            "10442 DNa01 L",
            "10760 DNa01 R",
            "523769 DNa02 L",
            "10360 DNa02 R",
            "13805 oDN1 L",
            "230783 oDN1 R",
        ],
    )
    _bind(
        doc,
        ("decoder", "neurons_from"),
        "docs/dn-arena-inventory.md (MaleCNS v1.0 annotation table, sha256 "
        "2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2); "
        "oDN1 is MaleCNS type DNg97",
    )
    _bind(
        doc,
        ("decoder", "sign_from"),
        "ipsilateral steering: 'Both cells are depolarized just before the fly "
        "steers in the ipsilateral direction' (Rayshubskiy et al., bioRxiv "
        "10.1101/2020.04.04.024703 v4, Fig 1D legend); 'the cell with a soma in "
        "the right hemisphere was more active during right turns, and vice "
        "versa' (Yang et al., bioRxiv 10.1101/2023.10.15.562426 v1, Fig 2A)",
    )
    _bind(
        doc,
        ("decoder", "linear_from"),
        "'rotational velocity was consistently related to the difference in "
        "right-left firing rates' and 'This relationship was essentially "
        "linear through its entire dynamic range' (Rayshubskiy et al. v4, "
        "Fig 3B-C)",
    )
    _bind(doc, ("decoder", "yaw_gain_deg_s_per_hz"), 2.0)
    _bind(doc, ("decoder", "forward_gain_mm_s_per_hz"), 0.2)
    _bind(
        doc,
        ("decoder", "gains_from"),
        "one cell of version 1's engineered envelope (its middle yaw gain and "
        "its larger forward gain), chosen by the owner to bound cost; no "
        "source states a numeric gain. Gains are not evidence and do not enter "
        "validation/evidence.yaml",
    )
    _bind(doc, ("decoder", "window_us"), [0, 1000000])
    _bind(doc, ("score", "window_us"), [200000, 1000000])
    _bind(
        doc,
        ("data_rule",),
        "a null, a difference or an uninformative outcome is archived as it is "
        "and not rerun with new configurations, gains, geometry or seeds",
    )


def _bar_consistent(stim: dict, duration: int) -> None:
    start, end = stim["visible_us"]
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= duration
    ):
        raise DNArenaError("the bar is not inside the duration")
    lo, hi = stim["left_sweep_body_azimuth_deg"]
    if not math.isclose(abs(hi - lo), float(stim["sweep_deg"])):
        raise DNArenaError("the sweep does not match its endpoints")
    seconds = (end - start) / 1_000_000
    if not math.isclose(float(stim["sweep_deg"]), float(stim["speed_deg_s"]) * seconds):
        raise DNArenaError("the sweep does not match the speed over the visible window")
    quad = stim["quadrature"]
    if (
        type(quad) is not list
        or len(quad) != 3
        or type(quad[0]) is not int
        or type(quad[1]) is not int
        or type(quad[2]) is not float
    ):
        raise DNArenaError("quadrature is not (n_radial, n_angular, max_sigma)")


def summary(doc: dict | None = None) -> str:
    doc = assert_matches_code() if doc is None else doc
    model, wn = doc["model"], doc["controls"]["wiring_null"]
    return (
        f"dn_arena v{doc['version']} (issue #{doc['issue']}): "
        f"{len(doc['pathway']['input_sets'])} input sets, "
        f"{len(configurations(doc))} configurations, "
        f"{len(doc['stimulus']['sides'])} sides, "
        f"{len(doc['arms'])} arms, "
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
    """Per input set and configuration: both sides' arms, then the nulls.

    The script has no connectome, so it is one job per side, after every set.
    `cfg` in a key is the configuration index.
    """
    order = _arm_order()
    wn = doc["controls"]["wiring_null"]
    seeds = range(wn["seed0"], wn["seed0"] + wn["seeds"])
    out = []
    for name in doc["pathway"]["input_sets"]:
        for cfg in configurations(doc):
            index = cfg["index"]
            for side in doc["stimulus"]["sides"]:
                out.append(
                    {
                        "key": f"arms/{name}/{index}/{side}",
                        "kind": "arms",
                        "input_set": name,
                        "side": side,
                        "configuration": cfg,
                        "arms": list(order),
                    }
                )
            for seed in seeds:
                out.append(
                    {
                        "key": f"wiring-null/{name}/{index}/{seed}",
                        "kind": "wiring-null",
                        "input_set": name,
                        "configuration": cfg,
                        "seed": seed,
                    }
                )
    for side in doc["stimulus"]["sides"]:
        out.append({"key": f"script/{side}", "kind": "script", "side": side})
    return out


def directed_inputs(columns: pd.DataFrame, receptors: pd.DataFrame) -> pd.DataFrame:
    """Photoreceptors on columns with a viewing direction, in neuron order.

    `rank` indexes the stimulus vector: columns whose azimuth and elevation are
    both present, in `columns` order, which is the order `optical_bars` returns.
    """
    has = (
        columns["azimuth_deg"].notna().to_numpy()
        & columns["elevation_deg"].notna().to_numpy()
    )
    rank = np.full(len(columns), -1, dtype=np.int64)
    rank[has] = np.arange(int(has.sum()))
    table = pd.DataFrame(
        {
            "side": columns["side"].to_numpy(),
            "hex1": columns["hex1"].to_numpy(),
            "hex2": columns["hex2"].to_numpy(),
            "rank": rank,
        }
    )
    joined = receptors.merge(table, on=["side", "hex1", "hex2"], how="inner")
    joined = joined[joined["rank"] >= 0]
    return joined.sort_values("neuron", kind="mergesort").reset_index(drop=True)


def paired_inputs(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows whose column has a mirror column in `frame`.

    `frame` is already the inputs on columns with a viewing direction. A mirror
    is the other side and the same hex1 and hex2, so a row of `frame` is a
    mirror column with a viewing direction and at least one input.
    """
    need = {"side", "hex1", "hex2"}
    if not need <= set(frame.columns):
        raise DNArenaError("paired inputs need side, hex1 and hex2")
    keys = frame.loc[:, ["side", "hex1", "hex2"]].drop_duplicates()
    flipped = keys.copy()
    flipped["side"] = flipped["side"].map({"L": "R", "R": "L"})
    if flipped["side"].isna().any():
        raise DNArenaError("a column side is not L or R")
    mirrored = keys.merge(flipped, on=["side", "hex1", "hex2"], how="inner")
    marked = frame.merge(
        mirrored.assign(_paired=True), on=["side", "hex1", "hex2"], how="left"
    )
    keep = marked["_paired"].fillna(False).astype(bool)
    return marked.loc[keep].drop(columns="_paired").reset_index(drop=True)


def _heading_deg(state: pose.BodyState) -> float:
    """Heading of the body's +x, degrees, counterclockwise from world +x."""
    x, y, _z = state.pose.orientation.rotate((1.0, 0.0, 0.0))
    return math.degrees(math.atan2(y, x))


def _body_sweep(stim: dict, side: str) -> tuple[float, float]:
    """Body azimuth of the bar centre at the start and end of the sweep.

    Left is negative, as in `optics`. Mirror negates that sweep.
    """
    lo, hi = stim["left_sweep_body_azimuth_deg"]
    if side == "left":
        return float(lo), float(hi)
    if side == "mirror":
        return -float(lo), -float(hi)
    raise DNArenaError(f"unknown side {side}")


def bars(doc: dict, state: pose.BodyState, mounts) -> dict[str, optics.Bar]:
    """One `optics.Bar` per side, fixed in world coordinates at the reset pose.

    Body azimuth is positive to the fly's right. World azimuth is
    counterclockwise from world +x toward +y. At heading 0 those are opposites,
    so body azimuth -45 degrees is world azimuth +45 degrees, and a rightward
    sweep (body azimuth increasing) is a negative world angular velocity. The
    cylinder axis is the reset position and does not follow the body; the
    bar's later retinal position therefore moves when the body turns. The bar
    spans the eye-mount mean height by `screen_radius_m * tan(height_deg / 2)`.
    """
    stim = doc["stimulus"]
    radius = float(stim["screen_radius_m"])
    heights = [float(pose.eye_pose(state, mount).position_m[2]) for mount in mounts]
    centre = float(np.mean(heights))
    half = radius * math.tan(math.radians(float(stim["height_deg"]) / 2.0))
    axis = state.pose.position_m
    heading = _heading_deg(state)
    visible = (stim["visible_us"][0], stim["visible_us"][1])
    speed = float(stim["speed_deg_s"])
    out = {}
    for side in stim["sides"]:
        start, end = _body_sweep(stim, side)
        body_rate = speed if end > start else -speed
        out[side] = optics.Bar(
            name=side,
            axis_xy_m=(float(axis[0]), float(axis[1])),
            screen_radius_m=radius,
            z_bottom_m=centre - half,
            z_top_m=centre + half,
            width_deg=float(stim["width_deg"]),
            azimuth0_deg=heading - start,
            angular_velocity_deg_s=-body_rate,
            visible_us=visible,
        )
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


def contrast(left: float, mirror: float) -> float:
    """Half the left-minus-mirror heading change."""
    return (float(left) - float(mirror)) / 2.0


def record_names(row: dict) -> dict[str, str]:
    """The stored record name and canonical-JSON sha256 behind one job's result."""
    if row["kind"] == "arms":
        return {
            f"{row['key']}__{arm}": summary["record_sha256"]
            for arm, summary in row["arms"].items()
        }
    if row["kind"] == "wiring-null":
        saved = row["record_sha256"]
        if type(saved) is not dict:
            raise DNArenaError("a wiring-null record names both sides")
        return {f"{row['key']}__{side}": saved[side] for side in saved}
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


def _observed_sign(value: float) -> str:
    if value > 0.0:
        return "positive"
    if value < 0.0:
        return "negative"
    return "zero"


def _verdict_label(value: float, lo: float, hi: float, silent: bool) -> str:
    if silent:
        return "uninformative"
    if lo <= value <= hi:
        return "null"
    if value < 0.0:
        return "difference (wrong sign)"
    return "difference"


def _envelope(labels: list[str]) -> str:
    if set(labels) == {"uninformative"}:
        return "uninformative"
    if len(set(labels)) == 1:
        return f"robust: {labels[0]}"
    return "depends"


def verdict(results: list[dict], doc: dict) -> dict:
    """Per configuration and input set: no-go, or the inclusive null range.

    The envelope reads the `all` set only. The `paired` set is `sensitivity`.
    """
    by: dict[str, dict] = {}
    for row in results:
        if row["key"] in by:
            raise DNArenaError(f"duplicate job {row['key']}")
        by[row["key"]] = row
    sides = list(doc["stimulus"]["sides"])
    scripts = {side: float(_take(by, f"script/{side}")["yaw_change"]) for side in sides}
    wn = doc["controls"]["wiring_null"]
    seeds = range(wn["seed0"], wn["seed0"] + wn["seeds"])
    ids = [str(body) for body in sorted(neurons(doc))]
    grouped: dict[str, list] = {name: [] for name in doc["pathway"]["input_sets"]}
    for name in doc["pathway"]["input_sets"]:
        for cfg in configurations(doc):
            grouped[name].append(
                _score_configuration(by, doc, cfg, name, sides, scripts, seeds, ids)
            )
    return {
        "configurations": grouped["all"],
        "sensitivity": grouped["paired"],
        "envelope": _envelope([row["verdict"] for row in grouped["all"]]),
    }


def _score_configuration(by, doc, cfg, name, sides, scripts, seeds, ids) -> dict:
    index = cfg["index"]
    arms = {}
    digests = []
    for side in sides:
        row = _take(by, f"arms/{name}/{index}/{side}")
        if row.get("replay_parity") is not True:
            raise DNArenaError("replay parity is required")
        digests.append(_sha256_hex(row.get("pathway_sha256")))
        per_arm = row["arms"]
        for arm in _arm_order():
            if arm not in per_arm:
                raise DNArenaError(f"missing arm {arm}")
        spikes = per_arm["intact"]["spikes"]
        if set(spikes) != set(ids):
            raise DNArenaError("intact spikes must name the six decoder neurons")
        arms[side] = per_arm
    if len(set(digests)) != 1:
        raise DNArenaError("the two sides do not share a pathway")
    intact = {
        side: contrast_value
        for side, contrast_value in (
            (side, float(arms[side]["intact"]["yaw_change"])) for side in sides
        )
    }
    value = contrast(intact["left"], intact["mirror"])
    nulls = np.array(
        [
            contrast(*_null_yaw(_take(by, f"wiring-null/{name}/{index}/{seed}")))
            for seed in seeds
        ]
    )
    lo, hi = float(nulls.min()), float(nulls.max())
    silent = all(sum(arms[side]["intact"]["spikes"].values()) == 0 for side in sides)
    label = _verdict_label(value, lo, hi, silent)
    sign = _observed_sign(value)
    return {
        "index": index,
        "input_set": name,
        "photoreceptor_mv": cfg["photoreceptor_mv"],
        "lmc_mv": cfg["lmc_mv"],
        "lmc_rate_hz": cfg["lmc_rate_hz"],
        "medulla_rate_hz": cfg["medulla_rate_hz"],
        "lamina_medulla_gain": cfg["lamina_medulla_gain"],
        "verdict": label,
        "expected_sign": "positive",
        "contrast_sign": sign,
        "expected_sign_met": sign == "positive",
        "contrast": value,
        "sides": {
            side: {
                "intact": float(arms[side]["intact"]["yaw_change"]),
                "disconnected": float(arms[side]["disconnected"]["yaw_change"]),
                "shuffled": float(arms[side]["shuffled"]["yaw_change"]),
                "replay": float(arms[side]["replay"]["yaw_change"]),
                "silenced": float(arms[side]["silenced"]["yaw_change"]),
                "script": scripts[side],
                "spikes": {arm: arms[side][arm]["spikes"] for arm in _arm_order()},
            }
            for side in sides
        },
        "wiring_null_minimum": lo,
        "wiring_null_median": float(np.median(nulls)),
        "wiring_null_maximum": hi,
        "pathway_sha256": digests[0],
        "replay_parity": True,
    }


def _null_yaw(row: dict) -> tuple[float, float]:
    yaw = row["yaw_change"]
    if type(yaw) is not dict or set(yaw) != set(_SIDES):
        raise DNArenaError("a wiring-null yaw names both sides")
    return float(yaw["left"]), float(yaw["mirror"])


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
class Inputs:
    name: str
    rows: np.ndarray
    ids: tuple[int, ...]
    column_of_input: np.ndarray


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
    inputs: dict[str, Inputs]
    traced_rows: np.ndarray
    traced_ids: tuple[int, ...]
    stimuli: dict
    optics: dict[str, str]
    column_sides: tuple[str, ...]
    out: Path
    execution_id: str
    intact: dict


def build(doc, neurons_df, edges, data_dir, out, execution_id: str) -> Setup:
    """The loop shared by every job. The optical callables stay in this process."""
    data_dir, out = Path(data_dir), Path(out)
    eye.fetch(data_dir)
    ann = pd.read_feather(
        data_dir / "raw" / data.RAW["annotations"],
        columns=["bodyId", "type", "instance", "assignedOlHex1", "assignedOlHex2"],
    )
    cols = eye.columns(ann, eye.lenses(data_dir))
    receptors = eye.photoreceptors(neurons_df, edges, ann)
    columns = optics.Columns.from_frame(cols, _source_sha256(data_dir))
    joined = directed_inputs(cols, receptors)
    has = (
        cols["azimuth_deg"].notna().to_numpy()
        & cols["elevation_deg"].notna().to_numpy()
    )
    mask = np.isfinite(columns.direction).all(axis=1)
    if not np.array_equal(has, mask):
        raise DNArenaError("column directions do not match the lens table")
    if joined.empty:
        raise DNArenaError("no photoreceptor has a viewing direction")
    made = _input_sets(doc, joined, neurons_df, int(has.sum()))
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
    registration = pose.Registration(
        pose.Pose("body", "eyemap", (0.0, 0.0, 0.0), pose.IDENTITY),
        doc["eye"]["registration"],
    )
    quad = tuple(doc["stimulus"]["quadrature"])
    acceptance = float(doc["eye"]["acceptance_deg"])
    stimuli, optics_hashes = {}, {}
    for side, bar in bars(doc, state, mounts).items():
        stimulus, digest = closedloop.optical_bars(
            columns, registration, mounts, (bar,), acceptance, quad
        )
        stimuli[side] = stimulus
        optics_hashes[side] = digest
    p = sim.Params()
    files = {
        "neurons": manifest.sha256_file(data_dir / "neurons.parquet"),
        "edges": manifest.sha256_file(data_dir / "edges.parquet"),
    }
    column_sides = tuple(
        side for side, keep in zip(columns.side, mask, strict=True) if keep
    )
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
        made,
        traced_rows,
        order,
        stimuli,
        optics_hashes,
        column_sides,
        out,
        execution_id,
        {},
    )


def _input_sets(doc, joined, neurons_df, n_columns: int) -> dict[str, Inputs]:
    table = neurons_df["bodyId"].to_numpy()
    made = {}
    for name in doc["pathway"]["input_sets"]:
        chosen = joined if name == "all" else paired_inputs(joined)
        rows = chosen["neuron"].to_numpy(np.int64)
        if rows.size == 0 or not np.array_equal(rows, np.unique(rows)):
            raise DNArenaError(
                f"input set {name} photoreceptor rows are not strictly increasing"
            )
        body_ids = tuple(int(v) for v in table[rows])
        if any(body_ids[i] >= body_ids[i + 1] for i in range(len(body_ids) - 1)):
            raise DNArenaError(
                f"input set {name} photoreceptor bodyIds are not aligned with row order"
            )
        column_of_input = chosen["rank"].to_numpy(np.int64)
        if column_of_input.min() < 0 or column_of_input.max() >= n_columns:
            raise DNArenaError("an input's column is outside the stimulus")
        made[name] = Inputs(name, rows, body_ids, column_of_input)
    return made


def _job(packed: tuple) -> list[dict]:
    setup = _resolve()
    key, kind, input_set, index, side, seed = packed
    if kind == "script":
        return [_script_job(setup, side)]
    cfg = configurations(setup.doc)[index]
    if kind == "arms":
        return [_arms_job(setup, key, cfg, input_set, side)]
    if kind == "wiring-null":
        return [_null_job(setup, key, cfg, input_set, seed)]
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


def _intact(setup: Setup, cfg: dict, name: str):
    """The intact graph's anchored pathway, once per input set and configuration."""
    key = (name, cfg["index"])
    cached = setup.intact.get(key)
    if cached is None:
        static, built = pathway(
            setup.W,
            setup.neurons,
            cfg,
            setup.inputs[name].rows,
            setup.proto,
            setup.params,
        )
        cached = (static, built, visual_pathway.config_hash(static, built))
        setup.intact[key] = cached
    return cached


def _arms_job(setup: Setup, key: str, cfg: dict, name: str, side: str) -> dict:
    _static, built, digest = _intact(setup, cfg, name)
    inputs = setup.inputs[name]
    intact = None
    per_arm = {}
    for arm in _arm_order():
        record = _run_arm(
            setup,
            built,
            digest,
            arm,
            intact if arm == "replay" else None,
            inputs,
            side,
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
        input_set=name,
        side=side,
        cfg=cfg,
        seed=None,
        yaw_change=None,
        spikes=None,
        record_sha256=None,
        arms=per_arm,
        replay_parity=True,
        pathway_sha256=digest,
    )


def _null_job(setup: Setup, key: str, cfg: dict, name: str, seed: int) -> dict:
    """Both sides on one shuffled pathway, dark-anchored once. Fresh state each side.

    Rate and drive gain stay the intact graph's for this input set.
    """
    _static, intact, _digest = _intact(setup, cfg, name)
    inputs = setup.inputs[name]
    rate = (intact.rate_hz, intact.receiving)
    gain = intact.gain
    shuffled, stats = wiring.shuffle_targets(setup.edges, seed)
    weights = sim.network(setup.neurons, shuffled, setup.params)
    static, built = pathway(
        weights,
        setup.neurons,
        cfg,
        inputs.rows,
        setup.proto,
        setup.params,
        rate=rate,
    )
    digest = visual_pathway.config_hash(static, built)
    per_side = {}
    for side in setup.doc["stimulus"]["sides"]:
        arena = _body(setup.doc)
        record = closedloop.run(
            cpu_runtime(
                built,
                inputs.rows,
                steps=setup.duration_us // setup.clock.neural_us,
                p=setup.params,
                per_bin=setup.clock.control_us // setup.clock.neural_us,
                trace=setup.traced_rows,
                silence=False,
            ),
            arena,
            input_ids=inputs.ids,
            traced_ids=setup.traced_ids,
            stimulus=setup.stimuli[side],
            transducer=_transducer(setup, gain, inputs.column_of_input),
            decoder=_decoder(setup, arena),
            compiled=arena.compiled,
            clock=setup.clock,
            duration_us=setup.duration_us,
            arm="intact",
            mode="synthetic",
            evidence=setup.evidence,
            provenance=setup.provenance,
            optics_config_sha256=setup.optics[side],
            run_identity_sha256=setup.execution_id,
            input_gap_steps=0,
            input_encoding="kick_equivalent",
            pathway_sha256=digest,
        )
        control = arena_controls.WiringNullControl(
            arena_controls.WIRING_NULL,
            seed,
            record,
            stats,
            {"control": arena_controls.WIRING_NULL, "shuffle_seed": seed},
        )
        per_side[side] = _closed_summary(setup, record, f"{key}__{side}", control)
        del record, control
    return _result(
        key=key,
        kind="wiring-null",
        input_set=name,
        side=None,
        cfg=cfg,
        seed=seed,
        yaw_change={side: per_side[side]["yaw_change"] for side in per_side},
        spikes={side: per_side[side]["spikes"] for side in per_side},
        record_sha256={side: per_side[side]["record_sha256"] for side in per_side},
        arms=None,
        replay_parity=None,
        pathway_sha256=digest,
    )


def _script_job(setup: Setup, side: str) -> dict:
    arena = _body(setup.doc)
    record = arena_controls.script(
        arena,
        clock=setup.clock,
        duration_us=setup.duration_us,
        rule=_script_rule(setup.column_sides, arena.actuators),
        stimulus=setup.stimuli[side],
    )
    heading = np.array([tick.yaw_rad for tick in record.ticks], dtype=float)
    change = yaw_change(heading, setup.clock, setup.score_window)
    digest = _store(setup.out, f"script/{side}", record)
    del record
    return _result(
        key=f"script/{side}",
        kind="script",
        input_set=None,
        side=side,
        cfg=None,
        seed=None,
        yaw_change=change,
        spikes=None,
        record_sha256=digest,
        arms=None,
        replay_parity=None,
        pathway_sha256=None,
    )


def _run_arm(
    setup: Setup, built, digest: str, arm: str, replay, inputs: Inputs, side: str
):
    arena = _body(setup.doc)
    return closedloop.run(
        cpu_runtime(
            built,
            inputs.rows,
            steps=setup.duration_us // setup.clock.neural_us,
            p=setup.params,
            per_bin=setup.clock.control_us // setup.clock.neural_us,
            trace=setup.traced_rows,
            silence=(arm == "silenced"),
        ),
        arena,
        input_ids=inputs.ids,
        traced_ids=setup.traced_ids,
        stimulus=setup.stimuli[side],
        transducer=_transducer(setup, built.gain, inputs.column_of_input),
        decoder=_decoder(setup, arena),
        compiled=arena.compiled,
        clock=setup.clock,
        duration_us=setup.duration_us,
        arm=arm,
        mode="synthetic",
        evidence=setup.evidence,
        provenance=setup.provenance,
        optics_config_sha256=setup.optics[side],
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


def _transducer(setup: Setup, gain: float, column_of_input):
    steps = setup.clock.body_us // setup.clock.neural_us
    return lambda coverage: drive(coverage, column_of_input, gain, steps)


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
    input_set,
    side,
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
        "input_set": input_set,
        "side": side,
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
        job.get("input_set"),
        None if cfg is None else cfg["index"],
        job.get("side"),
        job.get("seed"),
    )


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
    if any(
        gain not in env["lamina_medulla_gain"] for gain in path["lamina_medulla_gain"]
    ):
        raise DNArenaError("a lamina_medulla_gain is outside the T4/T5 envelope")
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
