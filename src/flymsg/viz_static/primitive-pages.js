// Lossless, source-order packing. Run in a worker; normals are supplied by the
// original fragment finisher, never recomputed at a page boundary.
export class PrimitivePages {
  constructor({ primitiveSize, attributes, maxBytes = 4 * 1024 * 1024 }) {
    if (
      attributes.position?.itemSize !== 3 ||
      !Number.isInteger(maxBytes) ||
      maxBytes < 1
    )
      throw new RangeError(
        "Float32 xyz positions and a positive page budget required",
      );
    if (![1, 2, 3].includes(primitiveSize))
      throw new RangeError("Invalid primitive size");
    this.primitiveSize = primitiveSize;
    this.schema = attributes;
    const stride = Object.values(attributes).reduce(
      (n, a) => n + a.itemSize * 4,
      0,
    );
    this.capacity =
      Math.floor(maxBytes / (stride + 4) / primitiveSize) * primitiveSize;
    if (this.capacity < primitiveSize)
      throw new RangeError("Page cannot hold one primitive");
    this.maxBytes = maxBytes;
    this.reset();
  }
  reset() {
    this.attributes = Object.fromEntries(
      Object.entries(this.schema).map(([name, a]) => [
        name,
        {
          itemSize: a.itemSize,
          array: new Float32Array(this.capacity * a.itemSize),
        },
      ]),
    );
    this.index = new Uint32Array(this.capacity);
    this.vertices = this.indices = 0;
    this.spans = [];
    this.bounds = {
      min: [Infinity, Infinity, Infinity],
      max: [-Infinity, -Infinity, -Infinity],
    };
  }
  flush() {
    if (!this.indices) return null;
    const page = {
      attributes: Object.fromEntries(
        Object.entries(this.attributes).map(([name, a]) => [
          name,
          {
            itemSize: a.itemSize,
            array: a.array.slice(0, this.vertices * a.itemSize),
          },
        ]),
      ),
      index: this.index.slice(0, this.indices),
      bounds: this.bounds,
      spans: this.spans,
    };
    this.reset();
    return page;
  }
  *append(source) {
    const position = source.attributes.position;
    const count = position.array.length / position.itemSize;
    const indices = source.index;
    const length = indices?.length ?? count;
    if (!Number.isInteger(count) || length % this.primitiveSize)
      throw new RangeError("Incomplete primitive");
    for (const [name, spec] of Object.entries(this.schema)) {
      const a = source.attributes[name];
      if (
        !a ||
        a.itemSize !== spec.itemSize ||
        (a.array &&
          (!(a.array instanceof Float32Array) ||
            a.array.length !== count * a.itemSize)) ||
        (!a.array && (!Number.isFinite(a.constant) || a.itemSize !== 1))
      )
        throw new TypeError(`Incompatible attribute ${name}`);
    }
    let remap = new Map();
    for (let offset = 0; offset < length; offset += this.primitiveSize) {
      // Reserve a worst-case primitive before touching the current page. This
      // bounds both vertex and index storage, including cross-page endpoints.
      if (
        this.indices + this.primitiveSize > this.capacity ||
        this.vertices + this.primitiveSize > this.capacity
      ) {
        yield this.flush();
        remap = new Map();
      }
      let span = this.spans.at(-1);
      if (!span || span.source !== source.key) {
        span = {
          source: source.key,
          first: offset / this.primitiveSize,
          count: 0,
        };
        this.spans.push(span);
      }
      span.count++;
      for (let j = 0; j < this.primitiveSize; j++) {
        const original = indices ? indices[offset + j] : offset + j;
        if (!Number.isInteger(original) || original < 0 || original >= count)
          throw new RangeError("Vertex index outside source");
        let vertex = remap.get(original);
        if (vertex === undefined) {
          vertex = this.vertices++;
          remap.set(original, vertex);
          for (const [name, a] of Object.entries(this.attributes)) {
            const input = source.attributes[name];
            if (input.array)
              a.array.set(
                input.array.subarray(
                  original * a.itemSize,
                  (original + 1) * a.itemSize,
                ),
                vertex * a.itemSize,
              );
            else a.array[vertex] = input.constant;
          }
          for (let axis = 0; axis < 3; axis++) {
            const value = position.array[original * 3 + axis];
            if (!Number.isFinite(value))
              throw new RangeError("Non-finite position");
            this.bounds.min[axis] = Math.min(this.bounds.min[axis], value);
            this.bounds.max[axis] = Math.max(this.bounds.max[axis], value);
          }
        }
        this.index[this.indices++] = vertex;
      }
    }
  }
}

export function pageTransfers(page) {
  return [
    page.index.buffer,
    ...Object.values(page.attributes).map((a) => a.array.buffer),
  ];
}

// A box rejected by every eye is safe to omit, including long segments and
// near-plane intersections. Planes and bounds are in the same local space.
export function pageVisible(bounds, eyes) {
  return (
    !eyes ||
    eyes.some((planes) =>
      planes.every(([x, y, z, w]) => {
        // GPU matrix arithmetic is float32. Expand eligibility near a plane;
        // this can submit extra geometry, never simplify the source.
        const roundoff =
          32 *
          2 ** -23 *
          (Math.abs(x) *
            Math.max(Math.abs(bounds.min[0]), Math.abs(bounds.max[0])) +
            Math.abs(y) *
              Math.max(Math.abs(bounds.min[1]), Math.abs(bounds.max[1])) +
            Math.abs(z) *
              Math.max(Math.abs(bounds.min[2]), Math.abs(bounds.max[2])) +
            Math.abs(w) +
            1);
        return (
          x * bounds[x >= 0 ? "max" : "min"][0] +
            y * bounds[y >= 0 ? "max" : "min"][1] +
            z * bounds[z >= 0 ? "max" : "min"][2] +
            w >=
          -roundoff
        );
      }),
    )
  );
}
