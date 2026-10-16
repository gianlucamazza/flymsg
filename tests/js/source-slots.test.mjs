import assert from "node:assert/strict";
import { test } from "node:test";
import * as T from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { SourceSlots } from "../../src/flymsg/viz_static/source-slots.js";

test("fragment slot and hole reuse matches the pinned renderer's independent public API", () => {
  const slots = new SourceSlots(64);
  const mesh = new T.BatchedMesh(64, 3, 3, new T.MeshBasicMaterial());
  const geometry = new T.BufferGeometry();
  geometry.setAttribute("position", new T.BufferAttribute(new Float32Array(9), 3));
  geometry.setIndex(new T.BufferAttribute(new Uint32Array([0, 1, 2]), 1));
  const gid = mesh.addGeometry(geometry);
  const active = [];
  for (let cycle = 0; cycle < 20; cycle++) {
    for (let i = 0; i < 20; i++) {
      const id = slots.allocate();
      assert.equal(id, mesh.addInstance(gid));
      active.push(id);
    }
    for (let i = active.length - 1; i >= 0; i -= 2) {
      const [id] = active.splice(i, 1);
      slots.release(id);
      mesh.deleteInstance(id);
    }
  }
  mesh.dispose(); geometry.dispose(); mesh.material.dispose();
});

test("capacity, double release and reset are explicit", () => {
  const slots = new SourceSlots(2);
  slots.allocate(); slots.allocate();
  assert.throws(() => slots.allocate(), /capacity/);
  slots.release(0);
  assert.throws(() => slots.release(0), /released/);
  assert.equal(slots.allocate(), 0);
  slots.reset();
  assert.equal(slots.allocate(), 0);
});
