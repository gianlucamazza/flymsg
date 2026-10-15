// Own native buffers explicitly. COPY_* targets do not change Three.js' VAO or
// ARRAY_BUFFER state. Only public GLBufferAttribute/BufferGeometry APIs are used.
export class GpuUploads {
  constructor(
    gl,
    {
      chunkBytes = 256 * 1024,
      bytesPerTick = 1024 * 1024,
      msPerTick = 2,
      now = () => performance.now(),
    } = {},
  ) {
    if (
      ![chunkBytes, bytesPerTick].every(
        (n) => Number.isInteger(n) && n >= 4 && n % 4 === 0,
      ) ||
      !(msPerTick > 0)
    )
      throw new RangeError("Invalid upload budget");
    Object.assign(this, { gl, chunkBytes, bytesPerTick, msPerTick, now });
    this.records = new Set();
    this.queue = [];
    this.epoch = 0;
    this.lost = false;
    this.error = null;
    this.metrics = {
      uploaded_bytes: 0,
      allocation_ms: 0,
      submission_ms: 0,
      max_call_ms: 0,
      budget_overruns: 0,
      cancellations: 0,
      max_tick_ms: 0,
      ticks: 0,
    };
  }
  enqueue(arrays, { indexSlot = null } = {}) {
    if (
      !arrays.length ||
      arrays.some((a) => !ArrayBuffer.isView(a) || !a.byteLength)
    )
      throw new RangeError("Non-empty typed buffers required");
    if (this.lost || this.error)
      throw new Error(this.error ?? "WebGL context lost");
    const record = {
      indexSlot,
      epoch: this.epoch,
      state: "preparing",
      buffers: [],
      arrays,
      slot: 0,
      offset: 0,
    };
    record.done = new Promise((resolve) => {
      record.settled = resolve;
    });
    this.records.add(record);
    this.queue.push(record);
    return record;
  }
  timed(fn, kind) {
    const start = this.now();
    fn();
    const elapsed = this.now() - start;
    this.metrics[kind] += elapsed;
    this.metrics.max_call_ms = Math.max(this.metrics.max_call_ms, elapsed);
  }
  tick() {
    if (this.lost || this.error || !this.queue.length) return;
    const gl = this.gl,
      start = this.now();
    const previous = gl.getParameter(gl.COPY_WRITE_BUFFER_BINDING);
    let bytes = 0;
    try {
      while (
        this.queue.length &&
        bytes < this.bytesPerTick &&
        this.now() - start < this.msPerTick
      ) {
        const record = this.queue[0];
        const array = record.arrays[record.slot];
        if (!record.buffers[record.slot]) {
          const buffer = gl.createBuffer();
          if (!buffer) throw new Error("GPU buffer allocation failed");
          record.buffers[record.slot] = { buffer, bytes: array.byteLength };
          if (record.slot === record.indexSlot) {
            // Establish WebGL's element-buffer type on our own VAO before
            // COPY_WRITE, without touching the renderer's element binding.
            const vao = gl.getParameter(gl.VERTEX_ARRAY_BINDING);
            this.indexVao ??= gl.createVertexArray();
            if (!this.indexVao) throw new Error("Index VAO allocation failed");
            try {
              gl.bindVertexArray(this.indexVao);
              gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buffer);
              gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, null);
            } finally {
              gl.bindVertexArray(vao);
            }
          }
          gl.bindBuffer(gl.COPY_WRITE_BUFFER, buffer);
          this.timed(
            () =>
              gl.bufferData(
                gl.COPY_WRITE_BUFFER,
                array.byteLength,
                gl.STATIC_DRAW,
              ),
            "allocation_ms",
          );
          // The budget cannot preempt a synchronous driver allocation.
          if (this.now() - start >= this.msPerTick) break;
        }
        gl.bindBuffer(gl.COPY_WRITE_BUFFER, record.buffers[record.slot].buffer);
        const length = Math.min(
          this.chunkBytes,
          this.bytesPerTick - bytes,
          array.byteLength - record.offset,
        );
        if (length) {
          const view = new Uint8Array(
            array.buffer,
            array.byteOffset + record.offset,
            length,
          );
          this.timed(
            () => gl.bufferSubData(gl.COPY_WRITE_BUFFER, record.offset, view),
            "submission_ms",
          );
          record.offset += length;
          bytes += length;
          this.metrics.uploaded_bytes += length;
        }
        if (gl.getError() !== gl.NO_ERROR) throw new Error("GPU upload failed");
        if (record.offset === array.byteLength) {
          record.offset = 0;
          record.slot++;
          if (record.slot === record.arrays.length) {
            record.state = "ready";
            record.settled();
            this.queue.shift();
          }
        }
      }
    } catch (error) {
      this.error = String(error);
      for (const record of this.queue) {
        record.state = "unsupported";
        record.settled();
      }
    } finally {
      gl.bindBuffer(gl.COPY_WRITE_BUFFER, previous);
      const elapsed = this.now() - start;
      this.metrics.ticks++;
      this.metrics.max_tick_ms = Math.max(this.metrics.max_tick_ms, elapsed);
      if (elapsed > this.msPerTick) this.metrics.budget_overruns++;
    }
  }
  release(record) {
    if (!this.records.delete(record)) return;
    if (record.state === "preparing") this.metrics.cancellations++;
    this.queue = this.queue.filter((r) => r !== record);
    if (!this.lost && record.epoch === this.epoch)
      for (const { buffer } of record.buffers) this.gl.deleteBuffer(buffer);
    record.state = "released";
    record.settled();
    record.arrays = [];
    record.buffers = [];
  }
  contextLost() {
    this.lost = true;
    for (const record of [...this.records]) this.release(record);
    this.epoch++;
    this.indexVao = null;
  }
  contextRestored() {
    this.lost = false;
    this.error = null;
  }
  dispose() {
    for (const record of [...this.records]) this.release(record);
    if (!this.lost && this.indexVao) this.gl.deleteVertexArray(this.indexVao);
    this.indexVao = null;
  }
  report() {
    return {
      state: this.lost
        ? "context-lost"
        : this.error
          ? "unsupported"
          : this.queue.length
            ? "preparing"
            : "ready",
      error: this.error,
      epoch: this.epoch,
      pending_pages: this.queue.length,
      owned_gpu_bytes: [...this.records].reduce(
        (sum, r) => sum + r.buffers.reduce((n, b) => n + b.bytes, 0),
        0,
      ),
      staging_cpu_bytes: [...this.records].reduce(
        (sum, r) => sum + r.arrays.reduce((n, a) => n + a.byteLength, 0),
        0,
      ),
      ...this.metrics,
    };
  }
}
