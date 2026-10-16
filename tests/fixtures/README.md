# Projection certificate reference inputs

`projection-bound-b4427da.json` records 1,120 expected certificates across 80
camera cases, sampled from captured full-scene 4/16 MiB page boxes. Expectations
come from unchanged commit `b4427da`, not the optimized implementation. The file
records the reference source SHA-256, original inventory hashes and explicit
unproved cases. Unit tests compare the prepared implementation bit for bit.

The original inventories and camera transforms are retained in
`docs/evidence/quest-bounded-motion-veto-2026-10-16.zip` and
`docs/evidence/quest-bounded-corrected-readback-2026-10-16.zip`. Cases use the
recorded native camera/data transform, 40 translated poses with two offsets,
viewport 1280 by 670 and conservative float/subpixel precision 23/4. These are
numeric regression inputs, not physical eye poses or cadence measurements.

Audit the expected values against the pinned source from local Git history:

```bash
node scripts/check_projection_fixture.mjs
```

The audit imports only the frozen source and does not generate or overwrite
expected values using the candidate. A separate exploratory replay checked
188,240 certificates across every captured box; the smaller corpus keeps the
independent reference in routine CI without a complete-scene browser run.
