import assert from "node:assert/strict";
import { test } from "node:test";
import { PrimitivePages, pageVisible } from "../../src/flymsg/viz_static/primitive-pages.js";

function originalStream(sources, size) {
  return sources.flatMap((s) => Array.from(s.index ?? { length: s.attributes.position.array.length / 3 }, (_, i) => {
    const vertex = s.index?.[i] ?? i;
    return Object.fromEntries(Object.entries(s.attributes).map(([name, a]) => [name,
      a.array ? Array.from(a.array.subarray(vertex * a.itemSize, (vertex + 1) * a.itemSize)) : [Math.fround(a.constant)]]));
  }));
}

for (const size of [1, 2, 3]) test(`pages retain every original primitive, attribute and order (${size})`, () => {
  const attributes = { position: { itemSize: 3 }, normal: { itemSize: 3 }, aNeuron: { itemSize: 1 } };
  const sources = [0, 1, 2].map((n) => ({
    key: `neuron-${n}`, attributes: {
      position: { itemSize: 3, array: Float32Array.from({ length: 45 }, (_, i) => (i - 20) * (n + 1) / 3) },
      normal: { itemSize: 3, array: Float32Array.from({ length: 45 }, (_, i) => (i % 3) / 7) },
      aNeuron: { itemSize: 1, constant: n },
    }, index: Uint32Array.from({ length: size * 31 }, (_, i) => (i * 7) % 15),
  }));
  const before = sources.map((s) => s.attributes.position.array.slice());
  const builder = new PrimitivePages({ primitiveSize: size, attributes, maxBytes: 512 });
  const pages = sources.flatMap((s) => [...builder.append(s)]);
  const tail = builder.flush();
  if (tail) pages.push(tail);
  assert(pages.length > 1);
  assert.deepEqual(originalStream(pages, size), originalStream(sources, size));
  const counts = new Map();
  for (const page of pages) {
    const bytes = page.index.byteLength + Object.values(page.attributes).reduce((n, a) => n + a.array.byteLength, 0);
    assert(bytes <= 512);
    assert.equal(page.index.length % size, 0);
    for (const { source, first, count } of page.spans) {
      assert.equal(first, counts.get(source) ?? 0);
      counts.set(source, first + count);
    }
    for (let i = 0; i < page.attributes.position.array.length; i++) {
      const x = page.attributes.position.array[i], axis = i % 3;
      assert(x >= page.bounds.min[axis] && x <= page.bounds.max[axis]);
    }
  }
  assert.deepEqual([...counts.values()], [31, 31, 31]);
  sources.forEach((s, i) => assert.deepEqual(s.attributes.position.array, before[i]));
});

test("non-indexed contextual points keep their colours", () => {
  const source = { key: "somata", attributes: {
    position: { itemSize: 3, array: new Float32Array([0, 0, 0, 1, 1, 1]) },
    color: { itemSize: 3, array: new Float32Array([1, 0, 0, 0, 1, 0]) },
  } };
  const builder = new PrimitivePages({ primitiveSize: 1, attributes: source.attributes, maxBytes: 32 });
  const pages = [...builder.append(source), builder.flush()].filter(Boolean);
  assert.deepEqual(originalStream(pages, 1), originalStream([source], 1));
});

test("invalid sources fail explicitly; incomplete triangles and foreign indices never publish", () => {
  const attributes = { position: { itemSize: 3, array: new Float32Array(9) } };
  const make = () => new PrimitivePages({ primitiveSize: 3, attributes });
  assert.throws(() => [...make().append({ key: "bad", attributes, index: new Uint32Array([0, 1]) })], /Incomplete/);
  assert.throws(() => [...make().append({ key: "bad", attributes, index: new Uint32Array([0, 1, 9]) })], /outside/);
});

test("culling keeps long edges, near-plane intersections and either-eye visibility", () => {
  const left = [[1, 0, 0, 2], [-1, 0, 0, -1], [0, 1, 0, 1], [0, -1, 0, 1], [0, 0, 1, 1], [0, 0, -1, 1]];
  const right = [[1, 0, 0, -1], [-1, 0, 0, 2], ...left.slice(2)];
  const box = (min, max) => ({ min, max });
  assert(pageVisible(box([1.5, 0, 0], [1.7, 0, 0]), [left, right]));
  assert(pageVisible(box([-3, 0, 0], [3, 0, 0]), [left, right]));
  assert(pageVisible(box([-1.5, 0, -2], [-1.5, 0, 0]), [left, right]));
  assert(!pageVisible(box([10, 0, 0], [11, 0, 0]), [left, right]));
  assert(pageVisible(box([10, 0, 0], [11, 0, 0]), null));
});
