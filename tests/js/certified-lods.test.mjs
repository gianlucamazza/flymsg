import assert from "node:assert/strict";
import { test } from "node:test";
import * as T from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { PrimitivePages } from "../../src/flymsg/viz_static/primitive-pages.js";
import {
  sourceAnchors,
  compilePageLods,
  composePageLod,
} from "../../src/flymsg/viz_static/certified-lods.js";
import {
  projectionErrorBound,
  certifiedPixelError,
} from "../../src/flymsg/viz_static/projection-error-bound.js";
function pages(vertices, index, maxBytes = 4096) {
  const position = Float32Array.from(vertices),
    edges = Uint32Array.from(index);
  const builder = new PrimitivePages({
    primitiveSize: 2,
    attributes: { position: { itemSize: 3 }, aNeuron: { itemSize: 1 } },
    maxBytes,
    preserveAnchors: true,
  });
  const result = [
    ...builder.append({
      key: "n",
      attributes: {
        position: { array: position, itemSize: 3 },
        aNeuron: { constant: 0, itemSize: 1 },
      },
      index: edges,
      anchors: sourceAnchors(position.length / 3, edges),
    }),
  ];
  const last = builder.flush();
  if (last) result.push(last);
  return result;
}
test("worker levels retain full source, branches, source ownership and a finite byte budget", () => {
  const input = pages(
    [0, 0, 0, 100, 0.1, 0, 200, 0, 0, 300, 0, 0, 200, 100, 0],
    [0, 1, 1, 2, 2, 3, 2, 4],
  );
  const catalogue = compilePageLods(input[0]);
  assert(catalogue.metadata.cpu_index_bytes <= 2 * input[0].index.byteLength);
  assert.deepEqual(
    [...composePageLod(catalogue, { 0: 0 })],
    [...input[0].index],
  );
  const level = [...catalogue.variants.keys()].find((n) => n !== 0);
  assert(level);
  const coarse = composePageLod(catalogue, { 0: level });
  assert.equal(coarse.length, 6);
  assert(coarse.includes(2));
  assert(coarse.includes(3));
  assert(coarse.includes(4));
});
test("a global branch split across tiny pages remains an anchor", () => {
  for (const page of pages(
    [0, 0, 0, 100, 0, 0, 200, 0, 0, 100, 100, 0],
    [0, 1, 1, 2, 1, 3],
    100,
  )) {
    const catalogue = compilePageLods(page);
    for (const variant of catalogue.variants.values()) {
      const branch = page.boundedSource.origins.findIndex((n) => n === 1);
      if (branch >= 0) assert(variant.index.includes(branch));
    }
  }
});
test("cycles and parallel edges retain their original topology", () => {
  for (const page of pages(
    [0, 0, 0, 100, 0, 0, 200, 0, 0],
    [0, 1, 1, 2, 2, 0, 0, 1],
  )) {
    const catalogue = compilePageLods(page);
    for (const variant of catalogue.variants.values())
      assert.equal(variant.index.length, page.index.length);
  }
});
test("projection certificate bounds independent dense sample projections and rejects clip uncertainty", () => {
  const camera = new T.PerspectiveCamera(55, 1.5, 0.1, 100);
  const eye = {
    modelView: new T.Matrix4().toArray(),
    projection: camera.projectionMatrix.toArray(),
    width: 1200,
    height: 800,
  };
  const box = { min: [-0.4, -0.3, -4], max: [0.4, 0.3, -2] };
  const bound = projectionErrorBound(box, eye);
  assert(Number.isFinite(bound.scale));
  for (let i = 0; i < 100; i++) {
    const a = new T.Vector3(-0.3 + i * 0.006, 0.1 * Math.sin(i), -3);
    const b = a.clone().add(new T.Vector3(0.0001, -0.0002, 0.00015));
    const x = a.clone().applyMatrix4(camera.projectionMatrix),
      y = b.clone().applyMatrix4(camera.projectionMatrix);
    const actual = Math.hypot((x.x - y.x) * 600, (x.y - y.y) * 400);
    assert(actual <= certifiedPixelError(a.distanceTo(b), bound));
  }
  assert(
    !Number.isFinite(
      projectionErrorBound({ min: [0, 0, -1], max: [1, 1, 0] }, eye).scale,
    ),
  );
  assert(
    !Number.isFinite(
      projectionErrorBound(box, eye, { float: 16, subpixel: 4 }).scale,
    ),
  );
});

