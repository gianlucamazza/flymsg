"""The flymsg command line: dispatch, error handling and the command table.

The commands live in modules by area (connectome, simulate, validation, experiments,
body, sensory); the parser is in `parser`.
"""

import sys

from flymsg import (
    apl_claws,
    baselines,
    behavior,
    benchmarks,
    convergence,
    data,
    dimorphism,
    draws,
    gf_looming,
    intervention,
    jump3d_lock,
    kc_sparseness,
    managed,
    manifest,
    partner_followup,
    plasticity,
    prereg,
    sensitivity,
    silence_scan,
    sim,
    song,
    t4t5,
    validate,
    viz,
    weight_rule,
    workbench,
)
from flymsg.cli.body import cmd_behavior, cmd_jump, cmd_jump3d, cmd_loop, cmd_muscles
from flymsg.cli.common import label, ng_link
from flymsg.cli.connectome import (
    audit_focus_types,
    cmd_audit,
    cmd_compare,
    cmd_dimorphism,
    cmd_homology,
    cmd_info,
    cmd_path,
    cmd_weight_rule,
)
from flymsg.cli.experiments import (
    cmd_confirm,
    cmd_experiment,
    cmd_explore,
    cmd_partner_followup,
    cmd_silence_scan,
)
from flymsg.cli.parser import build_parser
from flymsg.cli.sensory import (
    cmd_eye,
    cmd_kc_sparseness,
    cmd_mb_plasticity,
    cmd_odor,
    cmd_t4t5,
)
from flymsg.cli.simulate import cmd_calibrate, cmd_sim, cmd_trace, cmd_viz, summarize
from flymsg.cli.validation import (
    cmd_apl_claws,
    cmd_baselines,
    cmd_benchmarks,
    cmd_convergence,
    cmd_gf_looming,
    cmd_nulls,
    cmd_select_model,
    cmd_sensitivity,
    cmd_song,
    cmd_validate,
    cmd_wiring_null,
)

# the public surface; sim and validate stay reachable as flymsg.cli.sim/.validate
__all__ = [
    "COMMANDS",
    "MALECNS_ONLY",
    "audit_focus_types",
    "build_parser",
    "label",
    "main",
    "ng_link",
    "sim",
    "summarize",
    "validate",
]

COMMANDS = {
    "info": cmd_info,
    "path": cmd_path,
    "sim": cmd_sim,
    "validate": cmd_validate,
    "calibrate": cmd_calibrate,
    "compare": cmd_compare,
    "dimorphism": cmd_dimorphism,
    "select-model": cmd_select_model,
    "audit": cmd_audit,
    "viz": cmd_viz,
    "wiring-null": cmd_wiring_null,
    "nulls": cmd_nulls,
    "benchmarks": cmd_benchmarks,
    "behavior": cmd_behavior,
    "silence-scan": cmd_silence_scan,
    "partner-followup": cmd_partner_followup,
    "mb-plasticity": cmd_mb_plasticity,
    "eye": cmd_eye,
    "odor": cmd_odor,
    "muscles": cmd_muscles,
    "t4t5": cmd_t4t5,
    "jump3d": cmd_jump3d,
    "kc-sparseness": cmd_kc_sparseness,
    "weight-rule": cmd_weight_rule,
    "trace": cmd_trace,
    "sensitivity": cmd_sensitivity,
    "baselines": cmd_baselines,
    "convergence": cmd_convergence,
    "song": cmd_song,
    "gf-looming": cmd_gf_looming,
    "apl-claws": cmd_apl_claws,
    "experiment": cmd_experiment,
    "explore": cmd_explore,
    "confirm": cmd_confirm,
    "jump": cmd_jump,
    "loop": cmd_loop,
    "homology": cmd_homology,
}
# these need the whole connectome loaded; fetch and build make it, and --progress
# only reads checkpoint files
MALECNS_ONLY = (
    "validate",
    "calibrate",
    "compare",
    "dimorphism",
    "viz",
    "wiring-null",
    "nulls",
    "benchmarks",
    "behavior",
    "silence-scan",
    "partner-followup",
    "mb-plasticity",
    "eye",
    "odor",
    "muscles",
    "t4t5",
    "jump3d",
    "kc-sparseness",
    "weight-rule",
    "trace",
    "sensitivity",
    "baselines",
    "convergence",
    "song",
    "gf-looming",
    "apl-claws",
    "experiment",
    "explore",
    "confirm",
    "jump",
    "loop",
    "homology",
)


