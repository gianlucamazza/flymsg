import assert from "node:assert/strict";
import { test } from "node:test";
import { Box3, Frustum, Matrix4, PerspectiveCamera, Vector3, Vector4 } from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { linePages, visibleLinePages, writeVisibleEdges } from "../../src/flymsg/viz_static/geometry-pages.js";

const cube = (lo, hi) => [[1,0,0,-lo],[-1,0,0,hi],[0,1,0,-lo],[0,-1,0,hi],[0,0,1,-lo],[0,0,-1,hi]];
test("partition preserves every original edge, including duplicates and long cross-page edges", () => {
  const v = new Float32Array([-100,0,0,100,0,0,2,2,2,3,3,3]);
  const edges = new Uint32Array([2,3,0,1,2,3,1,0]);
  const pages = linePages(v, edges, 1);
  const full = visibleLinePages(pages, null);
  const output = new Uint32Array(edges.length);
  assert.equal(writeVisibleEdges(output, 0, edges, pages, full.visible), edges.length);
  assert.deepEqual(output, edges);
  const shown = visibleLinePages(pages, [cube(-1,1)]);
  const compact = new Uint32Array(2 * shown.edges);
  assert.equal(writeVisibleEdges(compact, 0, edges, pages, shown.visible), compact.length);
  assert.deepEqual([...compact], [0,1,1,0]); // neither endpoint lies in the view
  assert.deepEqual([...edges], [2,3,0,1,2,3,1,0]);
});

test("stereo uses the union; a one-eye peripheral edge is never discarded", () => {
  const v = new Float32Array([-2,0,0,-1.5,0,0,1.5,0,0,2,0,0]);
  const edges = new Uint32Array([0,1,2,3]);
  const pages = linePages(v, edges, 1);
  const left = cube(-3,0), right = cube(0,3);
  assert.equal(visibleLinePages(pages, [left]).edges, 1);
  assert.equal(visibleLinePages(pages, [right]).edges, 1);
  assert.equal(visibleLinePages(pages, [left,right]).edges, 2);
});

test("conservative pages contain every independently projected visible segment sample", () => {
  let seed = 9101;
  const rand = () => ((seed = (1664525 * seed + 1013904223) >>> 0) / 2**32);
  const v = Float32Array.from({ length: 6000 }, () => (rand() - .5) * 100);
  const edges = Uint32Array.from({ length: 2000 }, (_,i) => i);
  const pages = linePages(v, edges, 13);
  const local = new Matrix4().makeRotationY(.37).setPosition(5,-3,-8);
  for (let c = 0; c < 8; c++) {
    const camera = new PerspectiveCamera(35 + 4*c, 1.3, .1, 150);
    camera.position.set(c-4, 3, 40);
    camera.lookAt(0,0,0); camera.updateMatrixWorld(true);
    const clip = new Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).multiply(local);
    const f = new Frustum().setFromProjectionMatrix(clip);
    const planes = f.planes.map((p) => [...p.normal.toArray(),p.constant]);
    const shown = visibleLinePages(pages,[planes]);
    for (let e = 0; e < edges.length/2; e++) {
      const a = new Vector3().fromArray(v,3*edges[2*e]);
      const b = new Vector3().fromArray(v,3*edges[2*e+1]);
      for (let s = 0; s <= 16; s++) {
        const p = a.clone().lerp(b,s/16);
        const q = new Vector4(p.x,p.y,p.z,1).applyMatrix4(clip);
        if (q.w>0 && Math.abs(q.x)<=q.w && Math.abs(q.y)<=q.w && Math.abs(q.z)<=q.w)
          assert.equal(shown.visible[pages.edgePage[e]],1,`edge ${e}, sample ${s}, camera ${c}`);
      }
    }
    for (let p = 0; p < pages.sizes.length; p++) {
      const box = new Box3(new Vector3().fromArray(pages.bounds,6*p),new Vector3().fromArray(pages.bounds,6*p+3));
      if (f.intersectsBox(box)) assert.equal(shown.visible[p],1);
    }
  }
});

test("empty geometry, invalid endpoints, page capacity and source coordinates", () => {
  assert.equal(linePages(new Float32Array(),new Uint32Array()).sizes.length,0);
  assert.throws(() => linePages(new Float32Array(3),new Uint32Array([0,1])),RangeError);
  assert.throws(() => linePages(new Float32Array([NaN,0,0]),new Uint32Array([0,0])),RangeError);
  const edges = Uint32Array.from({length:1000},(_,i)=>i%2);
  const pages = linePages(new Float32Array([0,0,0,1,1,1]),edges,17);
  assert.equal(pages.sizes.reduce((a,b)=>a+b,0),500);
  assert.ok(Math.max(...pages.sizes)<=17);
});
