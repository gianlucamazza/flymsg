import assert from "node:assert/strict";
import { test } from "node:test";
import { createHash } from "node:crypto";
import { BufferGeometry, BufferAttribute, LineSegments, LineBasicMaterial } from "../../src/flymsg/viz_static/vendor/three/build/three.module.min.js";
import { geometryInventory } from "../../src/flymsg/viz_static/render-reference.js";

test("reference snapshots original typed data before asynchronous hashing", async () => {
  const positions = new Float32Array([0, 1, 2, 3, 4, 5]);
  const indices = new Uint32Array([0, 1]);
  const expected = createHash("sha256").update(Buffer.from(positions.buffer)).digest("hex");
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(positions, 3));
  geometry.setIndex(new BufferAttribute(indices, 1));
  const object = new LineSegments(geometry, new LineBasicMaterial());
  object.name = "original-edges";
  const pending = geometryInventory([object]);
  positions.fill(999);
  indices.fill(0);
  const [reference] = await pending;
  assert.equal(reference.attrs.position.sha256, expected);
  assert.equal(reference.attrs.position.byteLength, 24);
  assert.equal(reference.index.sha256, createHash("sha256").update(Buffer.from(new Uint32Array([0, 1]).buffer)).digest("hex"));
});
