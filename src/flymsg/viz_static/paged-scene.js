import { BoundedSelections } from "./bounded-selections.js";
import { GpuUploads } from "./gpu-upload.js";
import { pageVisible } from "./primitive-pages.js";

const pause = () => new Promise((resolve) => setTimeout(resolve, 0));
const cancelled = () =>
  new DOMException("Superseded geometry generation", "AbortError");

function sameSources(a, b) {
  return (
    a.length === b.length &&
    a.every((s, i) => {
      const t = b[i];
      return (
        s.key === t.key &&
        s.layer === t.layer &&
        s.index === t.index &&
        Object.keys(s.attributes).length === Object.keys(t.attributes).length &&
        Object.entries(s.attributes).every(([name, attr]) => {
          const other = t.attributes[name];
          return (
            other &&
            attr.array === other.array &&
            attr.constant === other.constant &&
            attr.itemSize === other.itemSize
          );
        })
      );
    })
  );
}

// An opt-in candidate within the existing renderer. CPU originals remain the
// oracle; neither their arrays nor the reference renderer's attributes are detached.
export class PagedScene {
  constructor(
    THREE,
    renderer,
    parent,
    { maxPageBytes = 4 * 1024 * 1024, bounded = false } = {},
  ) {
    Object.assign(this, { THREE, renderer, parent, maxPageBytes });
    this.uploads = new GpuUploads(renderer.getContext());
    this.boundedEnabled = bounded;
    if (bounded) {
      const gl = renderer.getContext();
      this.bounded = new BoundedSelections(
        THREE,
        this.uploads,
        (pages) => this.request({ kind: "bounded-compose", pages }),
        {
          float:
            gl.getShaderPrecisionFormat(gl.VERTEX_SHADER, gl.HIGH_FLOAT)
              ?.precision ?? 0,
          subpixel: gl.getParameter(gl.SUBPIXEL_BITS),
        },
      );
    }
    this.group = new THREE.Group();
    this.group.visible = false;
    parent.add(this.group);
    this.sources = [];
    this.pages = [];
    this.generation = 0;
    this.state = "preparing";
    this.complete = false;
    this.error = null;
    this.admissionError = null;
    this.waiters = new Map();
    this.requestId = 0;
    this.cpuMaxCallMs = 0;
    this.cpuBudgetOverruns = 0;
    this.preparedBytes = this.inputCopyBytes = this.workerInputBytes = 0;
  }
  request(message, transfers = []) {
    return new Promise((resolve, reject) => {
      const id = ++this.requestId;
      const timer = setTimeout(
        () => {
          this.waiters.delete(id);
          reject(
            new Error("Geometry worker timed out; no completed generation"),
          );
        },
        this.boundedEnabled ? 120000 : 30000,
      );
      this.waiters.set(id, {
        resolve: (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
      });
      this.worker.postMessage({ ...message, id }, transfers);
    });
  }
  current(generation) {
    if (generation !== this.generation || this.uploads.lost) throw cancelled();
  }
  async copyArray(array, generation) {
    this.current(generation);
    const started = performance.now();
    const copy = new array.constructor(array.length);
    this.inputCopyBytes += copy.byteLength;
    this.cpuDuration(performance.now() - started);
    let sliceStart = performance.now();
    const step = (256 * 1024) / array.BYTES_PER_ELEMENT;
    for (let offset = 0; offset < array.length; offset += step) {
      this.current(generation);
      const begin = performance.now();
      copy.set(
        array.subarray(offset, Math.min(offset + step, array.length)),
        offset,
      );
      this.cpuDuration(performance.now() - begin);
      if (performance.now() - sliceStart >= 2) {
        await pause();
        sliceStart = performance.now();
      }
    }
    return copy;
  }
  cpuDuration(ms) {
    this.cpuMaxCallMs = Math.max(this.cpuMaxCallMs, ms);
    if (ms > 2) this.cpuBudgetOverruns++;
  }
  async consume(page, layer, generation) {
    this.current(generation);
    if (!page) return;
    const names = Object.keys(page.attributes);
    const arrays = [
      ...names.map((name) => page.attributes[name].array),
      page.index,
    ];
    const record = this.uploads.enqueue(arrays, {
      indexSlot: arrays.length - 1,
    });
    this.preparedBytes += arrays.reduce((n, a) => n + a.byteLength, 0);
    // Backpressure: at most one completed worker page waits for GPU upload.
    await record.done;
    this.current(generation);
    if (record.state !== "ready")
      throw new Error(this.uploads.error ?? "Page upload failed");
    const begin = performance.now();
    const T = this.THREE,
      geometry = new T.BufferGeometry();
    names.forEach((name, i) => {
      const a = page.attributes[name];
      geometry.setAttribute(
        name,
        new T.GLBufferAttribute(
          record.buffers[i].buffer,
          this.uploads.gl.FLOAT,
          a.itemSize,
          4,
          a.array.length / a.itemSize,
        ),
      );
    });
    geometry.setIndex(
      new T.GLBufferAttribute(
        record.buffers.at(-1).buffer,
        this.uploads.gl.UNSIGNED_INT,
        1,
        4,
        page.index.length,
      ),
    );
    geometry.boundingBox = new T.Box3(
      new T.Vector3(...page.bounds.min),
      new T.Vector3(...page.bounds.max),
    );
    // One anatomical reference object draws source-order primitives. All its
    // pages need the same depth-sort key, including picking/depth passes.
    // Transparent context retains its original object's centre instead.
    // These are valid conservative public geometry bounds; culling uses boxes.
    const centre = layer.sortCenter ?? [0, 0, 0];
    const radius = Math.sqrt(
      centre.reduce(
        (sum, c, axis) =>
          sum +
          Math.max(
            Math.abs(page.bounds.min[axis] - c),
            Math.abs(page.bounds.max[axis] - c),
          ) **
            2,
        0,
      ),
    );
    geometry.boundingSphere = new T.Sphere(new T.Vector3(...centre), radius);
    const ObjectType =
      layer.primitiveSize === 2
        ? T.LineSegments
        : layer.primitiveSize === 1
          ? T.Points
          : T.Mesh;
    const object = new ObjectType(geometry, layer.material);
    object.frustumCulled = false; // union-of-eye culling is explicit below
    object.renderOrder = layer.renderOrder ?? 0;
    this.group.add(object);
    const published = {
      object,
      record,
      bounds: page.bounds,
      spans: page.spans,
      layer,
      names,
      counts: arrays.map((a) => a.length),
      boundedSource: page.boundedSource,
    };
    this.pages.push(published);
    if (page.bounded) this.bounded.add(published, page.bounded);
    // Release packing arrays after upload. Retain source originals and provenance.
    record.arrays = [];
    this.cpuDuration(performance.now() - begin);
  }
  async build(sources, generation) {
    this.worker = new Worker(new URL("./page-worker.js", import.meta.url), {
      type: "module",
    });
    this.worker.onmessage = ({ data }) => {
      if (generation !== this.generation) return;
      const pending = this.waiters.get(data.id);
      this.waiters.delete(data.id);
      if (data.error) pending?.reject(new Error(data.error));
      else pending?.resolve(data);
    };
    this.worker.onerror = (event) => {
      if (generation !== this.generation) return;
      for (const waiter of this.waiters.values())
        waiter.reject(new Error(event.message));
      this.waiters.clear();
    };
    let layer = null;
    for (const source of sources) {
      this.current(generation);
      if (layer !== source.layer) {
        if (layer)
          await this.consume(
            (await this.request({ kind: "finish" })).page,
            layer,
            generation,
          );
        layer = source.layer;
        this.current(generation);
        await this.request({
          kind: "start",
          options: {
            primitiveSize: layer.primitiveSize,
            attributes: Object.fromEntries(
              Object.entries(source.attributes).map(([name, a]) => [
                name,
                { itemSize: a.itemSize },
              ]),
            ),
            maxBytes: this.maxPageBytes,
            preserveAnchors:
              this.boundedEnabled &&
              layer.primitiveSize === 2 &&
              !layer.context,
          },
        });
      }
      const attributes = {},
        transfers = [];
      for (const [name, a] of Object.entries(source.attributes)) {
        attributes[name] = a.array
          ? { ...a, array: await this.copyArray(a.array, generation) }
          : a;
        if (a.array) transfers.push(attributes[name].array.buffer);
      }
      const index = source.index
        ? await this.copyArray(source.index, generation)
        : null;
      if (index) transfers.push(index.buffer);
      this.current(generation);
      this.workerInputBytes = transfers.reduce((n, b) => n + b.byteLength, 0);
      const response = this.request(
        {
          kind: "source",
          context: !!layer.context,
          source: { key: source.key, attributes, index },
        },
        transfers,
      );
      this.inputCopyBytes = 0; // transferred to worker, originals remain intact
      let result = await response;
      if (layer.context) layer.sortCenter = result.sortCenter;
      while (true) {
        await this.consume(result.page, layer, generation);
        this.current(generation);
        if (!result.pending) break;
        result = await this.request({ kind: "next" });
      }
      this.workerInputBytes = 0;
    }
    if (layer)
      await this.consume(
        (await this.request({ kind: "finish" })).page,
        layer,
        generation,
      );
    this.current(generation);
    if (!this.boundedEnabled) {
      this.worker.terminate();
      this.worker = null;
    }
    this.state = "warming"; // first full-quality draw must complete before XR admission
  }
  sync(sources, complete, admissionError = null) {
    if (
      sameSources(sources, this.sources) &&
      complete === this.complete &&
      admissionError === this.admissionError
    )
      return;
    this.reset();
    this.sources = sources;
    this.complete = complete;
    this.admissionError = admissionError;
    if (admissionError) {
      this.state = "unsupported";
      this.error = admissionError;
      return;
    }
    if (!complete || this.uploads.lost) return;
    const generation = this.generation;
    this.build(sources, generation).catch((error) => {
      if (generation !== this.generation) return;
      this.reset();
      this.complete = true; // latch this failed source set; no automatic retry loop
      this.state = "unsupported";
      this.error = String(error);
    });
  }
  reset() {
    this.preparedBytes = this.inputCopyBytes = this.workerInputBytes = 0;
    if (this.warmFence && !this.uploads.lost)
      this.uploads.gl.deleteSync(this.warmFence);
    this.warmFence = null;
    this.generation++;
    this.worker?.terminate();
    this.worker = null;
    for (const waiter of this.waiters.values()) waiter.reject(cancelled());
    this.waiters.clear();
    this.group.clear();
    for (const { object } of this.pages) {
      // Dispose VAOs with native attributes detached. WebGLAttributes.remove
      // would otherwise delete buffers owned by GpuUploads a second time.
      for (const name of Object.keys(object.geometry.attributes))
        object.geometry.deleteAttribute(name);
      object.geometry.setIndex(null);
      object.geometry.dispose();
    }
    this.bounded?.reset();
    this.pages = [];
    this.uploads.reset();
    this.state = "preparing";
    this.error = null;
    this.complete = false;
  }
  tick() {
    this.uploads.tick();
    if (this.state !== "warming" || !this.warmFence) return;
    const gl = this.uploads.gl;
    const result = gl.clientWaitSync(this.warmFence, 0, 0);
    if (result === gl.ALREADY_SIGNALED || result === gl.CONDITION_SATISFIED) {
      gl.deleteSync(this.warmFence);
      this.warmFence = null;
      this.state = "ready";
    } else if (result === gl.WAIT_FAILED) {
      this.reset();
      this.complete = true;
      this.state = "unsupported";
      this.error = "GPU preparation fence failed";
    }
  }
  contextLost() {
    this.uploads.contextLost();
    this.reset();
    this.sources = [];
    this.state = "context-lost";
  }
  contextRestored() {
    this.uploads.contextRestored();
    this.sources = [];
  }
  dispose() {
    this.reset();
    this.uploads.dispose();
    this.parent.remove(this.group);
  }
  render(
    originals,
    callback,
    { eyes = null, pass = "colour", boundedEyes = null } = {},
  ) {
    const shaderError = this.renderer.debug.onShaderError;
    if (this.state === "warming")
      this.renderer.debug.onShaderError = () => {
        throw new Error("Page shader compilation failed");
      };
    const saved = originals.map((o) => [o, o.visible]);
    originals.forEach((o) => {
      o.visible = false;
    });
    this.group.visible =
      ["warming", "ready"].includes(this.state) && this.complete;
    for (const page of this.pages) {
      page.object.visible =
        (this.state === "warming" || pageVisible(page.bounds, eyes)) &&
        (pass === "colour" || !page.layer.context);
      page.object.material = page.layer[pass] ?? page.layer.material;
    }
    try {
      if (this.bounded && pass === "colour") this.bounded.apply(boundedEyes);
      const result = callback();
      if (this.state === "warming" && pass === "colour" && !this.warmFence) {
        const gl = this.uploads.gl;
        this.warmFence = gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0);
        if (!this.warmFence)
          throw new Error("GPU preparation fence allocation failed");
        gl.flush();
      }
      return result;
    } catch (error) {
      this.reset();
      this.complete = true;
      this.state = "unsupported";
      this.error = String(error);
      throw error;
    } finally {
      this.bounded?.restore();
      this.renderer.debug.onShaderError = shaderError;
      this.group.visible = false;
      saved.forEach(([o, visible]) => {
        o.visible = visible;
      });
      for (const page of this.pages) page.object.material = page.layer.material;
    }
  }
  async inventory(digest) {
    if (this.state !== "ready")
      throw new Error("GPU inventory requires ready resources");
    const generation = this.generation,
      gl = this.uploads.gl,
      result = [];
    for (const page of this.pages) {
      const buffers = [];
      for (let i = 0; i < page.record.buffers.length; i++) {
        this.current(generation);
        const { buffer, bytes } = page.record.buffers[i];
        const data = new Uint8Array(bytes);
        const previous = gl.getParameter(gl.COPY_READ_BUFFER_BINDING);
        try {
          gl.bindBuffer(gl.COPY_READ_BUFFER, buffer);
          gl.getBufferSubData(gl.COPY_READ_BUFFER, 0, data);
        } finally {
          gl.bindBuffer(gl.COPY_READ_BUFFER, previous);
        }
        buffers.push({
          name: page.names[i] ?? "index",
          bytes,
          sha256: await digest(data),
        });
        await pause();
      }
      result.push({
        spans: page.spans,
        bounds: page.bounds,
        buffers,
        bounded: page.bounded,
        bounded_source: page.boundedSource
          ? {
              anchors_sha256: await digest(page.boundedSource.anchors),
              origins_sha256: await digest(page.boundedSource.origins),
              cpu_bytes:
                page.boundedSource.anchors.byteLength +
                page.boundedSource.origins.byteLength,
            }
          : undefined,
      });
    }
    this.current(generation);
    return result;
  }
  async prepareBounded(eyes) {
    if (!this.bounded) return null;
    const generation = this.generation,
      deadline = performance.now() + 120000;
    do {
      this.current(generation);
      this.tick();
      this.bounded.update(eyes);
      if (this.bounded.error) throw Error(this.bounded.error);
      if (this.bounded.settled()) return this.bounded.report();
      if (performance.now() > deadline)
        throw Error("Bounded preparation timed out");
      await new Promise((resolve) => setTimeout(resolve, 16));
    } while (true);
  }
  report() {
    return {
      ...this.uploads.report(),
      state: this.state,
      complete: this.complete,
      generation: this.generation,
      pages: this.pages.length,
      max_page_bytes: this.maxPageBytes,
      bounded: this.bounded?.report() ?? null,
      prepared_bytes: this.preparedBytes,
      input_copy_cpu_bytes: this.inputCopyBytes,
      worker_input_bytes: this.workerInputBytes,
      cpu_max_call_ms: this.cpuMaxCallMs,
      cpu_budget_overruns: this.cpuBudgetOverruns,
      error: this.error ?? this.uploads.error,
    };
  }
}
