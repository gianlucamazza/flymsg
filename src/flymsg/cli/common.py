"""Helpers shared by the command modules: labels, neuroglancer links, run manifests."""

import json
import os
import urllib.parse

import pandas as pd

from flymsg import manifest

NG = "https://neuroglancer-demo.appspot.com/#!"


def ng_link(body_ids) -> str:
    state = {
        "layers": [
            {
                "type": "image",
                "source": "precomputed://gs://flyem-male-cns/em/em-clahe-jpeg",
                "name": "em",
            },
            {
                "type": "segmentation",
                "source": "precomputed://gs://flyem-male-cns/v1.0/segmentation",
                "segments": [str(b) for b in body_ids],
                "name": "neurons",
            },
        ],
        "layout": "3d",
    }
    return NG + urllib.parse.quote(json.dumps(state, separators=(",", ":")))


def label(neurons: pd.DataFrame, i: int) -> str:
    r = neurons.iloc[i]
    name = next((x for x in (r["instance"], r["type"]) if pd.notna(x)), "untyped")
    return f"{name} ({r['bodyId']}, {r['nt']}, {r['superclass']})"


def stamp(out, command, a, neurons, edges, config, seeds, started, extra=None):
    """Write a run manifest next to this command's outputs."""
    dataset_dir = a.data / "fafb" if a.dataset == "fafb" else a.data
    if getattr(a, "_run", None) is not None:
        return a._run.stamp(
            command=command,
            config=config,
            seeds=seeds,
            dataset=a._dataset_snapshot,
            extra={"data_dir": os.fspath(dataset_dir), **(extra or {})},
        )
    manifest.write(
        out,
        command=command,
        config=config,
        seeds=seeds,
        dataset=manifest.dataset_info(a.dataset, a.data, neurons, edges),
        started_at=started,
        extra={"data_dir": os.fspath(dataset_dir), **(extra or {})},
    )
