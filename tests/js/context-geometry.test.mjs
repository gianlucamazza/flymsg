import assert from "node:assert/strict";
import { test } from "node:test";
import { prepareNeuropil, prepareSomata } from "../../src/flymsg/viz_static/context-geometry.js";
import { parseLegacyMesh } from "../../src/flymsg/viz_static/precomputed.js";

test("only transferred worker-owned legacy geometry opts into zero-copy views", () => {
  const buffer = new ArrayBuffer(52);
  new DataView(buffer).setUint32(0,3,true);
  new Float32Array(buffer,4,9).set([0,0,0,1,0,0,0,1,0]);
  new Uint32Array(buffer,40,3).set([0,1,2]);
  const copied = parseLegacyMesh(buffer), owned = parseLegacyMesh(buffer,{copy:false});
  assert.notEqual(copied.vertices.buffer,buffer);
  assert.equal(owned.vertices.buffer,buffer);
  assert.equal(owned.indices.buffer,buffer);
  assert.deepEqual(copied.vertices,owned.vertices);
  assert.deepEqual(copied.indices,owned.indices);
});

test("worker context assembly preserves fragment order, rebases every index and finishes full normals", () => {
  const parts = [
    { vertices: new Float32Array([0,0,0, 1,0,0, 0,1,0]), indices: new Uint32Array([0,1,2]) },
    { vertices: new Float32Array([0,0,1, 0,1,1, 1,0,1]), indices: new Uint32Array([0,1,2]) },
  ];
  const before = parts.map((p)=>p.vertices.slice());
  const result = prepareNeuropil(parts);
  assert.deepEqual([...result.positions], [0,0,0,1,0,0,0,1,0,0,0,1,0,1,1,1,0,1]);
  assert.deepEqual([...result.index], [0,1,2,3,4,5]);
  assert.deepEqual([...result.normals], [0,0,1,0,0,1,0,0,1,0,0,-1,0,0,-1,0,0,-1]);
  parts.forEach((p,i)=>assert.deepEqual(p.vertices,before[i]));
  assert.throws(()=>prepareNeuropil([{vertices:parts[0].vertices,indices:new Uint32Array([0,1,9])}]),/outside/);
});

test("soma preparation retains the original coordinate units and float32 palette values", () => {
  const buffer = new ArrayBuffer(26);
  new Float32Array(buffer,0,6).set([1.25,2.5,-3,0.5,1,2]);
  new Uint8Array(buffer,24,2).set([0,255]);
  const before = new Uint8Array(buffer).slice();
  const result = prepareSomata(buffer,[8,16,32],[[0.1,0.2,0.3],[0.7,0.8,0.9]]);
  assert.equal(result.count,2);
  assert.deepEqual(result.positions,new Float32Array([10,40,-96,4,16,64]));
  assert.deepEqual(result.colors,new Float32Array([0.1,0.2,0.3,0.7,0.8,0.9]));
  assert.deepEqual(new Uint8Array(buffer),before);
  assert.throws(()=>prepareSomata(new ArrayBuffer(1),[1,1,1],[[1,1,1]]),/Invalid/);
});
