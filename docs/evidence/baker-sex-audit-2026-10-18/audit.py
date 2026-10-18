"""Sex annotations of the 11 complete Baker classes other than AVLP_pr36 (2026-10-18).

Reads only identity tables: matches.json from baker-crossmatch-2026-10-17.zip, the
MaleCNS v1.0 parquet and flywire_annotations v3.2.0 Supplemental_file1. No response
data. Usage: python -I audit.py MATCHES_JSON NEURONS_PARQUET FLYWIRE_TSV > results.json
"""

import hashlib
import json
import re
import sys

import pandas as pd

CLASSES = [
    "A2",
    "B2",
    "AVLP_pr04",
    "AVLP_pr05",
    "AVLP_pr12",
    "AVLP_pr23",
    "AVLP_pr35",
    "IPS_pr02",
    "IPS/WED_pr01",
    "SAD_pr01",
    "WED_pr01",
]
PARQUET = "7ec0020f08495c35398deafa3183292dfb489ce6717d889b80cfcc11cb757c7c"
TSV = "b214970b55d2fbe0853bba536fdcb9e28730f4eb7ab06f600491df795da683cd"


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def counts(series):
    return {str(k): int(v) for k, v in series.fillna("").value_counts().items()}


matches_path, parquet, tsv = sys.argv[1:4]
if sha256(parquet) != PARQUET or sha256(tsv) != TSV:
    sys.exit("input hash mismatch")
with open(matches_path) as f:
    rows = [r for r in json.load(f) if r["baker_type"] in CLASSES]
if {r["status"] for r in rows} != {"complete"}:
    sys.exit("class not complete")

male = pd.read_parquet(parquet, columns=["bodyId", "type", "dimorphism", "flywireType"])
fem = pd.read_csv(
    tsv,
    sep="\t",
    usecols=["root_id", "cell_type", "dimorphism"],
    dtype={"root_id": "int64"},
)
male_ix, fem_ix = male.set_index("bodyId"), fem.set_index("root_id")

per_class = {}
for name in CLASSES:
    roots = {
        int(m["root_783"])
        for r in rows
        if r["baker_type"] == name
        for m in r["matches"]
    }
    bodies = {
        int(b["body_id"])
        for r in rows
        if r["baker_type"] == name
        for m in r["matches"]
        for b in m["male"]
    }
    per_class[name] = {
        "male_bodies": len(bodies),
        "male_dimorphism": counts(male_ix.loc[sorted(bodies), "dimorphism"]),
        "female_roots_783": len(roots),
        "female_dimorphism": counts(fem_ix.loc[sorted(roots), "dimorphism"]),
    }

# Is `isomorphic` asserted after a cross-sex comparison, or the residual value?
tokens = set()
for value in male.flywireType.dropna():
    tokens |= {t.strip() for t in re.split(r"[,;]", value) if t.strip()}
iso = fem[fem.dimorphism == "isomorphic"]
print(
    json.dumps(
        {
            "schema": "flymsg.baker_sex_audit/v1",
            "inputs": {"neurons_parquet": PARQUET, "flywire_v3_2_0_tsv": TSV},
            "classes": per_class,
            "male_dimorphism_values": counts(male.dimorphism),
            "female_dimorphism_values": counts(fem.dimorphism),
            "female_isomorphic_without_cell_type": int(iso.cell_type.isna().sum()),
            "female_isomorphic_typed_without_male_flywireType_token": int(
                (iso.cell_type.notna() & ~iso.cell_type.isin(tokens)).sum()
            ),
        },
        indent=2,
        sort_keys=True,
    )
)
