"""Independent rendered-camera check of G2, on synthetic registration only.

MUJOCO_GL=egl uv run python scripts/check_optics_camera.py --out runs/optics-camera.json
Uses FlyGym's actual vision cameras and renderer. Fly geometry is hidden only for this
isolated optical oracle; no physics advances, retina transducer or motor map is installed.
Acceptance is declared before rendering: the planar coverage must lie inside the GPU
silhouette's one-pixel erosion/dilation interval, expanded by the existing 0.0085 bound
for the planar-vs-spherical profile at 8.23 degrees. It does not qualify head registration.
"""

import argparse
import json
import math
import os
from importlib import metadata
from pathlib import Path

import mujoco
import numpy as np
import pandas as pd
from flygym.anatomy import AxisOrder, JointPreset, Skeleton
from flygym.compose import KinematicPosePreset, NeuroMechFly
from flygym.rendering import Renderer
from scipy.ndimage import binary_dilation, binary_erosion

from flymsg import manifest, optics, pose, runstore

RES = 1024
ACCEPTANCE_DEG = 8.23
PLANAR_BOUND = 0.0085
CASES = ((20.0, 0.0, 2.0), (20.0, 2.0, 2.0), (10.0, 0.0, 2.0))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("output exists; choose a new path")
    source = manifest.git_info()
    if source["dirty"] is not False:
        p.error("camera evidence requires clean committed source")
    fly = NeuroMechFly()
    fly.add_joints(
        Skeleton(
            axis_order=AxisOrder.YAW_PITCH_ROLL,
            joint_preset=JointPreset.LEGS_ACTIVE_ONLY,
        ),
        neutral_pose=KinematicPosePreset.NEUTRAL,
    )
    fly.add_vision()
    spec = fly.mjcf_root.copy()
    spec.compiler.fusestatic = False
    for geom in spec.geoms:
        geom.group = 4
    spec.worldbody.add_geom(
        name="oracle_target",
        type=mujoco.mjtGeom.mjGEOM_SPHERE,
        size=[2.0, 0.0, 0.0],
        pos=[20.0, 0.0, 0.0],
        contype=0,
        conaffinity=0,
        group=0,
    )
    model = spec.compile()
    model.vis.global_.offwidth = RES
    model.vis.global_.offheight = RES
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "c_thorax")
    target = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "oracle_target")
    state = pose.BodyState(
        0,
        pose.Pose(
            "world",
            "body",
            tuple(pose.mm(v) for v in data.xpos[root]),
            pose.Quat.of(tuple(data.xquat[root])),
        ),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    )
    mounts = pose.flygym_eye_mounts()
    registration = pose.Registration(
        pose.Pose("body", "eyemap", (0.0, 0.0, 0.0), pose.IDENTITY),
        "synthetic identity, camera oracle only",
    )
    rows = []
    cameras = [(s, f"{s.lower()}_eye_cam_camera") for s in ("L", "R")]
    body_rotation = data.xmat[root].reshape(3, 3)
    for side, camera in cameras:
        cid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera)
        axis = body_rotation.T @ (-data.cam_xmat[cid].reshape(3, 3)[:, 2])
        rows.append(
            {
                "side": side,
                "p": 0,
                "q": 0,
                "azimuth_deg": -math.degrees(math.atan2(axis[1], axis[0])),
                "elevation_deg": math.degrees(
                    math.atan2(axis[2], math.hypot(*axis[:2]))
                ),
            }
        )
    columns = optics.Columns.from_frame(pd.DataFrame(rows), runstore.digest(rows))
    renderer = Renderer(
        model,
        [c for _, c in cameras],
        camera_res=(RES, RES),
        render_rgb=False,
        render_segmentation=True,
    )
    results = []
    try:
        for col, (side, camera) in enumerate(cameras):
            cid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera)
            rotation = data.cam_xmat[cid].reshape(3, 3).copy()
            origin = data.cam_xpos[cid].copy()
            focal = RES / (2 * math.tan(math.radians(model.cam_fovy[cid]) / 2))
            grid = (np.arange(RES) + 0.5 - RES / 2) / focal
            x, y = np.meshgrid(grid, grid)
            radius2 = x * x + y * y
            polar = np.arctan(np.sqrt(radius2))
            sigma = math.radians(ACCEPTANCE_DEG) / (2 * math.sqrt(2 * math.log(2)))
            weight = np.exp(-(polar**2) / (2 * sigma * sigma)) / (1 + radius2) ** 1.5
            total = weight.sum()
            for distance_mm, offset_mm, radius_mm in CASES:
                centre = origin + rotation @ np.array([offset_mm, 0.0, -distance_mm])
                model.geom_pos[target] = centre
                model.geom_size[target, 0] = radius_mm
                mujoco.mj_forward(model, data)
                renderer.reset()
                renderer.render_as_needed(data)
                mask = renderer.segmentation_frames[camera][-1] == target
                lower = float(weight[binary_erosion(mask)].sum() / total)
                upper = float(weight[binary_dilation(mask)].sum() / total)
                raster = float(weight[mask].sum() / total)
                sphere = optics.Sphere(
                    "oracle_target",
                    tuple(pose.mm(v) for v in centre),
                    pose.mm(radius_mm),
                )
                optical = optics.sample(
                    columns, registration, mounts, state, (sphere,), ACCEPTANCE_DEG
                )
                predicted = float(optical.coverage[0, col])
                passed = bool(
                    mask.any()
                    and lower - PLANAR_BOUND <= predicted <= upper + PLANAR_BOUND
                )
                results.append(
                    {
                        "side": side,
                        "distance_mm": distance_mm,
                        "offset_mm": offset_mm,
                        "radius_mm": radius_mm,
                        "pixels": int(mask.sum()),
                        "raster_coverage": raster,
                        "one_pixel_interval": [lower, upper],
                        "planar_coverage": predicted,
                        "absolute_error": abs(raster - predicted),
                        "verdict": "pass" if passed else "fail",
                    }
                )
    finally:
        renderer.mj_renderer.close()
    dist = metadata.distribution("flygym")
    assets = {
        str(f): Path(dist.locate_file(f))
        for f in dist.files
        if str(f).startswith("flygym/assets/")
    }
    if manifest.git_info() != source:
        raise ValueError("source changed during camera check")
    report = {
        "source": source,
        "grade": "synthetic camera geometry only",
        "registration": "synthetic",
        "resolution": [RES, RES],
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
        "flygym": metadata.version("flygym"),
        "mujoco": mujoco.__version__,
        "assets_sha256": runstore.digest(runstore.files(assets)),
        "criterion": "one-pixel erosion/dilation interval plus existing 0.0085 planar bound; no tuned thresholds",
        "cases": results,
        "verdict": "pass" if all(r["verdict"] == "pass" for r in results) else "fail",
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2))
    if report["verdict"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
