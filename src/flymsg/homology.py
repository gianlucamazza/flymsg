"""Male/female homology (#29): a versioned type mapping and one pilot circuit.

The mapping is MaleCNS `flywireType`, the release's own call of the FAFB type of each male
neuron (Berg et al. 2026). Every male cell type gets one category, so that a missing match
is never read as a missing neuron:

- `matched`: its flywireType is a FAFB v783 type;
- `annotation not in FAFB table`: it has a flywireType the FAFB tables do not contain;
- `outside FAFB tissue`: no flywireType, and its superclass lies in the ventral nerve cord,
  which FAFB does not contain;
- `male-specific annotation`: no flywireType, and MaleCNS calls it male-specific;
- `not mapped`: no flywireType and none of the above; absence of a match, not of a cell.

FAFB types that no male neuron names are listed as `female type with no male mapping`.
The pilot compares LC4 → DNp01 synapse counts in both datasets, raw and divided by the
synapse-density ratio of the two reconstructions; a difference is not attributed to sex
without ruling out the reconstruction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from flymsg import compare

SCHEMA = "flymsg.homology/v1"
EVIDENCE = "MaleCNS flywireType annotation (Berg et al. 2026); FAFB v783 types"
CATEGORIES = (
    "matched",
    "annotation not in FAFB table",
    "outside FAFB tissue",
    "male-specific annotation",
    "not mapped",
    "female type with no male mapping",
)


def _vnc(superclass: str) -> bool:
    return str(superclass).startswith("vnc_")


def mapping(male: pd.DataFrame, female: pd.DataFrame) -> pd.DataFrame:
    """One row per male cell type and per unreferenced female type."""
    female_counts = female["type"].dropna().value_counts()
    rows = []
    for t, g in male.dropna(subset=["type"]).groupby("type", sort=True):
        fw = sorted(set(g["flywireType"].dropna()))
        superclass = (
            g["superclass"].mode().iat[0] if g["superclass"].notna().any() else ""
        )
        dimorph = g["dimorphism"].fillna("")
        if fw:
            in_fafb = [x for x in fw if x in female_counts.index]
            category = "matched" if in_fafb else "annotation not in FAFB table"
            n_female = int(sum(female_counts.get(x, 0) for x in fw))
        elif _vnc(superclass):
            category, n_female = "outside FAFB tissue", 0
        elif dimorph.str.contains("male-specific").any():
            category, n_female = "male-specific annotation", 0
        else:
            category, n_female = "not mapped", 0
        rows.append(
            {
                "male_type": t,
                "flywire_types": ";".join(fw),
                "category": category,
                "n_male": len(g),
                "n_female": n_female,
                "superclass": superclass,
                "evidence": "flywireType" if fw else "",
            }
        )
    named = set(male["flywireType"].dropna())
    for t, n in female_counts.items():
        if t not in named:
            rows.append(
                {
                    "male_type": "",
                    "flywire_types": t,
                    "category": "female type with no male mapping",
                    "n_male": 0,
                    "n_female": int(n),
                    "superclass": "",
                    "evidence": "",
                }
            )
    return pd.DataFrame(rows)


def pilot(
    male: tuple[pd.DataFrame, pd.DataFrame], female: tuple[pd.DataFrame, pd.DataFrame]
) -> pd.DataFrame:
    """LC4 → DNp01 synapses per DNp01 neuron in each dataset: raw, divided by the median
    density ratio, and as a share of that DNp01's own input, which needs no global scale."""
    ratio, n_types = compare.synapse_density_ratio(male, female)
    rows = []
    for sex, (n, e), col in (("male", male, "flywireType"), ("female", female, "type")):
        types = n[col].to_numpy()
        total_in = np.bincount(e["post"], weights=e["weight"], minlength=len(n))
        lc4 = types == "LC4"
        for i in (types == "DNp01").nonzero()[0]:
            into = e[e["post"].to_numpy() == i]
            syn = int(into.loc[lc4[into["pre"].to_numpy()], "weight"].sum())
            rows.append(
                {
                    "dataset": sex,
                    "DNp01": str(n["instance"].iat[i]) if "instance" in n else str(i),
                    "LC4_neurons": int(lc4.sum()),
                    "LC4_synapses": syn,
                    "density_scaled": syn / ratio if sex == "male" else float(syn),
                    "input_synapses": int(total_in[i]),
                    "share_of_input": syn / total_in[i]
                    if total_in[i]
                    else float("nan"),
                    "density_ratio": ratio,
                    "ratio_types": n_types,
                }
            )
    return pd.DataFrame(rows)
