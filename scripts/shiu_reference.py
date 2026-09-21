"""Reference run of the published Shiu et al. brian2 model on FlyWire v783 (engine check).

Runs their own model.py (pinned commit) on the sugar GRNs, 10 runs of 1 s per input rate,
and writes one spike table per rate to --out. brian2 is not a flymsg dependency; use a
separate environment:

    uv venv /tmp/brian && uv pip install --python /tmp/brian/bin/python brian2 pandas pyarrow joblib
    /tmp/brian/bin/python scripts/shiu_reference.py --rates 50,100,200

Compare with flymsg: compare.shiu_rates(neurons, edges, stim, rate) on `--dataset fafb`
(docs/comparison.md). Needs `flymsg --dataset fafb fetch` first.
"""

import argparse
import importlib.util
import sys
import urllib.request
from pathlib import Path

import pandas as pd
from brian2 import Hz

ROOT = Path(__file__).resolve().parent.parent
MODEL_URL = "https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/91bdd1e7dcf193f3e7ca5a8933497fcef63b7960/model.py"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rates", default="50,100,200")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "fafb" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "shiu-reference")
    a = ap.parse_args()
    cache = a.out / "model.py"
    a.out.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        urllib.request.urlretrieve(MODEL_URL, cache)
    sys.path.insert(0, str(a.out))
    model = load("model", cache)
    compare = load("compare", ROOT / "src" / "flymsg" / "compare.py")  # no scipy needed
    comp = pd.read_csv(a.data / "Completeness_783.csv", index_col=0)
    sugar = [i for i in compare.SHIU_SUGAR if i in comp.index]
    params = dict(model.default_params, n_run=a.runs)
    for rate in (int(r) for r in a.rates.split(",")):
        params["r_poi"] = rate * Hz
        model.run_exp(
            exp_name=f"sugar_{rate}Hz",
            neu_exc=sugar,
            path_res=a.out,
            path_comp=a.data / "Completeness_783.csv",
            path_con=a.data / "Connectivity_783.parquet",
            params=params,
            n_proc=a.procs,
        )


if __name__ == "__main__":
    main()
