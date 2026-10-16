import assert from "node:assert/strict";
import { test } from "node:test";
import * as T from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { auditSelection } from "../../src/flymsg/viz_static/bounded-runtime-oracle.js";
const p = Float32Array.from([
  -0.2, 0, -3, 0, 0.0001, -3, 0.2, 0, -3, 0, 0.2, -3,
]);
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
test("independent graph audit rejects missing paths, invented shortcuts and lost branches", () => {
  const source = Uint32Array.from([0, 1, 1, 2]),
    anchors = Uint8Array.from([1, 0, 1, 1]);
  const proof = auditSelection(
    T,
    p,
    source,
    Uint32Array.from([0, 2]),
    anchors,
    [eye],
  );
  assert(proof.maximum_error_px > 0 && proof.maximum_error_px < 0.5);
  assert.throws(
    () =>
      auditSelection(T, p, source, Uint32Array.from([0, 1]), anchors, [eye]),
    /anchor/,
  );
  assert.throws(
    () =>
      auditSelection(T, p, source, Uint32Array.from([0, 2, 0, 2]), anchors, [
        eye,
      ]),
    /invented/,
  );
  assert.throws(
    () =>
      auditSelection(
        T,
        p,
        Uint32Array.from([0, 1, 1, 2, 1, 3]),
        Uint32Array.from([0, 2, 1, 3]),
        anchors,
        [eye],
      ),
    /branch|candidate path/,
  );
  const moved = p.slice();
  moved[4] = 0.1;
  assert.throws(
    () =>
      auditSelection(T, moved, source, Uint32Array.from([0, 2]), anchors, [
        eye,
      ]),
    /half a pixel/,
  );
  const clipped = {
    ...eye,
    modelView: new T.Matrix4().makeTranslation(0, 0, 3).toArray(),
  };
  assert.throws(
    () =>
      auditSelection(T, p, source, Uint32Array.from([0, 2]), anchors, [
        clipped,
      ]),
    /clipped/,
  );
});
test("full original cycles and parallel edges remain verifiable", () => {
  const index = Uint32Array.from([0, 1, 1, 2, 2, 0, 0, 1]);
  assert.equal(
    auditSelection(T, p, index, index, Uint8Array.from([1, 1, 1, 1]), [eye])
      .source_edges,
    4,
  );
});
