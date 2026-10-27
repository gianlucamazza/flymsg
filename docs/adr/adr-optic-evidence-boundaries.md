# ADR: optic evidence boundaries and missing-anatomy diagnostics

Status: implemented under the optic-system audit mandate, 2026-10-27.

The existing graded eye, runtime and closed-loop ADRs remain authoritative. A valid
numerical input must not imply measured physiology, and unavailable anatomy must
remain distinguishable from darkness.

Decisions:

1. Validate the retinal input boundary without changing historical valid arithmetic.
2. Keep strongest-output assignments unchanged; publish a separate mask table covering
   every simulated receptor, including unassigned cells and unknown laterality.
3. Label transferred directions INFERRED and unavailable ones UNKNOWN. Source rays
   measured in another preparation do not establish measured MaleCNS/body registration.
4. Verify pinned eyemap bytes on download, cache reuse and direct parsing; preserve
   failed files rather than silently redownload or accept different anatomy.
5. New causal/convergence evidence uses a separate versioned SYNTHETIC protocol.
   Historical T4/T5 locks and negative results remain unchanged. The existing runtime
   is the only executor used by the new witness.
6. Missing physiological transfer/registration data produce an explicit scientific
   no-go while independent engineering work can continue.

Tradeoff: invalid inputs that formerly truncated or propagated now raise ValueError;
duplicate lens keys raise MergeError. Valid input numerics are unchanged. Extra mask
output is additive, and original parquet schemas remain unchanged. No physiological
parameters or historical serializers change. Reverting these diagnostics leaves the
existing graded and Poisson baseline paths intact.

Requirements, tests, source identities and remaining gates are in the
[optic audit](../report/optic-system-audit-2026-10-27.md).
