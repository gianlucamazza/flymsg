#!/usr/bin/env node
// Surface area of MaleCNS neurons from their published meshes at full resolution (LOD 0),
// with the viewer's own readers: the sharded multilod manifest (precomputed.js), the Draco
// decoder the page vendors, and the fragment transform the page draws with. One JSON line
// per body: bodyId, area in µm², non-empty fragments and triangles; a body without a mesh gets
// "missing". Areas sum the fragments' triangles; fragments partition a neuron's mesh, so seams
// add nothing and holes in the published mesh are not closed.
//
//   node scripts/mesh_area.mjs BODYID [BODYID ...]
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

import { meshArea } from "../src/flymsg/viz_static/geometry.js";
import {
  ShardedReader,
  fetchBytes,
  fetchJson,
  fragmentTransform,
  mergeRanges,
  parseMultilodManifest,
} from "../src/flymsg/viz_static/precomputed.js";

const SEG = "v1.0/segmentation";
const DRACO = new URL(
  "../src/flymsg/viz_static/vendor/three/examples/jsm/libs/draco/",
  import.meta.url,
);

async function decoderModule() {
  const require = createRequire(import.meta.url);
  const factory = require(new URL("draco_wasm_wrapper.js", DRACO).pathname);
  return factory({ wasmBinary: readFileSync(new URL("draco_decoder.wasm", DRACO)) });
}

function decode(draco, buf) {
  const decoder = new draco.Decoder();
  const array = new Int8Array(buf);
  const mesh = new draco.Mesh();
  const status = decoder.DecodeArrayToMesh(array, array.byteLength, mesh);
  if (!status.ok() || mesh.ptr === 0) throw new Error(`draco: ${status.error_msg()}`);
  const attribute = decoder.GetAttribute(mesh, decoder.GetAttributeId(mesh, draco.POSITION));
  const values = mesh.num_points() * attribute.num_components();
  let ptr = draco._malloc(values * 4);
  decoder.GetAttributeDataArrayForAllPoints(mesh, attribute, draco.DT_FLOAT32, values * 4, ptr);
  const q = new Float32Array(draco.HEAPF32.buffer, ptr, values).slice();
  draco._free(ptr);
  const indices = mesh.num_faces() * 3;
  ptr = draco._malloc(indices * 4);
  decoder.GetTrianglesUInt32Array(mesh, indices * 4, ptr);
  const index = new Uint32Array(draco.HEAPF32.buffer, ptr, indices).slice();
  draco._free(ptr);
  draco.destroy(mesh);
  draco.destroy(decoder);
  return { q, index };
}

async function area(draco, reader, info, bodyId) {
  const got = await reader.read(BigInt(bodyId));
  if (!got) return { bodyId, missing: true };
  const manifest = parseMultilodManifest(got.data, got.start);
  const lod = 0;
  // empty fragments hold no geometry; the viewer skips them too (lod.js)
  const ranges = manifest.lods[lod]
    .filter((f) => f.size > 0)
    .map((f) => ({ start: f.start, end: f.start + f.size, f }));
  let total = 0, triangles = 0;
  for (const req of mergeRanges(ranges)) {
    const buf = await fetchBytes(got.path, req.start, req.end);
    for (const part of req.parts) {
      const { q, index } = decode(draco, buf.slice(part.start - req.start, part.end - req.start));
      const t = fragmentTransform(manifest, lod, part.f.pos, info.vertex_quantization_bits, info.transform);
      const p = new Float64Array(q.length);
      for (let i = 0; i < q.length; i += 3)
        for (let a = 0; a < 3; a++) p[i + a] = t.offset[a] + t.scale[a] * q[i + a];
      total += meshArea(p, index);
      triangles += index.length / 3;
    }
  }
  // the mesh transform is in nanometres: nm² -> µm²
  return { bodyId, area_um2: total / 1e6, lod, fragments: ranges.length, triangles };
}

const ids = process.argv.slice(2);
if (!ids.length || ids.some((x) => !/^\d+$/.test(x))) {
  console.error("usage: mesh_area.mjs BODYID [BODYID ...]");
  process.exit(2);
}
const info = await fetchJson(`${SEG}/multi-res-meshes/info`);
const reader = new ShardedReader(`${SEG}/multi-res-meshes`, info.sharding);
const draco = await decoderModule();
for (const id of ids) console.log(JSON.stringify(await area(draco, reader, info, id)));
