// Readers for the neuroglancer precomputed formats used by the MaleCNS volumes, fetched
// straight from Google Cloud Storage. Pure functions (plus fetch), so they run in node tests.
//
// Formats: https://github.com/google/neuroglancer/tree/master/src/datasource/precomputed
// (sharded.md, meshes.md, skeletons.md).

export const BUCKET = "flyem-male-cns";
// The JSON API serves public objects with CORS and HTTP Range; storage.googleapis.com does not.
const API = `https://www.googleapis.com/storage/v1/b/${BUCKET}/o/`;

export const objectUrl = (path) =>
  `${API}${encodeURIComponent(path)}?alt=media`;

export async function fetchBytes(path, start, end, fetchImpl = fetch) {
  // [start, end) byte range; the whole object when start is undefined
  const headers =
    start === undefined ? {} : { Range: `bytes=${start}-${end - 1}` };
  const r = await fetchImpl(objectUrl(path), { headers });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  const buf = await r.arrayBuffer();
  if (start !== undefined && buf.byteLength !== end - start) {
    throw new Error(
      `${path}: got ${buf.byteLength} bytes, asked ${end - start}`,
    );
  }
  return buf;
}

export async function fetchJson(path, fetchImpl = fetch) {
  const buf = await fetchBytes(path, undefined, undefined, fetchImpl);
  return buf && JSON.parse(new TextDecoder().decode(buf));
}

export async function gunzip(buf) {
  const stream = new Blob([buf])
    .stream()
    .pipeThrough(new DecompressionStream("gzip"));
  return new Response(stream).arrayBuffer();
}

const decode = (buf, encoding) => (encoding === "gzip" ? gunzip(buf) : buf);

// ---------- murmurhash3_x86_128 ----------