test("precision uncertainty and malformed source boxes force exact fallback", () => {
  const eye = {
    modelView: new T.Matrix4().toArray(),
    projection: new T.PerspectiveCamera(
      55,
      1,
      0.1,
      100,
    ).projectionMatrix.toArray(),
    width: 1000,
    height: 1000,
  };
  for (const precision of [
    {},
    { float: 23 },
    { float: NaN, subpixel: 4 },
    { float: 23, subpixel: Infinity },
  ])
    assert(
      !Number.isFinite(
        projectionErrorBound(
          { min: [0, 0, -3], max: [1, 1, -2] },
          eye,
          precision,
        ).scale,
      ),
    );
  assert(
    !Number.isFinite(
      projectionErrorBound({ min: [2, 0, -3], max: [1, 1, -2] }, eye).scale,
    ),
  );
});

test("off-axis stereo and source-unit cancellation bound independently rounded float32 projections", () => {
  const camera = new T.PerspectiveCamera(55, 1.2, 0.1, 5000);
  camera.position.set(750, 270, 590);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  const data = new T.Matrix4().makeScale(0.001, -0.001, -0.001);
  data.setPosition(-376, 313, 538);
  const modelView = new T.Matrix4()
    .multiplyMatrices(camera.matrixWorldInverse, data)
    .toArray();
  const box = { min: [162000, 217000, 208000], max: [305000, 318000, 307000] };
  const f = Math.fround;
  const multiply = (m, v) =>
    Array.from({ length: 4 }, (_, r) => {
      let value = 0;
      for (let k = 0; k < 4; k++)
        value = f(value + f(f(m[k * 4 + r]) * f(v[k])));
      return value;
    });
  for (const offset of [-0.08, 0.11]) {
    const projection = camera.projectionMatrix.toArray();
    projection[8] = offset;
    const eye = { modelView, projection, width: 1832, height: 1920 },
      bound = projectionErrorBound(box, eye);
    assert(Number.isFinite(bound.scale));
    const project = (v) => {
      const q = multiply(projection, multiply(modelView, [...v, 1]));
      return [f(q[0] / q[3]) * 916, f(q[1] / q[3]) * 960];
    };
    for (let i = 0; i < 200; i++) {
      const a = [200000 + i * 100, 250000 + 1000 * Math.sin(i), 250000],
        b = [a[0] + 10, a[1] - 15, a[2] + 8];
      const x = project(a),
        y = project(b),
        actual = Math.hypot(x[0] - y[0], x[1] - y[1]);
      assert(actual <= certifiedPixelError(Math.hypot(10, 15, 8), bound));
    }
  }
});

test("all six clip-plane intersections conservatively retain full source", () => {
  const camera = new T.PerspectiveCamera(90, 1, 0.1, 100),
    eye = {
      modelView: new T.Matrix4().toArray(),
      projection: camera.projectionMatrix.toArray(),
      width: 1000,
      height: 1000,
    };
  for (const box of [
    { min: [-4, 0, -3], max: [0, 1, -2] },
    { min: [0, 0, -3], max: [4, 1, -2] },
    { min: [0, -4, -3], max: [1, 0, -2] },
    { min: [0, 0, -3], max: [1, 4, -2] },
    { min: [0, 0, -1], max: [0.1, 0.1, -0.01] },
    { min: [0, 0, -101], max: [0.1, 0.1, -99] },
  ])
    assert(!Number.isFinite(projectionErrorBound(box, eye).scale));
});