def main() -> None:
    p = build_parser()
    a = p.parse_args()
    manifest.mark_start()
    if getattr(a, "progress", False) and a.checkpoint is None:
        p.error("--progress needs --checkpoint FILE")

    try:
        if a.cmd == "fetch":
            return data.fetch(a.data, a.dataset)
        if a.cmd == "build":
            return data.build(a.data, a.dataset)
        if getattr(a, "progress", False):  # reads the checkpoint files only
            return print(dimorphism.progress(a.checkpoint).to_string(index=False))
        if a.cmd == "runs":  # reads manifests only
            table = workbench.index(a.roots)
            if a.label and not table.empty:
                column = "outcome" if a.label in workbench.OUTCOMES else "label"
                table = table[table[column] == a.label]
            return print(table.to_string(index=False) if not table.empty else "no runs")
        if a.cmd == "sensitivity" and not a.run:
            return print(sensitivity.summary())
        if a.cmd == "baselines" and not a.run:
            return print(baselines.summary())
        if a.cmd == "convergence" and not a.run:
            return print(convergence.summary())
        if a.cmd == "song" and not a.run:
            return print(song.summary())
        if a.cmd == "gf-looming" and not a.run:
            return print(gf_looming.summary())
        if a.cmd == "apl-claws" and not a.run:
            return print(apl_claws.summary())
        if a.cmd == "viz-compare":  # reads two exports; loads no dataset
            scene = viz.compare_bundles(
                a.a, a.b, a.out, tuple(a.labels), tuple(a.status), tuple(a.notes)
            )
            for d in scene["comparison"]["differences"]:
                print(f"  differs: {d['key']}: {d['a']} -> {d['b']}")
            return print(f"{len(scene['neurons'])} neurons -> {a.out}/")
        if a.cmd == "silence-scan" and not a.run:
            return print(silence_scan.summary())
        if a.cmd == "partner-followup" and not a.run:
            return print(partner_followup.summary())
        if a.cmd == "mb-plasticity" and not a.run:
            return print(plasticity.summary())
        if a.cmd == "kc-sparseness" and not a.run:
            return print(kc_sparseness.summary())
        if a.cmd == "t4t5" and not a.run:
            return print(t4t5.summary())
        if a.cmd == "weight-rule" and a.areas:
            if a.run:
                p.error("weight-rule takes --areas or --run, not both")
            neurons, _ = data.load(a.data, a.dataset)
            out = weight_rule.fetch_areas(weight_rule.assert_locked(), neurons, a.data)
            return print(f"areas -> {out}")
        if a.cmd == "weight-rule" and not a.run:
            return print(weight_rule.summary())
        if a.cmd == "jump3d" and not a.run:
            return print(jump3d_lock.summary())
        if a.cmd == "behavior" and not a.run:
            return print(behavior.summary())
        if a.cmd == "benchmarks" and a.run and a.corners:
            p.error("benchmarks takes --run or --corners, not both")
        if a.cmd == "benchmarks" and not a.run and not a.corners:
            return print(benchmarks.summary())
        if a.dataset == "fafb" and a.cmd in MALECNS_ONLY:
            # the battery needs the VNC, and the 3D view streams MaleCNS geometry
            sys.exit(f"flymsg: {a.cmd} needs --dataset malecns")
        prepared = managed.prepare(a)
        neurons, edges = data.load(a.data, a.dataset)
        managed.execute(a, neurons, edges, COMMANDS[a.cmd], prepared)
    except KeyError as err:  # unknown neuron query
        sys.exit(f"flymsg: {err.args[0]}")
    except OSError as err:  # missing data files, failed downloads
        sys.exit(f"flymsg: {err}")
    except draws.CheckpointMismatch as err:
        sys.exit(f"flymsg: {err}")
    except prereg.PreregistrationError as err:
        sys.exit(f"flymsg: {err}")
    except benchmarks.BenchmarkError as err:
        sys.exit(f"flymsg: {err}")
    except behavior.BehaviorError as err:
        sys.exit(f"flymsg: {err}")
    except intervention.InterventionError as err:
        sys.exit(f"flymsg: {err}")
    except workbench.ConfigError as err:
        sys.exit(f"flymsg: {err}")
    except sensitivity.SensitivityError as err:
        sys.exit(f"flymsg: {err}")
    except baselines.BaselineError as err:
        sys.exit(f"flymsg: {err}")
    except convergence.ConvergenceError as err:
        sys.exit(f"flymsg: {err}")
    except song.SongError as err:
        sys.exit(f"flymsg: {err}")
    except gf_looming.LoomingError as err:
        sys.exit(f"flymsg: {err}")
    except apl_claws.AplClawsError as err:
        sys.exit(f"flymsg: {err}")
    except silence_scan.ScanError as err:
        sys.exit(f"flymsg: {err}")
    except partner_followup.FollowupError as err:
        sys.exit(f"flymsg: {err}")
    except plasticity.PlasticityError as err:
        sys.exit(f"flymsg: {err}")
    except kc_sparseness.SparsenessError as err:
        sys.exit(f"flymsg: {err}")
    except t4t5.T4T5Error as err:
        sys.exit(f"flymsg: {err}")
    except jump3d_lock.Jump3DError as err:
        sys.exit(f"flymsg: {err}")
    except ValueError as err:  # bad argument combinations reaching the model
        sys.exit(f"flymsg: {err}")
    except KeyboardInterrupt:
        resume = (
            " (rerun with the same --checkpoint to resume)"
            if getattr(a, "checkpoint", None)
            else ""
        )
        sys.exit(f"flymsg: interrupted{resume}")