const rotl = (x, r) => (x << r) | (x >>> (32 - r));
const fmix = (h) => {
  h ^= h >>> 16;
  h = Math.imul(h, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  return h ^ (h >>> 16);
};

/** Low 64 bits (the first 8 digest bytes, little-endian) of MurmurHash3_x86_128, as BigInt. */
export function murmur3x86_128Low64(bytes, seed = 0) {
  const c1 = 0x239b961b,
    c2 = 0xab0e9789,
    c3 = 0x38b34ae5,
    c4 = 0xa1e38b93;
  let h1 = seed,
    h2 = seed,
    h3 = seed,
    h4 = seed;
  const n = bytes.length;
  const view = new DataView(bytes.buffer, bytes.byteOffset, n);
  const blocks = n - (n % 16);
  for (let i = 0; i < blocks; i += 16) {
    let k1 = view.getUint32(i, true),
      k2 = view.getUint32(i + 4, true);
    let k3 = view.getUint32(i + 8, true),
      k4 = view.getUint32(i + 12, true);
    k1 = Math.imul(rotl(Math.imul(k1, c1), 15), c2);
    h1 ^= k1;
    h1 = (Math.imul(rotl(h1, 19) + h2, 5) + 0x561ccd1b) | 0;
    k2 = Math.imul(rotl(Math.imul(k2, c2), 16), c3);
    h2 ^= k2;
    h2 = (Math.imul(rotl(h2, 17) + h3, 5) + 0x0bcaa747) | 0;
    k3 = Math.imul(rotl(Math.imul(k3, c3), 17), c4);
    h3 ^= k3;
    h3 = (Math.imul(rotl(h3, 15) + h4, 5) + 0x96cd1c35) | 0;
    k4 = Math.imul(rotl(Math.imul(k4, c4), 18), c1);
    h4 ^= k4;
    h4 = (Math.imul(rotl(h4, 13) + h1, 5) + 0x32ac3b17) | 0;
  }
  const tail = (from, count) => {
    let k = 0;
    for (let j = count - 1; j >= 0; j--)
      k = (k << 8) | bytes[blocks + from + j];
    return k;
  };
  const rest = n % 16;
  if (rest > 12)
    h4 ^= Math.imul(rotl(Math.imul(tail(12, rest - 12), c4), 18), c1);
  if (rest > 8)
    h3 ^= Math.imul(
      rotl(Math.imul(tail(8, Math.min(rest - 8, 4)), c3), 17),
      c4,
    );
  if (rest > 4)
    h2 ^= Math.imul(
      rotl(Math.imul(tail(4, Math.min(rest - 4, 4)), c2), 16),
      c3,
    );
  if (rest > 0)
    h1 ^= Math.imul(rotl(Math.imul(tail(0, Math.min(rest, 4)), c1), 15), c2);
  h1 ^= n;
  h2 ^= n;
  h3 ^= n;
  h4 ^= n;
  h1 = (h1 + h2 + h3 + h4) | 0;
  h2 = (h2 + h1) | 0;
  h3 = (h3 + h1) | 0;
  h4 = (h4 + h1) | 0;
  h1 = fmix(h1);
  h2 = fmix(h2);
  h3 = fmix(h3);
  h4 = fmix(h4);
  h1 = (h1 + h2 + h3 + h4) | 0;
  h2 = (h2 + h1) | 0;
  return BigInt(h1 >>> 0) | (BigInt(h2 >>> 0) << 32n);
}

// ---------- sharded format ----------

/** Shard file name and minishard of a uint64 key (BigInt). */
export function shardLocation(key, sharding) {
  const hashed = key >> BigInt(sharding.preshift_bits);
  let h;
  if (sharding.hash === "identity") h = hashed;
  else if (sharding.hash === "murmurhash3_x86_128") {
    const b = new Uint8Array(8);
    new DataView(b.buffer).setBigUint64(0, hashed, true);
    h = murmur3x86_128Low64(b);
  } else throw new Error(`unsupported shard hash ${sharding.hash}`);
  const minishard = Number(h & ((1n << BigInt(sharding.minishard_bits)) - 1n));
  const shard = Number(
    (h >> BigInt(sharding.minishard_bits)) &
      ((1n << BigInt(sharding.shard_bits)) - 1n),
  );
  const digits = Math.ceil(sharding.shard_bits / 4);
  return {
    shard,
    minishard,
    file: `${shard.toString(16).padStart(digits, "0")}.shard`,
  };
}

/** Decoded minishard index -> {keys: BigInt[], start: number[], size: number[]} (absolute). */
export function parseMinishardIndex(buf, shardIndexBytes) {
  const v = new DataView(buf);
  const n = buf.byteLength / 24;
  const keys = [],
    start = [],
    size = [];
  let key = 0n,
    end = shardIndexBytes;
  for (let i = 0; i < n; i++) {
    key += v.getBigUint64(8 * i, true);
    const s = end + Number(v.getBigUint64(8 * (n + i), true));
    const len = Number(v.getBigUint64(8 * (2 * n + i), true));
    keys.push(key);
    start.push(s);
    size.push(len);
    end = s + len;
  }
  return { keys, start, size };
}

/** Reads sharded chunks of one volume, caching minishard indices. */
export class ShardedReader {
  constructor(dir, sharding, fetchImpl = fetch) {
    this.dir = dir;
    this.sharding = sharding;
    this.fetch = fetchImpl;
    this.indexBytes = 16 * 2 ** sharding.minishard_bits;
    this.minishards = new Map();
  }

  async minishard(loc) {
    const k = `${loc.file}/${loc.minishard}`;
    if (!this.minishards.has(k)) {
      this.minishards.set(
        k,
        (async () => {
          const path = `${this.dir}/${loc.file}`;
          const entry = new DataView(
            await fetchBytes(
              path,
              16 * loc.minishard,
              16 * loc.minishard + 16,
              this.fetch,
            ),
          );
          const s0 = Number(entry.getBigUint64(0, true)),
            s1 = Number(entry.getBigUint64(8, true));
          if (s0 === s1) return { keys: [], start: [], size: [] };
          const raw = await fetchBytes(
            path,
            this.indexBytes + s0,
            this.indexBytes + s1,
            this.fetch,
          );
          return parseMinishardIndex(
            await decode(raw, this.sharding.minishard_index_encoding),
            this.indexBytes,
          );
        })(),
      );
    }
    return this.minishards.get(k);
  }

  /** {path, start, size} of the chunk stored under `key`, or null. */
  async locate(key) {
    const loc = shardLocation(key, this.sharding);
    const mi = await this.minishard(loc);
    const i = mi.keys.indexOf(key);
    return i < 0
      ? null
      : {
          path: `${this.dir}/${loc.file}`,
          start: mi.start[i],
          size: mi.size[i],
        };
  }

  async read(key) {
    const at = await this.locate(key);
    if (!at) return null;
    const raw = await fetchBytes(
      at.path,
      at.start,
      at.start + at.size,
      this.fetch,
    );
    return { ...at, data: await decode(raw, this.sharding.data_encoding) };
  }
}

// ---------- multi-resolution (multilod draco) meshes ----------

/** Parse a multilod manifest; fragment byte ranges precede the manifest at `manifestStart`. */
export function parseMultilodManifest(buf, manifestStart) {
  const v = new DataView(buf);
  let o = 0;
  const f32 = (count) => {
    const a = Array.from({ length: count }, (_, i) =>
      v.getFloat32(o + 4 * i, true),
    );
    o += 4 * count;
    return a;
  };
  const u32 = (count) => {
    const a = Array.from({ length: count }, (_, i) =>
      v.getUint32(o + 4 * i, true),
    );
    o += 4 * count;
    return a;
  };
  const chunkShape = f32(3),
    gridOrigin = f32(3);
  const [numLods] = u32(1);
  const lodScales = f32(numLods);
  const vertexOffsets = Array.from({ length: numLods }, () => f32(3));
  const counts = u32(numLods);
  const lods = [];
  for (let l = 0; l < numLods; l++) {
    const n = counts[l];
    const xs = u32(n),
      ys = u32(n),
      zs = u32(n),
      sizes = u32(n);
    lods.push(xs.map((x, i) => ({ pos: [x, ys[i], zs[i]], size: sizes[i] })));
  }
  if (o !== buf.byteLength)
    throw new Error(`manifest: parsed ${o} of ${buf.byteLength} bytes`);
  // fragments are stored right before the manifest, LOD by LOD in manifest order
  let at = manifestStart - lods.flat().reduce((s, f) => s + f.size, 0);
  for (const lod of lods)
    for (const f of lod) {
      f.start = at;
      at += f.size;
    }
  return { chunkShape, gridOrigin, lodScales, vertexOffsets, lods };
}

/** Group [start, end) ranges into requests, merging ranges that touch. */
export function mergeRanges(ranges) {
  const sorted = [...ranges].sort((a, b) => a.start - b.start);
  const out = [];
  for (const r of sorted) {
    const last = out[out.length - 1];
    if (last && r.start <= last.end) {
      last.end = Math.max(last.end, r.end);
      last.parts.push(r);
    } else out.push({ start: r.start, end: r.end, parts: [r] });
  }
  return out;
}

/**
 * Affine map from a fragment's quantized draco positions to model space:
 * model = gridOrigin + vertexOffset[lod] + chunkShape * 2^lod * (pos + q / (2^bits - 1)),
 * then the volume's 3x4 `transform` (row-major). Returns {scale: [3], offset: [3]} per axis
 * (the MaleCNS transforms are diagonal; off-diagonal terms are rejected).
 */
export function fragmentTransform(
  manifest,
  lod,
  pos,
  quantizationBits,
  transform,
) {
  for (const [i, t] of [1, 2, 4, 6, 8, 9].map((i) => [i, transform[i]])) {
    if (t !== 0) throw new Error(`non-diagonal mesh transform (entry ${i})`);
  }
  const diag = [transform[0], transform[5], transform[10]];
  const shift = [transform[3], transform[7], transform[11]];
  const qmax = 2 ** quantizationBits - 1;
  const scale = [],
    offset = [];
  for (let a = 0; a < 3; a++) {
    const side = manifest.chunkShape[a] * 2 ** lod;
    const base =
      manifest.gridOrigin[a] + manifest.vertexOffsets[lod][a] + side * pos[a];
    scale.push((diag[a] * side) / qmax);
    offset.push(diag[a] * base + shift[a]);
  }
  return { scale, offset };
}

/** Axis-aligned bounds of a fragment's chunk, in the same space as fragmentTransform. */
export function fragmentBounds(manifest, lod, pos, transform) {
  const min = [], max = [];
  for (let a = 0; a < 3; a++) {
    const side = manifest.chunkShape[a] * 2 ** lod;
    const lo = manifest.gridOrigin[a] + manifest.vertexOffsets[lod][a] + side * pos[a];
    const d = transform[a * 5], t = transform[a * 4 + 3];
    min.push(d * lo + t);
    max.push(d * (lo + side) + t);
  }
  return { min, max };
}

// ---------- skeletons and legacy meshes ----------

/** Unsharded precomputed skeleton: uint32 nv, ne; float32 xyz[nv]; uint32 edges[2*ne]. */
export function parseSkeleton(buf) {
  const v = new DataView(buf);
  const nv = v.getUint32(0, true),
    ne = v.getUint32(4, true);
  return {
    vertices: new Float32Array(buf.slice(8, 8 + 12 * nv)),
    edges: new Uint32Array(buf.slice(8 + 12 * nv, 8 + 12 * nv + 8 * ne)),
  };
}

/** Legacy mesh fragment: uint32 nv; float32 xyz[nv]; uint32 triangles[...]. */
export function parseLegacyMesh(buf) {
  const nv = new DataView(buf).getUint32(0, true);
  return {
    vertices: new Float32Array(buf.slice(4, 4 + 12 * nv)),
    indices: new Uint32Array(buf.slice(4 + 12 * nv)),
  };
}
