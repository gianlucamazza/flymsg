// Full-original ID pixels are the independent source-stroke support. Expand by
// half a pixel plus a conservative raster margin; never derive it from candidate pixels.
function bytes(image) {
  return Uint8Array.from(atob(image.base64), (c) => c.charCodeAt(0));
}
export function verifyRasterFootprint(
  original,
  candidate,
  sourceIds,
  width,
  height,
  { x = 2, y = 2 } = {},
) {
  const a = bytes(original),
    b = bytes(candidate),
    ids = bytes(sourceIds),
    size = width * height;
  if (
    !Number.isInteger(width) ||
    !Number.isInteger(height) ||
    width < 1 ||
    height < 1 ||
    [a, b, ids].some((p) => p.length !== size * 4) ||
    ![x, y].every((v) => Number.isInteger(v) && v >= 2)
  )
    throw Error("Invalid raster footprint");
  // Separable sliding windows avoid work proportional to the bloom radius.
  const horizontal = new Uint8Array(size),
    mask = new Uint8Array(size);
  for (let row = 0; row < height; row++) {
    let count = 0;
    const occupied = (col) => {
      const i = (row * width + col) * 4;
      return +(ids[i] !== 0 || ids[i + 1] !== 0 || ids[i + 2] !== 0);
    };
    for (let col = 0; col <= Math.min(x, width - 1); col++)
      count += occupied(col);
    for (let col = 0; col < width; col++) {
      horizontal[row * width + col] = +(count > 0);
      if (col - x >= 0) count -= occupied(col - x);
      if (col + x + 1 < width) count += occupied(col + x + 1);
    }
  }
  for (let col = 0; col < width; col++) {
    let count = 0;
    for (let row = 0; row <= Math.min(y, height - 1); row++)
      count += horizontal[row * width + col];
    for (let row = 0; row < height; row++) {
      mask[row * width + col] = +(count > 0);
      if (row - y >= 0) count -= horizontal[(row - y) * width + col];
      if (row + y + 1 < height)
        count += horizontal[(row + y + 1) * width + col];
    }
  }
  let changed = 0,
    covered = 0;
  for (let i = 0; i < size; i++) {
    covered += mask[i];
    if (a.subarray(i * 4, i * 4 + 4).some((v, c) => v !== b[i * 4 + c])) {
      changed++;
      if (!mask[i])
        throw Error("Colour changed outside original stroke footprint");
    }
  }
  return {
    changed_pixels: changed,
    footprint_pixels: covered,
    total_pixels: size,
    radius: { x, y },
    qualification:
      "support only; geometric proof and human visual acceptance remain separate",
  };
}

export function bloomFootprint(api, width, height) {
  if (!api.bloom.enabled) return { x: 2, y: 2 };
  const bloom = api.bloom;
  if (
    bloom.separableBlurMaterials.length !== bloom.renderTargetsHorizontal.length
  )
    throw Error("Unknown bloom support");
  let x = 4,
    y = 4;
  for (let i = 0; i < bloom.separableBlurMaterials.length; i++) {
    const radius = bloom.separableBlurMaterials[i].defines.KERNEL_RADIUS,
      target = bloom.renderTargetsHorizontal[i];
    if (
      !Number.isInteger(radius) ||
      radius < 1 ||
      !(target.width > 0 && target.height > 0)
    )
      throw Error("Unknown bloom kernel");
    // Each mip reads the preceding blurred mip. Include both bilinear taps,
    // downsampling and final composition support in physical output pixels.
    x += ((radius + 2) * width) / target.width;
    y += ((radius + 2) * height) / target.height;
  }
  return { x: Math.ceil(x), y: Math.ceil(y) };
}
