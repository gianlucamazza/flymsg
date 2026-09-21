// node --test tests/js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  fragmentBounds,
  fragmentTransform,
  gunzip,
  mergeRanges,
  murmur3x86_128Low64,
  parseLegacyMesh,
  parseMinishardIndex,
  parseMultilodManifest,
  parseSkeleton,
  shardLocation,
} from "../../src/flymsg/viz_static/precomputed.js";

const MESH_SHARDING = {
  "@type": "neuroglancer_uint64_sharded_v1",
  hash: "murmurhash3_x86_128",
  preshift_bits: 6,
  minishard_bits: 8,
  shard_bits: 10,
  minishard_index_encoding: "gzip",
  data_encoding: "gzip",
};

// Vectors from Python mmh3.hash64(..., x64arch=False)[0] (unsigned)
const RAW = {
  "": 0n,
  61: 6149295974043128636n,
  616263: 11722877137761191633n,
  "30313233343536373839616263646566": 3940318768118187017n,
  "3031323334353637383961626364656658595a": 5379454296622070735n,
};
const SEGMENTS = {
  10001: [196, 636],
  22847: [19, 727],
  800146: [227, 131],
  12781: [18, 533],
  556329: [59, 659],
  0: [65, 174],
  1099511640121: [3, 762],
};

test("murmurhash3_x86_128 low 64 bits match mmh3", () => {
  for (const [hex, want] of Object.entries(RAW)) {
    const bytes = Uint8Array.from(hex.match(/../g) ?? [], (h) => parseInt(h, 16));
    assert.equal(murmur3x86_128Low64(bytes), want, `input ${hex}`);
  }
});

test("shard location of segment ids", () => {
  for (const [seg, [minishard, shard]] of Object.entries(SEGMENTS)) {
    const loc = shardLocation(BigInt(seg), MESH_SHARDING);
    assert.deepEqual([loc.minishard, loc.shard], [minishard, shard], `segment ${seg}`);
  }
  assert.equal(shardLocation(10001n, MESH_SHARDING).file, "27c.shard"); // verified against GCS
});

test("minishard index: delta-coded keys and offsets", () => {
  // two chunks: key 5 at +10 (size 4), key 9 right after a 2-byte gap (size 3)
  const words = [5n, 4n, 10n, 2n, 4n, 3n];
  const buf = new ArrayBuffer(48);
  words.forEach((w, i) => new DataView(buf).setBigUint64(8 * i, w, true));
  const mi = parseMinishardIndex(buf, 100);
  assert.deepEqual(mi.keys, [5n, 9n]);
  assert.deepEqual(mi.start, [110, 116]);
  assert.deepEqual(mi.size, [4, 3]);
});

test("GF 10001 multilod manifest (fixture from GCS)", async () => {
  const raw = readFileSync(new URL("../fixtures/manifest-10001.bin", import.meta.url));
  const buf = await gunzip(raw);
  const m = parseMultilodManifest(buf, 1130353161);
  assert.deepEqual(m.chunkShape, [1024, 1024, 1024]);
  assert.deepEqual(m.lodScales, [1, 2, 4, 8]);
  assert.deepEqual(m.lods.map((l) => l.length), [206, 80, 29, 16]);
  const bytes = m.lods.map((l) => l.reduce((s, f) => s + f.size, 0));
  assert.deepEqual(bytes, [51839451, 6583310, 972903, 169399]);
  assert.equal(m.lods[0][0].start, 1130353161 - bytes.reduce((a, b) => a + b));
  const last = m.lods[3].at(-1);
  assert.equal(last.start + last.size, 1130353161); // fragments end where the manifest begins
});

test("fragment transform and bounds", () => {
  const manifest = { chunkShape: [1024, 1024, 1024], gridOrigin: [0, 0, 0], vertexOffsets: [[0, 0, 0], [0, 0, 0]] };
  const T = [16, 0, 0, 0, 0, 16, 0, 0, 0, 0, 16, 0];
  const t = fragmentTransform(manifest, 1, [3, 0, 1], 16, T);
  // q = 0 -> chunk corner, q = 65535 -> opposite corner
  assert.deepEqual(t.offset, [16 * 2048 * 3, 0, 16 * 2048]);
  assert.equal(t.offset[0] + t.scale[0] * 65535, 16 * 2048 * 4);
  const b = fragmentBounds(manifest, 1, [3, 0, 1], T);
  assert.deepEqual(b.min, t.offset);
  assert.deepEqual(b.max, [16 * 2048 * 4, 16 * 2048, 16 * 2048 * 2]);
  assert.throws(() => fragmentTransform(manifest, 0, [0, 0, 0], 16, [16, 1, 0, 0, 0, 16, 0, 0, 0, 0, 16, 0]));
});

test("merge touching byte ranges", () => {
  const merged = mergeRanges([
    { start: 20, end: 30 },
    { start: 0, end: 10 },
    { start: 10, end: 20 },
    { start: 40, end: 45 },
  ]);
  assert.deepEqual(merged.map((r) => [r.start, r.end, r.parts.length]), [[0, 30, 3], [40, 45, 1]]);
});

test("skeleton and legacy mesh parsers", () => {
  const sk = new ArrayBuffer(8 + 24 + 8);
  const v = new DataView(sk);
  v.setUint32(0, 2, true);
  v.setUint32(4, 1, true);
  [1, 2, 3, 4, 5, 6].forEach((x, i) => v.setFloat32(8 + 4 * i, x, true));
  v.setUint32(32, 0, true);
  v.setUint32(36, 1, true);
  const s = parseSkeleton(sk);
  assert.deepEqual([...s.vertices], [1, 2, 3, 4, 5, 6]);
  assert.deepEqual([...s.edges], [0, 1]);

  const m = new ArrayBuffer(4 + 36 + 12);
  const w = new DataView(m);
  w.setUint32(0, 3, true);
  [0, 0, 0, 1, 0, 0, 0, 1, 0].forEach((x, i) => w.setFloat32(4 + 4 * i, x, true));
  [0, 1, 2].forEach((x, i) => w.setUint32(40 + 4 * i, x, true));
  const mesh = parseLegacyMesh(m);
  assert.equal(mesh.vertices.length, 9);
  assert.deepEqual([...mesh.indices], [0, 1, 2]);
});

test(
  "live: ShardedReader finds the GF manifest on GCS (FLYMSG_NETWORK=1)",
  { skip: !process.env.FLYMSG_NETWORK },
  async () => {
    const { ShardedReader, fetchJson } = await import("../../src/flymsg/viz_static/precomputed.js");
    const dir = "v1.0/segmentation/multi-res-meshes";
    const info = await fetchJson(`${dir}/info`);
    assert.equal(info["@type"], "neuroglancer_multilod_draco");
    const got = await new ShardedReader(dir, info.sharding).read(10001n);
    assert.equal(got.path, `${dir}/27c.shard`);
    assert.equal(got.start, 1130353161);
    const fixture = await gunzip(readFileSync(new URL("../fixtures/manifest-10001.bin", import.meta.url)));
    assert.deepEqual(new Uint8Array(got.data), new Uint8Array(fixture));
  },
);
