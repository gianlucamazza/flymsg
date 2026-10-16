import assert from "node:assert/strict";
import { test } from "node:test";
import { GpuUploads } from "../../src/flymsg/viz_static/gpu-upload.js";

function fixture({ allocationMs = 0, uploadMs = 0, fail = false } = {}) {
  let clock = 0, binding = { original: true };
  const original = binding, chunks = [], allocations = [], deletions = [];
  const gl = {
    COPY_WRITE_BUFFER_BINDING: 1, COPY_WRITE_BUFFER: 2, STATIC_DRAW: 3, NO_ERROR: 0,
    getParameter: () => binding,
    createBuffer: () => ({ bytes: null }),
    bindBuffer: (target, b) => { assert.equal(target, 2); binding = b; },
    bufferData: (target, bytes) => { assert.equal(target, 2); allocations.push(bytes); binding.bytes = new Uint8Array(bytes); clock += allocationMs; },
    bufferSubData: (target, offset, data) => { assert.equal(target, 2); chunks.push(data.byteLength); binding.bytes.set(data, offset); clock += uploadMs; },
    getError: () => fail ? 1285 : 0,
    deleteBuffer: (buffer) => deletions.push(buffer),
  };
  const queue = new GpuUploads(gl, { chunkBytes: 16, bytesPerTick: 32, msPerTick: 2, now: () => clock });
  return { queue, gl, chunks, allocations, deletions, original, binding: () => binding };
}

test("uploads are bounded, byte-exact, atomically ready and restore GL bindings", () => {
  const f = fixture(), source = Float32Array.from({ length: 43 }, (_, i) => i / 7);
  const record = f.queue.enqueue([source, new Uint32Array([0, 1, 2])]);
  const states = [];
  for (let i = 0; record.state === "preparing" && i < 100; i++) {
    const before = f.queue.report().uploaded_bytes;
    f.queue.tick();
    assert(f.queue.report().uploaded_bytes - before <= 32);
    assert.equal(f.binding(), f.original);
    states.push(record.state);
  }
  assert(states.includes("preparing"));
  assert.equal(record.state, "ready");
  assert(f.chunks.every((n) => n <= 16));
  assert.deepEqual(record.buffers[0].buffer.bytes, new Uint8Array(source.buffer));
  assert.equal(f.queue.report().owned_gpu_bytes, source.byteLength + 12);
  f.queue.release(record);
  f.queue.release(record);
  assert.equal(f.deletions.length, 2);
  assert.equal(f.queue.report().owned_gpu_bytes, 0);
});

test("slow allocations count overruns and defer transfers to the next tick", () => {
  const f = fixture({ allocationMs: 5 });
  const record = f.queue.enqueue([new Float32Array(10)]);
  f.queue.tick();
  assert.equal(record.state, "preparing");
  assert.deepEqual(f.chunks, []);
  assert.equal(f.queue.report().budget_overruns, 1);
  assert.equal(f.queue.report().max_call_ms, 5);
  f.queue.tick();
  assert.equal(f.queue.report().uploaded_bytes, 32);
});

test("index classification preserves the renderer VAO and disposes the private VAO once", () => {
  const f = fixture();
  const originalVao = { renderer: true };
  let vao = originalVao, deletedVaos = 0;
  const get = f.gl.getParameter, bind = f.gl.bindBuffer;
  Object.assign(f.gl, {
    VERTEX_ARRAY_BINDING: 4, ELEMENT_ARRAY_BUFFER: 5,
    getParameter: (key) => key === 4 ? vao : get(key),
    createVertexArray: () => ({ scratch: true }),
    bindVertexArray: (value) => { vao = value; },
    deleteVertexArray: (value) => { assert(value.scratch); deletedVaos++; },
    bindBuffer: (target, buffer) => {
      if (target === 5) {
        assert(vao.scratch);
        if (buffer) buffer.element = true;
      } else bind(target, buffer);
    },
  });
  const record = f.queue.enqueue([new Float32Array(2), new Uint32Array([0, 1])], { indexSlot: 1 });
  f.queue.tick();
  assert.equal(vao, originalVao);
  assert.equal(f.binding(), f.original);
  assert.equal(record.buffers[0].buffer.element, undefined);
  assert.equal(record.buffers[1].buffer.element, true);
  f.queue.dispose();
  f.queue.dispose();
  assert.equal(deletedVaos, 1);
});

test("empty buffers are rejected and an idle queue makes no GL calls", () => {
  const f = fixture();
  assert.throws(() => f.queue.enqueue([]), /Non-empty/);
  assert.throws(() => f.queue.enqueue([new Float32Array(0)]), /Non-empty/);
  f.gl.getParameter = () => { throw new Error("Idle GL call"); };
  f.queue.tick();
});

test("context loss abandons invalid handles; restoration does not double-delete", () => {
  const f = fixture(), old = f.queue.enqueue([new Float32Array(20)]);
  f.queue.tick();
  f.queue.contextLost();
  assert.equal(old.state, "released");
  assert.equal(f.deletions.length, 0);
  assert.equal(f.queue.report().owned_gpu_bytes, 0);
  assert.equal(f.queue.report().state, "context-lost");
  assert.throws(() => f.queue.enqueue([new Float32Array(1)]), /lost/);
  f.queue.contextRestored();
  const next = f.queue.enqueue([new Float32Array(1)]);
  f.queue.tick();
  assert.equal(next.state, "ready");
  f.queue.release(old);
  f.queue.release(next);
  assert.equal(f.deletions.length, 1);
});

test("allocation/upload failure is unsupported, never ready, and remains releasable", () => {
  const f = fixture({ fail: true }), record = f.queue.enqueue([new Float32Array(5)]);
  f.queue.tick();
  assert.equal(record.state, "unsupported");
  assert.equal(f.queue.report().state, "unsupported");
  assert.equal(f.binding(), f.original);
  f.queue.release(record);
  assert.equal(f.queue.report().owned_gpu_bytes, 0);
});

test("a new source generation can recover after failed allocations are released", () => {
  const f = fixture({ fail: true });
  f.queue.enqueue([new Float32Array(5)]);
  f.queue.tick();
  assert.equal(f.queue.report().state, "unsupported");
  f.queue.reset();
  f.gl.getError = () => 0;
  const next = f.queue.enqueue([new Float32Array(5)]);
  f.queue.tick();
  assert.equal(next.state, "ready");
  assert.equal(f.deletions.length, 1);
  f.queue.reset();
  assert.equal(f.deletions.length, 2);
});
