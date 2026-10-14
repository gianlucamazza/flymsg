"""The argparse definition of every flymsg command."""

import argparse
import os
from pathlib import Path

from flymsg import dimorphism, nulls, prereg, sim, viz, workbench


def build_parser() -> argparse.ArgumentParser:
    """The command line, as a parser that can be built and inspected on its own."""
    p = argparse.ArgumentParser(
        prog="flymsg",
        description="Explore and simulate the male Drosophila CNS connectome",
    )
    p.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("FLYMSG_DATA", "data")),
        help="data dir (env FLYMSG_DATA)",
    )
    p.add_argument(
        "--dataset",
        choices=["malecns", "fafb"],
        default="malecns",
        help="malecns (male CNS, default) or fafb (female brain, FlyWire v783, in DATA/fafb)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser(
        "behavior",
        help="print the frozen one-bit looming-jump protocol, or run it with --run",
    )
    s.add_argument(
        "--run",
        action="store_true",
        help="run the frozen closed loop at the default parameters",
    )
    s = sub.add_parser(
        "benchmarks",
        help="print the frozen held-out manifest, or score it with --run",
    )
    s.add_argument(
        "--run",
        action="store_true",
        help="score the frozen cases at the default corner (no other parameters)",
    )
    s.add_argument(
        "--corners",
        action="store_true",
        help="score the two frozen sensitivity corners (does not replace --run)",
    )
    s = sub.add_parser(
        "experiment",
        help="validate and run an exploratory config (flymsg.experiment/v1)",
    )
    s.add_argument("config", type=Path)
    s.add_argument("--check", action="store_true", help="validate only")
    s.add_argument("--root", type=Path, default=Path("runs/experiments"))
    s = sub.add_parser(
        "jump",
        help="M1: drive a one-DOF jump body from a motor neuron through an engineered decoder",
    )
    s.add_argument("--sim", nargs="+", required=True, metavar="STIM")
    s.add_argument("--silence", nargs="+")
    s.add_argument("--motor", default="TTMn_R")
    s.add_argument(
        "--gain-n", type=float, required=True, help="newtons per spike (engineered)"
    )
    s.add_argument("--mass-kg", type=float, required=True)
    s.add_argument("--rate", type=float, default=100.0)
    s.add_argument("--duration", type=float, default=600.0)
    s.add_argument("--stim-ms", type=float, default=300.0)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", type=Path, default=Path("runs/jump"))
    s = sub.add_parser(
        "homology",
        help="male/female type mapping (flywireType) and the LC4 -> DNp01 pilot",
    )
    s.add_argument("--out", type=Path, default=Path("validation/homology"))
    s = sub.add_parser(
        "loop",
        help="M2: looming closed loop with disconnected, shuffled and replay controls",
    )
    s.add_argument("--sim", nargs="+", required=True, metavar="STIM")
    s.add_argument("--motor", default="TTMn_R")
    s.add_argument("--radius-m", type=float, required=True)
    s.add_argument("--distance-m", type=float, required=True)
    s.add_argument("--speed-m-s", type=float, required=True)
    s.add_argument(
        "--transducer-gain", type=float, required=True, help="Hz per rad/s (engineered)"
    )
    s.add_argument("--max-rate-hz", type=float, required=True)
    s.add_argument(
        "--gain-n", type=float, required=True, help="newtons per spike (engineered)"
    )
    s.add_argument("--mass-kg", type=float, required=True)
    s.add_argument("--duration", type=float, default=300.0)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", type=Path, default=Path("runs/loop"))
    s = sub.add_parser(
        "explore",
        help="paths between two populations, then silence each intermediate type (exploratory)",
    )
    s.add_argument("source", nargs="?")
    s.add_argument("target", nargs="?")
    s.add_argument("--paths", type=int, default=3)
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--seed0", type=int, default=0)
    s.add_argument("--silence", nargs="+", help="silenced in every arm (e.g. DNp01)")
    s.add_argument("--replay", type=Path, help="rerun a saved exploration and compare")
    s.add_argument("--out", type=Path, default=Path("runs/explore"))
    s = sub.add_parser(
        "confirm", help="run a registered intervention lock (flymsg.intervention/v1)"
    )
    s.add_argument("lock", type=Path)
    s.add_argument("--checkpoint", type=Path)
    s.add_argument("--out", type=Path, default=Path("runs/interventions"))
    s = sub.add_parser("runs", help="index every run manifest (no dataset needed)")
    s.add_argument(
        "roots", nargs="*", type=Path, default=[Path("runs"), Path("docs/live")]
    )
    s.add_argument("--label", choices=workbench.LABELS + workbench.OUTCOMES)
    s = sub.add_parser(
        "sensitivity",
        help="print the locked w_syn x th_jump grid, or run it with --run (a report)",
    )
    s.add_argument("--run", action="store_true")
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--checkpoint", type=Path)
    s = sub.add_parser(
        "convergence",
        help="print the locked timestep convergence check, or run it with --run (SF2)",
    )
    s.add_argument("--run", action="store_true")
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--checkpoint", type=Path)
    s = sub.add_parser(
        "song",
        help="print the locked pulse/sine benchmark (Pacheco et al. 2021), or run it with --run (#36)",
    )
    s.add_argument("--run", action="store_true")
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--checkpoint", type=Path)
    s = sub.add_parser(
        "gf-looming",
        help="print the locked looming -> giant fiber timing benchmark (Dombrovski et al. 2025), or run it with --run (#34)",
    )
    s.add_argument("--run", action="store_true")
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--checkpoint", type=Path)
    s = sub.add_parser(
        "trace",
        help="record v, g, threshold, spikes and input of chosen neurons (exploratory)",
    )
    s.add_argument("stim", nargs="+", help="stimulated types/instances/bodyIds")
    s.add_argument(
        "--neurons", nargs="+", required=True, help="neurons to record (types/bodyIds)"
    )
    s.add_argument("--silence", nargs="+", help="neurons that never fire")
    s.add_argument("--rate", type=float, default=100.0)
    s.add_argument("--duration", type=float, default=600.0, help="ms")
    s.add_argument("--stim-ms", type=float, default=300.0)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--every", type=int, default=1, help="record every N neural steps")
    s.add_argument("--w-syn", type=float, default=sim.Params.w_syn)
    s.add_argument("--th-jump", type=float, default=sim.Params.th_jump)
    s.add_argument("--out", type=Path, default=Path("runs/trace"))
    s = sub.add_parser(
        "silence-scan",
        help="print the frozen residual TTMn_R partner scan (issue #20), or run it with --run",
    )
    s.add_argument("--run", action="store_true", help="run the frozen scan")
    s.add_argument("--workers", type=int, default=1, help="worker processes")
    s.add_argument(
        "--checkpoint",
        type=Path,
        help="JSON-lines file; an interrupted run resumes from it",
    )
    s = sub.add_parser(
        "partner-followup",
        help="print the frozen residual partner follow-up (issue #76), or run it with --run",
    )
    s.add_argument("--run", action="store_true", help="run the frozen follow-up")
    s.add_argument("--workers", type=int, default=1, help="worker processes")
    s.add_argument(
        "--checkpoint",
        type=Path,
        help="JSON-lines file; an interrupted run resumes from it",
    )
    s = sub.add_parser(
        "kc-sparseness",
        help="print the frozen Kenyon cell sparseness diagnostic (issue #95), or run it",
    )
    s.add_argument("--run", action="store_true", help="run the frozen diagnostic")
    s = sub.add_parser(
        "weight-rule",
        help="print the frozen count-vs-density weight comparison (#139), or run it",
    )
    s.add_argument("--run", action="store_true", help="run the frozen comparison")
    s.add_argument(
        "--areas",
        action="store_true",
        help="measure the LHN mesh areas into data/weight_rule/ (before --run)",
    )
    s = sub.add_parser(
        "jump3d",
        help="print the frozen TTM-driven NeuroMechFly jump (#90, #94), or run it",
    )
    s.add_argument("--run", action="store_true", help="run the frozen jump")
    s = sub.add_parser(
        "t4t5",
        help="print the frozen T4/T5 direction-selectivity test (#84), or run it",
    )
    s.add_argument("--run", action="store_true", help="run the frozen test")
    s = sub.add_parser(
        "odor", help="a DoOR odorant as a response per MaleCNS ORN type (#96)"
    )
    s.add_argument("name", help="DoOR odorant name, e.g. 3-octanol")
    sub.add_parser(
        "muscles",
        help="MANC's muscle per MaleCNS motor neuron (Cheong 2024, fetched); no actuator",
    )
    sub.add_parser(
        "eye",
        help="column -> viewing direction and photoreceptor -> column tables (#84)",
    )
    s = sub.add_parser(
        "mb-plasticity",
        help="print the frozen KC -> MBON11 depression protocol (issue #85), or run it",
    )
    s.add_argument("--run", action="store_true", help="run the frozen protocol")
    sub.add_parser("fetch", help="download raw tables (malecns ~1.1 GB, fafb ~135 MB)")
    sub.add_parser("build", help="compact raw tables to data/*.parquet")
    s = sub.add_parser(
        "info", help="annotations and top partners of a type/instance/bodyId"
    )
    s.add_argument("query")
    s.add_argument("--top", type=int, default=10)
    s = sub.add_parser(
        "path", help="strongest path between two types/instances/bodyIds"
    )
    s.add_argument("src")
    s.add_argument("dst")
    s.add_argument("--min-weight", type=int, default=5)
    s.add_argument(
        "--alt",
        type=int,
        default=1,
        help="routes to list, each avoiding the intermediate types of the previous ones",
    )
    s = sub.add_parser("sim", help="LIF simulation with Poisson stimulation")
    s.add_argument(
        "stim",
        nargs="+",
        help="types/instances/bodyIds to stimulate (e.g. LC4 or LC4_R)",
    )
    s.add_argument("--rate", type=float, default=150.0)
    s.add_argument("--duration", type=float, default=1000.0, help="ms")
    s.add_argument(
        "--stim-ms", type=float, help="stimulus length in ms (default: whole run)"
    )
    s.add_argument(
        "--w-syn", type=float, default=sim.Params.w_syn, help="mV per synapse"
    )
    s.add_argument(
        "--th-jump",
        type=float,
        default=sim.Params.th_jump,
        help="adaptive threshold, mV/spike (0 = Shiu)",
    )
    s.add_argument(
        "--superclass",
        nargs="*",
        help="only report these superclasses, e.g. descending_neuron vnc_motor",
    )
    s.add_argument("--top", type=int, default=25)
    s.add_argument("--seed", type=int, default=0, help="first seed")
    s.add_argument("--seeds", type=int, default=1, help="number of seeds to average")
    s.add_argument("--out", type=Path)
    s = sub.add_parser(
        "wiring-null",
        help="N1: one degree-preserving shuffle, then criterion v4 on both graphs",
    )
    s.add_argument(
        "--stats",
        action="store_true",
        help="print the shuffle census and stop, without simulating",
    )
    s = sub.add_parser(
        "nulls",
        help="pre-registered null families (CI draw count by default; --full for 20)",
    )
    locked = prereg.load()
    s.add_argument(
        "--draws",
        type=int,
        default=locked["nulls"]["draws_ci"],
        help="seeded draws per family (default: CI count "
        f"{locked['nulls']['draws_ci']}; full protocol is "
        f"{locked['nulls']['draws_full']})",
    )
    s.add_argument(
        "--full",
        action="store_true",
        help=f"use the pre-registered full draw count ({locked['nulls']['draws_full']})",
    )
    s.add_argument(
        "--families",
        nargs="+",
        choices=list(nulls.FAMILIES),
        help="subset of families (default: all four)",
    )
    s.add_argument("--seed0", type=int, default=0, help="first shuffle seed")
    s.add_argument("--out", type=Path, default=Path("runs/nulls"))
    s.add_argument(
        "--exploratory",
        action="store_true",
        help="allow a draw count that is not the locked CI or full value",
    )
    s = sub.add_parser(
        "validate", help="run the validation battery (known circuits + controls)"
    )
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--w-syn", type=float, default=sim.Params.w_syn)
    s.add_argument("--th-jump", type=float, default=sim.Params.th_jump)
    s.add_argument(
        "--out", type=Path, help="directory for report.csv and manifest.json"
    )
    s.add_argument(
        "--exploratory",
        action="store_true",
        help="allow w_syn, th_jump or seeds that differ from the preregistration",
    )
    s = sub.add_parser(
        "audit",
        help="reconstruction completeness: left/right asymmetry of bilateral types",
    )
    s.add_argument(
        "--types", nargs="+", help="types to report (default: those behind results)"
    )
    s.add_argument("--top", type=int, default=20, help="most asymmetric types to list")
    s = sub.add_parser(
        "select-model",
        help="pre-registered choice: calibrated model vs density-scaled model",
    )
    s.add_argument("--seeds", type=int, default=10)
    s.add_argument("--workers", type=int, default=4)
    # Pre-registered model A uses th_jump 2. The simulator default stays 0, so this
    # flag does not borrow sim.Params.th_jump.
    s.add_argument("--th-jump-a", type=float, default=2.0)
    s.add_argument(
        "--rho-range", type=float, nargs=2, default=[1.43, 2.43], metavar=("LO", "HI")
    )
    s.add_argument("--out", type=Path, help="directory for one CSV report per model")
    s.add_argument("--seed0", type=int, default=0, help="first simulation seed")
    s.add_argument(
        "--control-seed", type=int, default=0, help="seed of the control draws"
    )
    s.add_argument(
        "--replication",
        action="store_true",
        help="A vs B- only (the pre-registered replication; use fresh seeds)",
    )
    s = sub.add_parser(
        "compare",
        help="male vs female: synapse density, same model on both, the FAFB LB3 split",
    )
    s.add_argument("--sex", action="store_true", help="same model on both sexes")
    s.add_argument(
        "--fingerprint",
        nargs="+",
        metavar="TYPE",
        help="cosine of each male type's output profile against Shiu et al.'s FAFB sets",
    )
    s.add_argument(
        "--lb3-split",
        action="store_true",
        help="assign each FAFB LB3 neuron to a male subtype, then MN9 per part",
    )
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--out", type=Path, default=Path("runs"))
    s = sub.add_parser(
        "dimorphism",
        help="share of fru/dsx+, male-specific and dimorphic neurons among responders",
    )
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument(
        "--silencing",
        action="store_true",
        help="instead: response drop when each category is silenced",
    )
    s.add_argument(
        "--loop",
        nargs="?",
        const="t2",
        choices=sorted(dimorphism.LOOP_PRESETS),
        help="instead: silence a pre-registered set of cell types vs matched responders"
        " (t2: the v0.5 loop; t3: the route it pointed to; t4: AVLP717m)",
    )
    s.add_argument("--null", type=int, default=1000, help="random silencings per test")
    s.add_argument(
        "--progress",
        action="store_true",
        help="instead: how far the run of --checkpoint has got (read-only, no data needed)",
    )
    s.add_argument(
        "--checkpoint",
        type=Path,
        help="save each finished job here and resume from it",
    )
    s.add_argument(
        "--by-type",
        nargs=2,
        metavar=("CASE", "CATEGORY"),
        help='instead: silence one type at a time, e.g. "P1 courtship drive" male-specific',
    )
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--w-syn", type=float, default=sim.Params.w_syn)
    s.add_argument("--th-jump", type=float, default=sim.Params.th_jump)
    s = sub.add_parser(
        "calibrate", help="grid-search w_syn x th_jump against the validation battery"
    )
    s.add_argument("--w-syn", type=float, nargs="+", default=[0.2, 0.275, 0.35])
    s.add_argument(
        "--th-jump", type=float, nargs="+", default=[2.0, 4.0, 6.0, 8.0, 12.0]
    )
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--out", type=Path)
    s = sub.add_parser(
        "viz", help="export a three.js 3D view (anatomy or simulation replay)"
    )
    what = s.add_mutually_exclusive_group(required=True)
    what.add_argument(
        "--types", nargs="+", help="types/instances/bodyIds, one colour group each"
    )
    what.add_argument(
        "--path",
        nargs=2,
        metavar=("SRC", "DST"),
        help="strongest path between two populations",
    )
    what.add_argument(
        "--sim",
        nargs="+",
        metavar="STIM",
        help="simulate and replay; shows every neuron that fires during the stimulus",
    )
    what.add_argument(
        "--eye",
        nargs=2,
        metavar=("POLARITY", "DIRECTION"),
        help="replay one edge of the locked T4/T5 protocol through the eye (on/off, "
        "front_to_back/back_to_front/upward/downward), graded potentials included",
    )
    s.add_argument("--rate", type=float, default=100.0)
    s.add_argument("--duration", type=float, default=600.0, help="ms")
    s.add_argument("--stim-ms", type=float, default=300.0)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument(
        "--keep",
        nargs="+",
        help="with --sim: always export these neurons, even if silent (group 'kept')",
    )
    s.add_argument(
        "--min-rate",
        type=float,
        default=0.0,
        help="replay: only neurons above this rate (Hz)",
    )
    s.add_argument(
        "--silence", nargs="+", help="replay: neurons that never fire (types/bodyIds)"
    )
    s.add_argument(
        "--eye-config",
        type=int,
        default=0,
        help="with --eye: the locked configuration to replay (index, as in its report)",
    )
    s.add_argument(
        "--eye-top",
        type=int,
        default=300,
        help="with --eye: neurons shown per class (graded classes and spiking pathway)",
    )
    s.add_argument("--out", type=Path, default=Path("runs/viz"))
    s = sub.add_parser(
        "viz-compare",
        help="pair two replay exports for side-by-side viewing (no simulation)",
    )
    s.add_argument("a", type=Path, help="baseline export directory")
    s.add_argument("b", type=Path, help="intervention export directory")
    s.add_argument("--labels", nargs=2, required=True, metavar=("A", "B"))
    s.add_argument(
        "--status",
        nargs=2,
        required=True,
        choices=viz.COMPARE_STATUSES,
        metavar=("A", "B"),
        help=f"protocol status of each run: {', '.join(viz.COMPARE_STATUSES)}",
    )
    s.add_argument("--notes", nargs=2, default=("", ""), metavar=("A", "B"))
    s.add_argument("--out", type=Path, default=Path("runs/viz-compare"))
    return p
