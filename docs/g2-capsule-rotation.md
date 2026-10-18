# G2: eyemap → head-capsule rotation (feasibility, 2026-10-18)

Status: **feasible, not measured, protocol not locked; landmarks algorithmic, measurement deferred.** This is half of the head
registration: the rotation from the Zhao et al. 2025 eyemap frame to a head-capsule frame
built from the landmarks the Ispizua, Abe et al. 2026 pipeline tracks (`Antenna_Base`,
`EyeL`, `EyeR`). It composes later with a measured head-to-thorax angle, which is still
unavailable ([leads](https://github.com/gianlucamazza/flymsg/blob/main/docs/leads.md), G2). Nothing here is a value for `pose.Registration`.
Feasibility by an agent, with key facts re-checked; no angle has been computed.

## Findings

- Per-fly 3D lens and cone positions are public in `reiserlab/eyemap_T4`
  (`99d2a43`, GPL-3.0; not copied here) as `data/microCT/{20231107,20240530,20240701}.RData`.
  flymsg's `data/raw/eyemap/eyemap.RData` holds unit directions only.
- The rigid µCT → eyemap map (`proc_uCT.R` lines 36–79: equator normal from the authors'
  `UP`/`DOWN` cone labels, front from the lens/cone PCA, origin at their centroid) is
  recomputed for all three flies to ~10⁻¹⁶; the saved lenses differ from it only by one
  hexagonal smooth (median 0.33 µm).
- `20240701.RData`, the map flymsg uses, is the volume `20240710_PTA.zip` of figshare
  doi:10.25378/janelia.29111339.v1 (CC BY 4.0; 970 8-bit TIFFs, 1.0065 µm voxels): the lens
  cloud follows both corneal rims after a one-facet translation of about (−12, 0, −4)
  voxels. The other two pairings are unverified name matches.
- On that volume the antennal sockets and the dorso-posterior cuticle corner of each eye are
  inside the field. The corners are rounded: raters will scatter by several voxels.
- Limits: three fixed female heads (PTA, ethanol, no shrinkage correction), n = 3; the
  equator is the authors' labels; flymsg's left eye is a mirror, so yaw, roll or a lateral
  shift cannot enter `Registration` without a contract change.

**Decision (2026-10-18): the landmarks are placed by an algorithm, not by raters.** No
human raters with a 3D viewer are available, and a language model reading 2D renders is not
counted as a rater. The landmark definitions below become code, committed with tests on
synthetic volumes before any of the three volumes is processed by it; the code is then part
of the locked protocol. The "Raters" section is replaced by a sensitivity check: each
landmark is recomputed with `t` moved by ±1 voxel per axis and the cuticle threshold moved
by ±10 %, and the head is discarded if any landmark moves by more than the same **25 µm**.
That spread is reported in micrometres and degrees, separate from the between-fly SD.

**Priority: deferred.** This rotation is only the eyemap → capsule half. It cannot enter
`Registration` until a measured head-to-thorax angle exists, and the only candidate source
is the undeposited Ispizua landmark set ([leads](https://github.com/gianlucamazza/flymsg/blob/main/docs/leads.md), G2). The algorithm is written when
that request has an answer, so the measurement is not left unused.

## Protocol draft (not locked)

The following is the text to freeze. Changing a number after the first angle has been computed voids the batch.

**Objects.** Three female heads, the three PTA volumes of figshare `10.25378/janelia.29111339.v1`. One rotation per head: capsule ← eyemap. No thorax landmark. No `Registration` write.

**Frames.**

- Export µm: recovered as `center + scores @ rotation.T` from `eye_pca`, sorted as R `order(x,y,z)`.
- Eyemap: `p_eyemap = (p_µm − center) @ mrot`, with `mrot` from `proc_uCT.R` lines 36–79 using `ind_Up` and `ind_Down`. Saved `vn`, `vf`, `vleft` are ignored.
- TIFF voxel `v` → export µm by `p_µm = (v − t) * s`, where `s` is the `Info.JPG` pixel size of that zip and `t` is the translation below.
- Capsule: origin `E = (EyeL + EyeR) / 2`, `+y` the fly's left, the unit vector along `EyeL − EyeR`; `+x` anterior, `Antenna_Base − E` with its `+y` component removed, normalised; `+z` dorsal = `x × y`, right-handed. Built from points already in the eyemap frame.

**Zip check, per head, before clicks.** A slab of the lens cloud must follow both corneal rims under `(identity permutation, no flip, s from Info.JPG)`. If it does not, that zip is not that `RData`, and the head is not measured. Expected, and confirmed only for the first: `20240701` ↔ `20240710_PTA.zip` at `s = 1.0065` µm. `20240530` ↔ `20240530_PTA.zip` and `20231107` ↔ `2023110_PTA7.zip` are name hypotheses.

**Translation `t`, frozen per head.** On a 1-voxel grid, using every lens spot and no landmark, choose `t` to maximise mean voxel intensity at the mapped spots. Record the grid, the winner, and the mean. For 20240710 the 4-voxel-grid result to beat or confirm is `t = (−12, 0, −4)`. Do not revisit `t` after a click.

**Landmark definitions.**

- `Antenna_Base`: the point on the head-capsule cuticle halfway between the two antennal sockets. The arista, the antennal shaft, and the proboscis are not this point.
- `EyeL`, `EyeR`: the dorso-posterior cuticle tip of each compound eye, dorsal as given by `vn` (the UP side), posterior as the side toward the thoracic fragment. The point is the cuticle corner beyond the last lenses. Left and right are assigned by `ind_left_lens`, so `EyeL` is the fly's left.
- Length gate, from the head-scout protocol: reject the head if `|Antenna_Base − E| < 0.05` mm or `> 0.80` mm, or if the posterior eye margin of either eye is cut by the reconstruction field.

**Raters (superseded by the 2026-10-18 decision above; kept as drafted).** Two raters. Each clicks each of the three points twice, on separate passes, with the previous click hidden. All twelve numbers (2 × 2 × 3) are stored before any frame is built. If the two raters' means for any point differ by more than **25 µm**, that head is discarded or both raters repeat the whole head. The 25 µm figure is the Ispizua tracking-error scale used by the head scout. It is not refit after seeing a pitch. Within-rater SD and between-rater SD are reported in micrometres and in degrees, separate from the between-fly SD.

**Angle.** Positive pitch is nose-down: `Ry(θ)` with rows `[cos θ, 0, sin θ]`, `[0, 1, 0]`, `[−sin θ, 0, cos θ]`, acting on eyemap vectors to produce capsule vectors. Publish, per head, pitch, yaw, roll, and the eyemap-frame y coordinate of `E`. Across heads, publish the mean pitch and the sample SD with divisor n − 1. n = 3. If a head is discarded, n drops and the discard is named. There is no replacement head in this dataset.

**Sagittal gate, applied after the angle exists and without changing the angle.** A head fails the gate if `|yaw| > 2.04°` or `|roll| > 2.04°` or the eyemap-y component of `E` has absolute value `> 25 µm`. The 2.04° bound is `atan2(0.025 mm, 0.7035 mm)`, rounded to 0.01°. The 0.7035 mm is the Y separation of the two eye centres in the 20240710 volume, voxels 153 and 852 at 1.0065 µm. A failing head is still reported. It is not loaded into `Registration`. Passing the gate is also not a licence to load: `optics.sample` additionally requires a pure pitch and `|position_y| ≤ 1e-12` m, and the capsule origin is not the eyemap origin. Loading is a later contract decision.

**Out of scope for the person who measures.** qpos and any inverse-kinematics site. NeuroMechFly's 20° head pose. Hengstenberg 1991. Fenk et al. 2022. Any pitch read off `mrot` itself. Any use of the thoracic muscle block as `c_thorax`. Copying these `RData` files into the flymsg repo.
