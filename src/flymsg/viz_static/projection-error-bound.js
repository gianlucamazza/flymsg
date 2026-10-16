// Conservative source-space Lipschitz certificate for the actual uploaded matrices.
const unit = 2 ** -24,
  gamma = (7 * unit) / (1 - 7 * unit);
function row(m, r) {
  return [m[r], m[r + 4], m[r + 8], m[r + 12]];
}
function dot(a, b) {
  return a.reduce((sum, x, i) => sum + x * b[i], 0);
}
const norm = (a) => Math.hypot(...a.slice(0, 3));
export function projectionErrorBound(
  box,
  eye,
  precision = { float: 23, subpixel: 4 },
) {
  if (
    !Number.isInteger(precision?.float) ||
    !Number.isInteger(precision?.subpixel) ||
    precision.float < 23 ||
    precision.subpixel < 4 ||
    precision.subpixel > 32 ||
    !box ||
    box.min?.length !== 3 ||
    box.max?.length !== 3 ||
    box.min.some((v, i) => v > box.max[i]) ||
    !eye?.modelView ||
    !eye?.projection
  )
    return { scale: Infinity, rounding: Infinity };
  const mv = Array.from(eye.modelView, Math.fround),
    p = Array.from(eye.projection, Math.fround);
  if (
    mv.length !== 16 ||
    p.length !== 16 ||
    ![...mv, ...p, ...box.min, ...box.max, eye.width, eye.height].every(
      Number.isFinite,
    ) ||
    !(eye.width > 0 && eye.height > 0)
  )
    return { scale: Infinity, rounding: Infinity };
  const absolute = [
    ...box.min.map((x, i) => Math.max(Math.abs(x), Math.abs(box.max[i]))),
    1,
  ];
  const vBound = Array.from({ length: 4 }, (_, i) =>
    dot(row(mv, i).map(Math.abs), absolute),
  );
  const vError = vBound.map((v) => gamma * v);
  const clipError = Array.from({ length: 4 }, (_, i) => {
    const coefficients = row(p, i).map(Math.abs);
    return (
      dot(coefficients, vError) +
      gamma *
        dot(
          coefficients,
          vBound.map((v, j) => v + vError[j]),
        )
    );
  });
  const composite = Array.from({ length: 4 }, (_, r) =>
    Array.from({ length: 4 }, (_, c) => {
      let sum = 0;
      for (let k = 0; k < 4; k++) sum += p[k * 4 + r] * mv[c * 4 + k];
      return sum;
    }),
  );
  const minimum = [Infinity, Infinity, Infinity, Infinity],
    maximum = [-Infinity, -Infinity, -Infinity, -Infinity];
  const clipMargins = Array.from({ length: 3 }, () => [Infinity, Infinity]);
  for (let mask = 0; mask < 8; mask++) {
    const x = [...box.min.map((v, i) => ((mask >> i) & 1 ? box.max[i] : v)), 1];
    const q = composite.map((a) => dot(a, x));
    for (let i = 0; i < 4; i++) {
      minimum[i] = Math.min(minimum[i], q[i]);
      maximum[i] = Math.max(maximum[i], q[i]);
    }
    for (let axis = 0; axis < 3; axis++) {
      clipMargins[axis][0] = Math.min(clipMargins[axis][0], q[3] + q[axis]);
      clipMargins[axis][1] = Math.min(clipMargins[axis][1], q[3] - q[axis]);
    }
  }
  const doubleGuard =
    128 *
    Number.EPSILON *
    Math.max(1, ...vBound, ...minimum.map(Math.abs), ...maximum.map(Math.abs));
  const w = minimum[3] - doubleGuard;
  if (
    !(
      w > clipError[3] + doubleGuard &&
      clipMargins.every((margins, axis) =>
        margins.every(
          (margin) => margin > clipError[axis] + clipError[3] + doubleGuard,
        ),
      )
    )
  )
    return { scale: Infinity, rounding: Infinity };
  const c = norm(composite[3]),
    axes = [0, 1].map((axis) => {
      const n =
        Math.max(Math.abs(minimum[axis]), Math.abs(maximum[axis])) +
        doubleGuard;
      const size = (axis === 0 ? eye.width : eye.height) / 2;
      const scale = (norm(composite[axis]) / w + (n * c) / (w * w)) * size;
      const error =
        (clipError[axis] / (w - clipError[3]) +
          (n * clipError[3]) / (w * (w - clipError[3])) +
          (2 * unit * n) / w) *
        size;
      return { scale, error };
    });
  const scale = Math.hypot(...axes.map((a) => a.scale));
  const rounding =
    2 * Math.hypot(...axes.map((a) => a.error)) +
    Math.SQRT2 / 2 ** precision.subpixel +
    doubleGuard;
  return Number.isFinite(scale + rounding)
    ? { scale, rounding }
    : { scale: Infinity, rounding: Infinity };
}
export function certifiedPixelError(error, bounds) {
  if (
    !Number.isFinite(error) ||
    error < 0 ||
    !Number.isFinite(bounds?.scale) ||
    bounds.scale < 0 ||
    !Number.isFinite(bounds?.rounding) ||
    bounds.rounding < 0
  )
    return Infinity;
  return bounds.scale * error + bounds.rounding;
}
