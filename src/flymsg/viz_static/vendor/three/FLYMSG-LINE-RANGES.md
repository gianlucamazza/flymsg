# FlyMSG indexed line ranges (Three.js r170)

This MIT-licensed extension keeps the existing WebGLRenderer, shaders, uniforms,
binding-state management, indexed-buffer renderer and context lifecycle. It adds
one dispatch branch for original-order line ranges. It does not impersonate a
BatchedMesh or intercept WebGL calls in production.

`LineSegments` may set `isMultiDrawLineSegments = true` and supply `lineStarts`
(Int32Array of **byte** offsets), `lineCounts` (Int32Array of index counts), and
`lineDrawCount`. They reference the object's existing index buffer. The caller
preserves original order, validates capacity and keeps ranges inside that buffer.
Use one geometry group covering the arena with the existing shared material.
Colour, picking and depth therefore use exactly the same range submission.

The branch requires indexed LineSegments and WEBGL_multi_draw; unsupported use
throws. FlyMSG checks the capability first and retains bounded public geometry
groups/compaction on other renderers. Its native list is capped at 16,384 ranges.
There is no new vertex shader or gl_DrawID dependency. Other objects follow the
unchanged upstream branch. `FLYMSG_LINE_RANGES = 1` identifies this capability.

The only changes to the pinned minified upstream module are reproducible with
`python scripts/patch_three_line_ranges.py`; `--check` reverses the transform in
memory and verifies the exact upstream SHA-256. It refuses unreviewed upstream
versions. The original Three.js license and copyright remain in LICENSE and in
the module header. Upgrade this extension explicitly alongside a Three upgrade.

Correctness gates compare the untouched full-index dispatch with range dispatch,
including equal-depth ownership, clipping, off-axis/stereo views and colour/ID/
depth outputs. Real-device probes count actual index uploads and compare every
moving colour image. Passing these does not qualify XR frame cadence.
