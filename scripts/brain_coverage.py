"""What of the MaleCNS brain the model uses, and what it leaves out, in numbers.

    uv run python scripts/brain_coverage.py

Prints the figures cited in docs/roadmap.md ("Brain coverage"): neurons and signs, the
FlyWire cross-check of the unsigned neurons, somata in the volume, and the photoreceptors
and optic-lobe columns an eye encoder would use. Reads data/ and data/raw only; changes
nothing.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from flymsg import data

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
FAST = {"acetylcholine", "gaba", "glutamate", "histamine"}
PURITY = 0.9  # share of a FAFB type's neurons with its majority transmitter


def side(instance) -> str | None:
    s = instance if isinstance(instance, str) else ""
    return s[-1] if s[-2:] in ("_L", "_R") else None


def main() -> None:
    neurons, edges = data.load(ROOT / "data")
    out = np.bincount(edges["pre"], weights=edges["weight"], minlength=len(neurons))
    total = out.sum()

    def share(mask) -> float:
        return 100 * out[np.asarray(mask)].sum() / total

    print(f"neurons {len(neurons):,}, synapses {int(total):,}")
    for s in (1, -1, 0):
        m = (neurons["sign"] == s).to_numpy()
        print(f"  sign {s:+d}: {m.sum():,} neurons, {share(m):.2f}% of output synapses")

    nt = pd.read_feather(RAW / "body-neurotransmitters-male-cns-v1.0.feather")
    consensus = (
        nt.set_index("body")["consensus_nt"].reindex(neurons["bodyId"]).to_numpy()
    )
    zero = (neurons["sign"] == 0).to_numpy()
    unclear = (
        zero
        & pd.Series(consensus).fillna("missing").isin(["unclear", "missing"]).to_numpy()
    )
    print(
        f"  sign 0: unclear or missing {unclear.sum():,} ({share(unclear):.2f}%), "
        f"modulatory {int((zero & ~unclear).sum()):,} ({share(zero & ~unclear):.2f}%)"
    )

    fafb = pd.read_parquet(ROOT / "data" / "fafb" / "neurons.parquet")
    by_type = fafb[fafb["type"].notna() & fafb["nt"].notna()].groupby("type")["nt"]
    top = by_type.agg(lambda x: x.value_counts().index[0])
    purity = by_type.agg(lambda x: x.value_counts(normalize=True).iloc[0])
    ft = neurons["flywireType"].where(unclear)
    matched = ft.isin(top.index).to_numpy()
    pred = ft.map(top)
    good = matched & ft.map(purity).ge(PURITY).to_numpy()
    fast = good & pred.isin(FAST).to_numpy()
    by_nt = {k: int(v) for k, v in pred[good].value_counts().items()}
    print(
        f"  FlyWire cross-check of the {unclear.sum():,} unclear or missing: "
        f"{int(ft.notna().sum()):,} have a flywireType, {matched.sum():,} match a FAFB type, "
        f"{good.sum():,} with purity >= {PURITY}, of which {fast.sum():,} fast "
        f"({share(fast):.2f}% of output synapses); "
        f"{by_nt}"
    )

    ann = (
        pd.read_feather(
            RAW / "body-annotations-male-cns-v1.0-minconf-0.5.feather",
            columns=["bodyId", "somaLocation", "assignedOlHex1", "assignedOlHex2"],
        )
        .set_index("bodyId")
        .reindex(neurons["bodyId"])
    )
    soma = ann["somaLocation"].map(lambda x: isinstance(x, np.ndarray)).to_numpy()
    print(f"somata in the volume {soma.sum():,} of {len(neurons):,}")

    sides = neurons["instance"].map(side)
    hexed = (
        ann["assignedOlHex1"].notna().to_numpy()
        & ann["assignedOlHex2"].notna().to_numpy()
    )
    cols = {
        s: len(
            set(
                zip(
                    ann["assignedOlHex1"][
                        hexed
                        & (neurons["type"] == "L1").to_numpy()
                        & (sides == s).to_numpy()
                    ],
                    ann["assignedOlHex2"][
                        hexed
                        & (neurons["type"] == "L1").to_numpy()
                        & (sides == s).to_numpy()
                    ],
                    strict=True,
                )
            )
        )
        for s in "LR"
    }
    print(f"optic-lobe columns (one L1 each): L {cols['L']}, R {cols['R']}")
    hex_idx = np.flatnonzero(hexed)
    col = pd.DataFrame(
        {
            "side": sides.iloc[hex_idx].to_numpy(),
            "h1": ann["assignedOlHex1"].iloc[hex_idx].to_numpy(),
            "h2": ann["assignedOlHex2"].iloc[hex_idx].to_numpy(),
        },
        index=hex_idx,
    )
    for kind, pattern in (("R1-R6", r"^R1-R6$"), ("R7", r"^R7"), ("R8", r"^R8")):
        cells = np.flatnonzero(
            neurons["type"].fillna("").str.contains(pattern).to_numpy()
        )
        e = edges[np.isin(edges["pre"], cells) & np.isin(edges["post"], hex_idx)]
        e = e.join(col, on="post")
        votes = e.groupby(["pre", "side", "h1", "h2"])["weight"].sum().reset_index()
        per = votes.sort_values("weight").groupby("pre").tail(1)
        n_side = {s: int((sides.iloc[cells] == s).sum()) for s in "LR"}
        covered = {
            s: len(per[per["side"] == s][["h1", "h2"]].drop_duplicates()) for s in "LR"
        }
        print(
            f"  {kind}: {len(cells):,} simulated (L {n_side['L']}, R {n_side['R']}); "
            f"{len(per):,} assigned to a column by their strongest output; columns "
            f"covered L {covered['L']}, R {covered['R']}"
        )


if __name__ == "__main__":
    main()
