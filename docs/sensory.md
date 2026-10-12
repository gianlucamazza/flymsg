# Experimental sensory encoder (M1a)

Status: exploratory, **not** validated biological perception.

`flymsg.sensory` provides a deterministic looming geometry-to-rate encoder.
A circular object of radius `r` approaches along the viewing axis at constant
speed `v`, distance `d(t) = d0 - vt`. Angular size is
`2 atan(r/d)` and angular expansion rate is `2rv/(d²+r²)`.

`encode_looming` samples the optical signal on an integer-microsecond grid,
then maps expansion to a bounded, nonnegative rate:
`min(max_rate, baseline + gain * angular_velocity)`.

This is **not** a measured LC4 response, a retinal model, or a Poisson spike
generator. No connectome body IDs are assigned. The existing `flymsg sim`,
`validate`, and `behavior` paths remain unchanged. In particular, the
29/29 calibrated checks and the failed held-out/silencing checks cannot be
claimed as evidence for this encoder.

## Usage

```python
from flymsg.sensory import LoomingStimulus, encode_looming

samples = encode_looming(LoomingStimulus(
    radius_m=0.01, initial_distance_m=0.5,
    approach_speed_m_s=0.1, duration_us=100_000,
))
print(samples[0])
```

## Next gates

1. Experimental LC4/LPLC2 tuning data and uncertainty bounds.
2. Explicit mapping of sample rates to MaleCNS sensory body IDs.
3. Online neural stepping that accepts a time-varying drive without changing
   the validated kernel's scheduling or seeded reproducibility.
4. Verified neuromuscular map, body dynamics, and physical sensory feedback.
5. Held-out, pre-registered behavior tests, including negative controls.

The existing M0 embodiment fixture remains synthetic. Do not label the
system as a physically realistic embodied fly until these gates pass.
