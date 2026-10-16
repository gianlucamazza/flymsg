import assert from "node:assert/strict";
import { test } from "node:test";
import * as T from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import {
  sourcePaths,
  projectSource,
  simplifyPath,
  sourceVertexView,
} from "../../src/flymsg/viz_static/bounded-paths.js";
import { verifyBoundedPaths } from "../../src/flymsg/viz_static/bounded-path-oracle.js";
const eye = { matrix: new T.Matrix4().toArray(), width: 100, height: 100 };
function run(vertices, edges, eyes = [eye]) {
  const positions = Float32Array.from(vertices),
    indices = Uint32Array.from(edges);
  const projections = projectSource(positions, eyes);
  const records = [...sourcePaths(positions.length / 3, indices)].map(
    (path) => ({ ...path, cuts: simplifyPath(path.vertices, projections) }),
  );
  return {
    records,
    positions,
    indices,
    report: verifyBoundedPaths(T, positions, indices, records, eyes),
  };
}
test("bounded paths reduce a straight chain and retain branches and every source edge", () => {
  const f = run(
    [0, 0, 0, 0.1, 0.001, 0, 0.2, 0, 0, 0.3, 0, 0, 0.2, 0.1, 0],
    [0, 1, 1, 2, 2, 3, 2, 4],
  );
  assert.equal(f.report.original_edges, 4);
  assert.equal(f.report.candidate_edges, 3);
  assert(f.report.maximum_error_px < 0.5);
});
test("stricter eye controls reduction and projected excursions are retained", () => {
  const vertices = [0, 0, 0, 0.1, 0.008, 0, 0.2, 0, 0],
    edges = [0, 1, 1, 2];
  assert.equal(run(vertices, edges).report.candidate_edges, 1);
  assert.equal(
    run(vertices, edges, [eye, { ...eye, height: 200 }]).report.candidate_edges,
    2,
  );
});
test("near and far clipping, cycles, parallel edges and self loops retain full paths", () => {
  for (const [v, e] of [
    [
      [0, 0, -2, 0.1, 0, 0, 0.2, 0, 0],
      [0, 1, 1, 2],
    ],
    [
      [0, 0, 2, 0.1, 0, 0, 0.2, 0, 0],
      [0, 1, 1, 2],
    ],
    [
      [0, 0, 0, 0.1, 0, 0, 0.2, 0.1, 0],
      [0, 1, 1, 2, 2, 0],
    ],
    [
      [0, 0, 0, 0.1, 0, 0],
      [0, 1, 0, 1],
    ],
    [
      [0, 0, 0],
      [0, 0],
    ],
  ])
    assert.equal(run(v, e).report.candidate_edges, e.length / 2);
});
test("independent verifier rejects missing provenance and an excessive chord", () => {
  const f = run([0, 0, 0, 0.1, 0.03, 0, 0.2, 0, 0], [0, 1, 1, 2]);
  assert.throws(
    () => verifyBoundedPaths(T, f.positions, f.indices, [], [eye]),
    /not completely/,
  );
  const records = structuredClone(f.records);
  records[0].cuts = [0, 2];
  assert.throws(
    () => verifyBoundedPaths(T, f.positions, f.indices, records, [eye]),
    /exceeds/,
  );
  records[0].edges = [0, 0];
  assert.throws(
    () => verifyBoundedPaths(T, f.positions, f.indices, records, [eye]),
    /duplicated/,
  );
});
test("perspective with off-axis stereo projections verifies using the pinned vector implementation", () => {
  const a = new T.PerspectiveCamera(60, 1, 0.1, 100),
    b = a.clone();
  b.position.x = 0.03;
  b.updateMatrixWorld(true);
  b.projectionMatrix.elements[8] = 0.15;
  const eyes = [a, b].map((c) => ({
    matrix: c.projectionMatrix.clone().multiply(c.matrixWorldInverse).toArray(),
    width: 1024,
    height: 1024,
  }));
  const f = run(
    [0, 0, -2, 0.01, 0.0001, -1.9, 0.02, 0, -1.8],
    [0, 1, 1, 2],
    eyes,
  );
  assert.equal(f.report.candidate_edges, 1);
  assert(f.report.maximum_error_px <= 0.5);
});

test("original source extraction excludes arena padding and checks endpoint owners", () => {
  const p = new Float32Array([9, 9, 9, 0, 0, 0, 0.1, 0, 0, 8, 8, 8]),
    owner = new Float32Array([4, 7, 7, 0]);
  const view = sourceVertexView(p, owner, 1, new Uint32Array([0, 1]), 7);
  assert.equal(view.buffer, p.buffer);
  assert.equal(view.length, 6);
  assert.throws(
    () => sourceVertexView(p, owner, 2, new Uint32Array([0, 1]), 7),
    /owner/,
  );
  assert.throws(
    () => sourceVertexView(p, owner, 3, new Uint32Array([0, 1]), 7),
    /bounds/,
  );
});

test("deterministic branching and disconnected graphs preserve independent topology and bounds", () => {
  let seed = 7;
  const random = () => {
    seed = (1664525 * seed + 1013904223) >>> 0;
    return seed / 2 ** 32;
  };
  const camera = new T.PerspectiveCamera(50, 1.6, 0.1, 100);
  const eyes = [-0.04, 0.04].map((x) => {
    const c = camera.clone();
    c.position.x = x;
    c.updateMatrixWorld(true);
    return {
      matrix: c.projectionMatrix
        .clone()
        .multiply(c.matrixWorldInverse)
        .toArray(),
      width: 1280,
      height: 800,
    };
  });
  for (let trial = 0; trial < 20; trial++) {
    const vertices = [],
      edges = [];
    for (let v = 0; v < 80; v++) {
      vertices.push(random() - 0.5, random() - 0.5, -2 - random());
      if (v && v % 17) edges.push(v, Math.floor(random() * v));
    }
    const f = run(vertices, edges, eyes);
    assert.equal(f.report.original_edges, edges.length / 2);
    assert(f.report.maximum_error_px <= 0.5);
  }
});
