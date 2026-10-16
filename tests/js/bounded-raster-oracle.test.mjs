import assert from "node:assert/strict";
import { test } from "node:test";
import {
  verifyRasterFootprint,
  bloomFootprint,
} from "../../src/flymsg/viz_static/bounded-raster-oracle.js";
const image = (bytes) => ({ base64: Buffer.from(bytes).toString("base64") });
test("colour changes require independent full-original stroke support, including borders", () => {
  const width = 13,
    height = 11,
    size = width * height * 4,
    a = new Uint8Array(size),
    ids = new Uint8Array(size);
  const seeds = [
    [0, 0],
    [6, 5],
    [12, 10],
  ];
  for (const [x, y] of seeds) ids[(y * width + x) * 4] = 1;
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      const b = a.slice();
      b[(y * width + x) * 4] = 1;
      const admitted = seeds.some(
        ([sx, sy]) => Math.abs(x - sx) <= 2 && Math.abs(y - sy) <= 2,
      );
      const verify = () =>
        verifyRasterFootprint(image(a), image(b), image(ids), width, height);
      if (admitted) assert.equal(verify().changed_pixels, 1);
      else assert.throws(verify, /outside/);
    }
  const b = a.slice();
  b[4 * width * height - 1] = 1;
  assert.throws(
    () =>
      verifyRasterFootprint(
        image(a),
        image(b),
        image(new Uint8Array(size)),
        width,
        height,
      ),
    /outside/,
  );
});
test("bloom support follows every progressive pinned mip, not a local pixel-equality claim", () => {
  const api = {
    bloom: {
      enabled: true,
      separableBlurMaterials: [
        { defines: { KERNEL_RADIUS: 3 } },
        { defines: { KERNEL_RADIUS: 5 } },
      ],
      renderTargetsHorizontal: [
        { width: 100, height: 50 },
        { width: 50, height: 25 },
      ],
    },
  };
  assert.deepEqual(bloomFootprint(api, 200, 100), { x: 42, y: 42 });
  api.bloom.enabled = false;
  assert.deepEqual(bloomFootprint(api, 200, 100), { x: 2, y: 2 });
});
