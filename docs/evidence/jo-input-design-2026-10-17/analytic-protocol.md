# JO input design: preregistered mathematical controls

Status: synthetic design diagnostics only, 2026-10-17. Written before executing
`analytic-controls.py`. No measured traces, neural model, JO adapter, gain fitting,
biological qualification or held-out response data are involved.

Use only Python standard-library deterministic finite constructions. Every case must
pass an exact assertion or an explicitly stated floating-point tolerance of 1e-12.
Failure means the mathematical argument or diagnostic is wrong; passing demonstrates
only the stated counterexample, never an empirical property of JO neurons.

1. **Envelope non-identifiability.** Two distinct integer-frequency carriers, 100 and
   200 Hz over 10 ms sampled at 10 kHz, have the same prescribed constant unit envelope.
   Assert distinct waveforms and identical envelopes. Interpretation: a driver consuming
   only that envelope has no information to distinguish those carriers.
2. **Acquisition alias.** Sample 101 and 111 Hz unit cosine signals on a 10 Hz clock at
   t = k/10 seconds for k = 0..9. Assert equality within 1e-12. Interpretation: this
   abstract sampled signal cannot recover its frequency uniquely. This is explicitly
   not a calcium forward model and does not assert fluorescence follows these cosines.
3. **Amplitude convention.** For a sine with peak amplitude 2 in one fixed unit,
   peak-to-peak is 4 and RMS is sqrt(2). Assert the consistent round trips and that
   interpreting peak-to-peak as peak produces factor-two error. Two different stated
   acoustic impedances, 2 and 4 in consistent abstract units, map the same pressure
   amplitude 2 to velocities 1 and 0.5 under u=p/Z. Interpretation: pressure alone
   cannot specify velocity when impedance is unknown.
4. **Half-open bins, multiplicity and alignment.** On a 100 us grid over [0,300 us),
   events at 0, 99, 100, 299 and 300 us yield counts [2,1,1], with 300 excluded.
   Assert total 4, binary occupancy total 3, and a non-aligned onset at 150 us requires
   aligned replay at 200 us under ceiling quantization, with delay 50 us. Floor mapping
   would leak 50 us before onset. Interpretation: boolean bins lose events and onset
   rounding must be specified; this does not choose an eventual replay policy.
5. **Rates do not identify population correlation.** Two binary eight-bin trains each
   contain four events. Pairing the first with itself gives correlation +1; pairing it
   with its complement gives -1. Assert identical per-neuron mean rates and different
   correlations. Interpretation: marginal rates cannot select a population covariance.
6. **Normalized tuning does not identify gain.** The normalized shape [0.25,1,0.5]
   multiplied by gains 20 and 80 gives different absolute traces, both normalizing to
   the same shape. Assert fourfold amplitude ratio and identical normalization.
   Interpretation: normalized band-pass evidence alone cannot determine absolute Hz.

Output JSON must record this protocol SHA256, script SHA256, six named outcomes,
assertion count, synthetic-only scope and explicit exclusions. No artifact hashes
are scientific calibration. These controls leave data acquisition, eligibility,
source-mode ADR acceptance and prospective experimental input protocol outstanding.
