// flymsg 3D viewer. Neuron surfaces (multi-resolution Draco meshes), skeletons and neuropil
// meshes are streamed from the public MaleCNS volumes on GCS; scene.json (and activity.bin for
// replays) come from `flymsg viz`. See precomputed.js (formats), lod.js (level of detail),
// geometry.js (fragment finishing, run in geometry-worker.js) and perf.js (measurements).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import GUI from "lil-gui";

import {
  ShardedReader,
  fetchBytes,
  fetchJson,
  fragmentBounds,
  fragmentTransform,
  mergeRanges,
  parseLegacyMesh,
  parseMultilodManifest,
  parseSkeleton,
} from "./precomputed.js";
import { projectedPx, select } from "./lod.js";
import { DIMORPHISM_COLORS, FRU_DSX_COLORS, dimorphismClass, fruDsxClass } from "./colors.js";
import { centroid, signedVolume } from "./geometry.js";
import { Perf } from "./perf.js";

const SEG = "v1.0/segmentation";
const MESHES = `${SEG}/multi-res-meshes`;
const SKELETONS = `${SEG}/skeletons-malecns/skeletons-precomputed`;
const ROIS = {
  brain: "rois/fullbrain-roi-v4",
  vnc: "rois/malecns-vnc-neuropil-roi-v0",
};

const PALETTE = [
  "#4cc9f0",
  "#f72585",
  "#b5e48c",
  "#ffd166",
  "#9b5de5",
  "#ff7b00",
  "#00f5d4",
  "#ef476f",
  "#8ecae6",
  "#e9c46a",
];
const NT_COLORS = {
  acetylcholine: "#4cc9f0",
  gaba: "#f72585",
  glutamate: "#ffd166",
  histamine: "#9b5de5",
  dopamine: "#00f5d4",
  serotonin: "#ff7b00",
  octopamine: "#b5e48c",
  unclear: "#7b8494",
  unknown: "#7b8494",
};
const TAU_MS = 15; // display decay of a spike's glow
const HISTORY_BINS = 5;
const MAX_INSTANCES = 65536; // loaded fragments at once
const INST_TEX_W = 256; // MAX_INSTANCES = 256 x 256
const TEX_W = 1024; // per-neuron textures for skeletons
const IDLE_REDRAW_MS = 250; // scene changes from loading redraw at most this often when nothing moves
const TARGET_FRAME_MS = 1000 / 60;
const MSAA = 4; // samples at rest (see adaptive quality)
// Skeleton LOD: tolerances SKEL_EPS_NM x 2^l, l < SKEL_LEVELS; a level is drawn only while its
// tolerance projects to at most SKEL_ERROR_PX device pixels, so the image matches the full
// skeleton to within half a pixel and zooming in returns every source vertex.
const SKEL_EPS_NM = 32;
const SKEL_LEVELS = 10;
const SKEL_ERROR_PX = 0.5;

const query = new URLSearchParams(location.search);
const settings = {
  detailPx: Number(query.get("detail")) || 256, // refine a fragment when its chunk exceeds this on screen
  budgetM: Number(query.get("budget")) || 8, // million triangles held on the GPU
  // ?neuropils=0|1: start with every shell hidden (and not downloaded) or shown; by default
  // shown in anatomy views and hidden in replays, where the silent skeletons already outline
  // the whole CNS and the 11 M translucent shell triangles cost ~40 ms per frame on an Iris Xe
  neuropils: query.has("neuropils") ? query.get("neuropils") !== "0" : null,
  adaptive: query.get("adaptive") !== "0", // drop MSAA, then pixel ratio, while moving if frames run long
};

// ---------- a small priority queue for network work ----------
class Queue {
  constructor(limit) {
    this.limit = limit;
    this.active = 0;
    this.items = [];
  }
  push(priority, job) {
    return new Promise((resolve, reject) => {
      this.items.push({ priority, job, resolve, reject });
      this.pump();
    });
  }
  pump() {
    while (this.active < this.limit && this.items.length) {
      let best = 0;
      for (let i = 1; i < this.items.length; i++)
        if (this.items[i].priority > this.items[best].priority) best = i;
      const { job, resolve, reject } = this.items.splice(best, 1)[0];
      this.active++;
      job()
        .then(resolve, reject)
        .finally(() => {
          this.active--;
          this.pump();
        });
    }
  }
  get size() {
    return this.active + this.items.length;
  }
}
// HTTP/2 multiplexes requests to the one GCS host, so wide queues are cheap
const manifestQueue = new Queue(32),
  fragmentQueue = new Queue(8),
  skeletonQueue = new Queue(24),
  roiQueue = new Queue(6);

// ---------- fragment finishing off the main thread ----------
const workers = Array.from(
  {
    length: Math.max(1, Math.min(4, (navigator.hardwareConcurrency || 4) - 1)),
  },
  () =>
    new Worker(new URL("./geometry-worker.js", import.meta.url), {
      type: "module",
    }),
);
const jobs = new Map();
let jobId = 0;
for (const w of workers) {
  w.onmessage = ({ data }) => {
    jobs.get(data.id)(data);
    jobs.delete(data.id);
  };
}
/** Dequantize + normals in a worker; `q` and `index` are transferred (not usable afterwards). */
function finish(q, index, scale, offset) {
  if (q.buffer === index.buffer) index = index.slice(); // both are transferred
  return new Promise((resolve) => {
    const id = ++jobId;
    jobs.set(id, resolve);
    workers[id % workers.length].postMessage({ id, q, index, scale, offset }, [
      q.buffer,
      index.buffer,
    ]);
  });
}
/** Skeleton levels of detail in a worker (see skeletonLevels); `edges` stays usable here. */
function skeletonLod(vertices, edges) {
  return new Promise((resolve) => {
    const id = ++jobId;
    jobs.set(id, resolve);
    workers[id % workers.length].postMessage({ kind: "skeleton", id, vertices, edges, base: SKEL_EPS_NM, count: SKEL_LEVELS });
  });
}
function geometryFrom({ positions, normals, index }) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  g.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
  g.setIndex(new THREE.BufferAttribute(index, 1));
  return g;
}

// ---------- scene description and source volumes ----------
const meta = await (await fetch("scene.json")).json();
const actBuf = meta.activity
  ? await (await fetch("activity.bin")).arrayBuffer()
  : null;
const [segInfo, meshInfo] = await Promise.all([
  fetchJson(`${SEG}/info`),
  fetchJson(`${MESHES}/info`),
]);
const scale0 = segInfo.scales[0];
const centreNm = scale0.size.map((n, a) => (n * scale0.resolution[a]) / 2);
const volumeUm = scale0.size.map((n, a) => (n * scale0.resolution[a]) / 1000);
const reader = new ShardedReader(MESHES, meshInfo.sharding);
const draco = new DRACOLoader()
  .setDecoderPath("./vendor/three/examples/jsm/libs/draco/")
  .setDecoderConfig({ type: "wasm" });
draco.preload();
document.getElementById("loading").remove();

// ---------- renderer, camera, light ----------
const nativeRatio = Math.min(devicePixelRatio, 2);
// every frame goes through the composer, so multisampling belongs to its render targets
const renderer = new THREE.WebGLRenderer({ antialias: false });
renderer.setPixelRatio(nativeRatio);
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
const perf = new Perf(renderer);

const world = new THREE.Scene();
world.background = new THREE.Color("#05070a");
const camera = new THREE.PerspectiveCamera(
  40,
  innerWidth / innerHeight,
  0.5,
  50000,
);
world.add(camera);
world.add(new THREE.HemisphereLight("#dfe8ff", "#1c1612", 0.8));
const keyLight = new THREE.DirectionalLight("#ffffff", 1.8); // follows the camera
keyLight.position.set(0.6, 0.8, 1);
keyLight.target.position.set(0, 0, -1);
camera.add(keyLight, keyLight.target);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

const replay = Boolean(meta.activity);
settings.neuropils ??= !replay;
const composer = new EffectComposer(
  renderer,
  new THREE.WebGLRenderTarget(innerWidth, innerHeight, { type: THREE.HalfFloatType, samples: MSAA }),
);
composer.setSize(innerWidth, innerHeight); // sizes the targets with the pixel ratio
composer.addPass(new RenderPass(world, camera));
// threshold 1: lit surfaces stay below it, only emissive activity blooms; nothing glows
// without a replay, so the pass is off there
const bloom = new UnrealBloomPass(
  new THREE.Vector2(innerWidth, innerHeight),
  0.8,
  0.5,
  1.0,
);
bloom.enabled = replay;
composer.addPass(bloom);
composer.addPass(new OutputPass());

// Data live in nm inside `data`; `root` rotates EM space (y grows ventrally) so dorsal is up.
const root = new THREE.Group();
root.rotation.x = Math.PI;
world.add(root);
const data = new THREE.Group();
data.scale.setScalar(1e-3); // nm -> um
data.position.set(...centreNm.map((c) => -c * 1e-3));
root.add(data);

// ---------- redraw scheduling ----------
// Render every frame while the camera moves or a replay plays; otherwise only after the scene
// changed, and then at most every IDLE_REDRAW_MS, so streaming does not keep the GPU busy.
let sceneDirty = true,
  lastRender = 0,
  interacting = false,
  lastMove = 0;
const invalidate = () => (sceneDirty = true);
controls.addEventListener("start", () => (interacting = true));
controls.addEventListener("end", () => (interacting = false));

// ---------- neurons ----------
const groups = [...new Set(meta.neurons.map((n) => n.group))];
const neurons = meta.neurons.map((n, k) => ({
  ...n,
  k,
  manifest: null,
  manifestPath: null,
  manifestState: "idle",
  bounds: null,
  shown: new Map(), // fragment key -> {gid, iid, geometry, tris}
  shownSig: "",
  loadingSig: "",
  skelLod: null, // skeleton levels, once loaded
  skelBase: 0, // first vertex in the shared skeleton buffer
  skeletonState: "idle",
}));
const N = neurons.length;
const hash = (s) =>
  [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
const COLOR_MODES = ["group", "transmitter", "type", "dimorphism", "fru/dsx"];
const view = {
  colorBy: COLOR_MODES.includes(query.get("color")) ? query.get("color") : "group", // ?color=
  filter: "",
  groupsOn: Object.fromEntries(groups.map((g) => [g, true])),
};
const colourOf = (n) =>
  view.colorBy === "group"
    ? PALETTE[groups.indexOf(n.group) % PALETTE.length]
    : view.colorBy === "transmitter"
      ? (NT_COLORS[n.nt] ?? NT_COLORS.unknown)
      : view.colorBy === "dimorphism"
        ? DIMORPHISM_COLORS[dimorphismClass(n.dimorphism)]
        : view.colorBy === "fru/dsx"
          ? FRU_DSX_COLORS[fruDsxClass(n.fruDsx)]
          : PALETTE[hash(n.type) % PALETTE.length];
const isShown = (n) =>
  view.groupsOn[n.group] &&
  (!view.filter || n.type.toLowerCase().includes(view.filter));
const activity = new Float32Array(N);

// ---------- surface meshes: one BatchedMesh holds every loaded fragment ----------
const meshMaterial = new THREE.MeshStandardMaterial({
  color: replay ? 0x404040 : 0xffffff, // dimmed in a replay so the activity glow reads
  roughness: 0.55,
  metalness: 0.0,
  // FrontSide: ?check=winding found outward counter-clockwise winding on every neuron tested
  // (signed volume > 0 from the mesh centroid), so back faces can be culled
  side: THREE.FrontSide,
});
// 4x4 ordered dither for screen-door transparency: order independent, so every instance of the
// one BatchedMesh draw, and every neuron in the one skeleton draw, can have its own opacity
const BAYER4 = /* glsl */ `
  float bayer4(vec2 p) {
    ivec2 q = ivec2(mod(p, 4.0));
    int m[16] = int[16](0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5);
    return (float(m[q.y * 4 + q.x]) + 0.5) / 16.0;
  }`;
const instanceTex = (fill = 0) => {
  const t = new THREE.DataTexture(
    new Float32Array(MAX_INSTANCES).fill(fill),
    INST_TEX_W,
    INST_TEX_W,
    THREE.RedFormat,
    THREE.FloatType,
  );
  t.needsUpdate = true;
  return t;
};
const instanceActivity = instanceTex(); // activity per instance
const instanceNeuron = instanceTex(); // neuron index + 1 per instance (0 = free), for picking
const shared = {
  uActivity: { value: instanceActivity },
  uGain: { value: replay ? 4.0 : 0.0 },
  // opacity of a silent surface in a replay (active ones are opaque), so large neurons do not
  // hide the activity behind them
  uInactiveAlpha: { value: replay ? 0.3 : 1.0 },
};
const instanceIdGlsl = /* glsl */ `int(getIndirectIndex(gl_DrawID))`;
const texelOf = (id) => `ivec2(${id} % ${INST_TEX_W}, ${id} / ${INST_TEX_W})`;
meshMaterial.onBeforeCompile = (shader) => {
  Object.assign(shader.uniforms, shared);
  shader.vertexShader = shader.vertexShader
    .replace(
      "#include <common>",
      "#include <common>\nuniform sampler2D uActivity;\nvarying float vActivity;",
    )
    .replace(
      "#include <batching_vertex>",
      `#include <batching_vertex>
      #ifdef USE_BATCHING
        { int id = ${instanceIdGlsl}; vActivity = texelFetch(uActivity, ${texelOf("id")}, 0).r; }
      #else
        vActivity = 0.0;
      #endif`,
    );
  shader.fragmentShader = shader.fragmentShader
    .replace(
      "#include <common>",
      `#include <common>
      uniform float uGain, uInactiveAlpha;
      varying float vActivity;
      ${BAYER4}`,
    )
    .replace(
      "#include <clipping_planes_fragment>",
      `#include <clipping_planes_fragment>
      if (bayer4(gl_FragCoord.xy) >= mix(uInactiveAlpha, 1.0, clamp(4.0 * vActivity, 0.0, 1.0))) discard;`,
    )
    .replace(
      "#include <emissivemap_fragment>",
      "#include <emissivemap_fragment>\ntotalEmissiveRadiance += diffuseColor.rgb * vActivity * uGain;",
    );
};

let batched = null;
const capacity = { vertices: 0, indices: 0 }; // of the BatchedMesh buffers (allocated lazily by three)
function flushInstanceTextures() {
  if (!instanceTexturesDirty) return;
  instanceActivity.needsUpdate = instanceNeuron.needsUpdate = true;
  instanceTexturesDirty = false;
}
let instanceTexturesDirty = false;

function makeBatched() {
  if (batched) {
    data.remove(batched);
    batched.dispose();
    for (const n of neurons) {
      n.shown.clear();
      n.shownSig = n.loadingSig = "";
    }
  }
  const tris = settings.budgetM * 1e6;
  capacity.vertices = Math.ceil(tris * 0.65); // measured 0.54 vertices per triangle, see vertsPerTri
  capacity.indices = Math.ceil(tris * 3);
  batched = new THREE.BatchedMesh(MAX_INSTANCES, capacity.vertices, capacity.indices, meshMaterial);
  batched.sortObjects = false;
  batched.frustumCulled = false; // its bounds are computed once, while still empty; fragments cull individually
  data.add(batched);
  instanceNeuron.image.data.fill(0);
  instanceTexturesDirty = true;
  invalidate();
}
makeBatched();

// decoded fragments kept on the CPU after leaving the GPU, so zooming back is instant
const lru = new Map();
let lruTris = 0;
function remember(key, geometry) {
  lru.set(key, geometry);
  lruTris += geometry.index.count / 3;
  while (lruTris > settings.budgetM * 1e6 * 0.5 && lru.size) {
    const [k, g] = lru.entries().next().value;
    lru.delete(k);
    lruTris -= g.index.count / 3;
    g.dispose();
  }
}
function recall(key) {
  const g = lru.get(key);
  if (g) {
    lru.delete(key);
    lruTris -= g.index.count / 3;
  }
  return g;
}

// Learned from decoded fragments: the selection budgets triangles from compressed sizes, and the
// GPU buffer runs out of vertices or indices, whichever comes first.
const stats = { bytes: 0, tris: 0, verts: 0, capacityHits: 0 };
const trisPerByte = () => (stats.bytes > 1e5 ? stats.tris / stats.bytes : 0.6); // 0.6: GF coarsest LOD
const vertsPerTri = () => (stats.tris > 1e5 ? stats.verts / stats.tris : 0.6);
/** Triangles the BatchedMesh can actually hold, with 10% slack for fragmentation. */
function effectiveBudget() {
  const byVerts = capacity.vertices / vertsPerTri();
  const byIndices = capacity.indices / 3;
  return 0.9 * Math.min(settings.budgetM * 1e6, byVerts, byIndices);
}

function addFragment(n, key, geometry) {
  let gid;
  try {
    gid = batched.addGeometry(geometry);
  } catch {
    batched.optimize(); // compact the holes left by deleted fragments
    try {
      gid = batched.addGeometry(geometry);
    } catch {
      stats.capacityHits++; // the estimate was off: select again with the updated ratios
      selectionDirty = true;
      remember(`${key}@${n.k}`, geometry);
      return false;
    }
  }
  const iid = batched.addInstance(gid);
  batched.setColorAt(iid, new THREE.Color(colourOf(n)));
  instanceNeuron.image.data[iid] = n.k + 1;
  instanceActivity.image.data[iid] = activity[n.k];
  instanceTexturesDirty = true;
  n.shown.set(key, { gid, iid, geometry, tris: geometry.index.count / 3 });
  invalidate();
  return true;
}

function removeFragment(n, key) {
  const f = n.shown.get(key);
  batched.deleteGeometry(f.gid);
  instanceNeuron.image.data[f.iid] = 0;
  instanceTexturesDirty = true;
  n.shown.delete(key);
  remember(`${key}@${n.k}`, f.geometry);
  invalidate();
}

async function decodeFragment(buf, n, lod, frag) {
  const bytes = buf.byteLength; // DRACOLoader transfers (detaches) the buffer
  const g = await new Promise((resolve, reject) =>
    draco.parse(buf, resolve, reject),
  );
  const t = fragmentTransform(
    n.manifest,
    lod,
    frag.pos,
    meshInfo.vertex_quantization_bits,
    meshInfo.transform,
  );
  const out = geometryFrom(
    await finish(
      g.getAttribute("position").array,
      g.index.array,
      t.scale,
      t.offset,
    ),
  );
  stats.bytes += bytes;
  stats.tris += out.index.count / 3;
  stats.verts += out.getAttribute("position").count;
  perf.count("fragments", bytes);
  return out;
}

async function loadManifest(n) {
  n.manifestState = "loading";
  const got = await reader.read(BigInt(n.bodyId));
  if (!got) {
    n.manifestState = "missing"; // skeleton only
    return;
  }
  perf.count("manifests", got.size);
  n.manifest = parseMultilodManifest(got.data, got.start);
  n.manifestPath = got.path;
  const top = n.manifest.lods.length - 1;
  const boxes = n.manifest.lods[top].map((f) =>
    fragmentBounds(n.manifest, top, f.pos, meshInfo.transform),
  );
  n.bounds = {
    min: [0, 1, 2].map((a) => Math.min(...boxes.map((b) => b.min[a]))),
    max: [0, 1, 2].map((a) => Math.max(...boxes.map((b) => b.max[a]))),
  };
  n.manifestState = "ready";
  selectionDirty = true;
}

// Load every fragment of a selection, then swap it in at once (no holes, no overlaps).
async function showFragments(n, want, sig) {
  if (n.loadingSig !== sig) return; // superseded while queued
  const staged = new Map();
  const ranges = [];
  for (const { lod, i } of want) {
    const key = `${lod}:${i}`;
    if (n.shown.has(key)) continue;
    const cached = recall(`${key}@${n.k}`);
    if (cached) staged.set(key, cached);
    else {
      const f = n.manifest.lods[lod][i];
      ranges.push({ start: f.start, end: f.start + f.size, lod, i, f });
    }
  }
  for (const req of mergeRanges(ranges)) {
    const buf = await fetchBytes(n.manifestPath, req.start, req.end);
    const parts = await Promise.all(
      req.parts.map((part) =>
        decodeFragment(
          buf.slice(part.start - req.start, part.end - req.start),
          n,
          part.lod,
          part.f,
        ),
      ),
    );
    req.parts.forEach((part, j) =>
      staged.set(`${part.lod}:${part.i}`, parts[j]),
    );
    if (n.loadingSig !== sig) break; // selection moved on while loading
  }
  if (n.loadingSig !== sig) {
    for (const [key, g] of staged) remember(`${key}@${n.k}`, g);
    return;
  }
  const keep = new Set(want.map(({ lod, i }) => `${lod}:${i}`));
  for (const key of [...n.shown.keys()])
    if (!keep.has(key)) removeFragment(n, key);
  for (const [key, g] of staged) addFragment(n, key, g);
  n.shownSig = sig;
  n.loadingSig = "";
  skeletonsDirty = true;
  checkWinding(n);
}

function hideMeshes(n) {
  for (const key of [...n.shown.keys()]) removeFragment(n, key);
  n.shownSig = n.loadingSig = "";
}

// ?check=winding: log the signed volume of the first complete coarsest-LOD surfaces. Positive
// means triangles wind counter-clockwise seen from outside, so FrontSide culling is safe.
const windingChecks = [];
function checkWinding(n) {
  if (!query.has("check") || windingChecks.length >= 5 || !n.manifest) return;
  if (windingChecks.some((c) => c.bodyId === n.bodyId)) return;
  const top = n.manifest.lods.length - 1;
  const complete = n.manifest.lods[top].filter((f) => f.size > 0).length;
  const keys = [...n.shown.keys()];
  if (
    keys.length !== complete ||
    keys.some((k) => Number(k.split(":")[0]) !== top)
  )
    return;
  const geoms = [...n.shown.values()].map((f) => f.geometry);
  const origin = centroid(geoms.map((g) => g.getAttribute("position").array));
  let volume = 0;
  for (const g of geoms) volume += signedVolume(g.getAttribute("position").array, g.index.array, origin);
  windingChecks.push({
    bodyId: n.bodyId,
    fragments: keys.length,
    volume_um3: +(volume / 1e9).toFixed(1),
  });
  console.log(`WINDING ${JSON.stringify(windingChecks.at(-1))}`);
}

// ---------- skeletons: coarsest LOD, and the placeholder while meshes load ----------
// All skeletons share one vertex buffer and one LineSegments. The index lists, for every neuron
// whose skeleton is on, the segments of its current level, so hidden skeletons cost nothing and
// everything draws in one call (on an Iris Xe, 2,662 separate draws took 46 ms per frame and
// the same lines in one draw 27 ms).
const texH = Math.max(1, Math.ceil(N / TEX_W));
const neuronTex = () => {
  const t = new THREE.DataTexture(
    new Float32Array(TEX_W * texH * 4),
    TEX_W,
    texH,
    THREE.RGBAFormat,
    THREE.FloatType,
  );
  t.needsUpdate = true;
  return t;
};
const skelColour = neuronTex(); // rgb colour
const skelActivity = neuronTex(); // r = activity
const neuronIndexGlsl = /* glsl */ `ivec2(int(mod(aNeuron, ${TEX_W}.0)), int(aNeuron / ${TEX_W}.0))`;
const skelMaterial = new THREE.ShaderMaterial({
  uniforms: {
    uColor: { value: skelColour },
    uAct: { value: skelActivity },
    uGain: { value: replay ? 4.0 : 0.0 },
    uBase: { value: replay ? 0.15 : 0.8 }, // in a replay only activity should stand out
    uInactiveAlpha: shared.uInactiveAlpha, // silent lines are see-through like silent surfaces
  },
  vertexShader: /* glsl */ `
    attribute float aNeuron;
    uniform sampler2D uColor;
    uniform sampler2D uAct;
    uniform float uBase, uGain;
    varying vec3 vColor;
    varying float vOn; // 0 silent .. 1 active
    void main() {
      ivec2 p = ${neuronIndexGlsl};
      float act = texelFetch(uAct, p, 0).r;
      vOn = clamp(4.0 * act, 0.0, 1.0);
      vec3 c = texelFetch(uColor, p, 0).rgb;
      c = mix(vec3(dot(c, vec3(0.299, 0.587, 0.114))), c, mix(${replay ? "0.35" : "1.0"}, 1.0, vOn));
      vColor = c * (uBase + uGain * act);
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }`,
  fragmentShader: /* glsl */ `
    uniform float uInactiveAlpha;
    varying vec3 vColor;
    varying float vOn;
    ${BAYER4}
    void main() {
      if (bayer4(gl_FragCoord.xy) >= mix(uInactiveAlpha, 1.0, vOn)) discard;
      gl_FragColor = vec4(vColor, 1.0);
    }`,
});
const pool = {
  positions: new Float32Array(3 << 20),
  neuron: new Float32Array(1 << 20), // aNeuron: neuron index per vertex
  used: 0, // vertices
  index: new Uint32Array(1 << 22),
  state: new Int8Array(N).fill(-1), // level drawn per neuron, -1 = off
};
const skelGeometry = new THREE.BufferGeometry();
function poolAttributes() {
  skelGeometry.dispose(); // frees the GPU buffers of the arrays being replaced
  skelGeometry.setAttribute("position", new THREE.BufferAttribute(pool.positions, 3));
  skelGeometry.setAttribute("aNeuron", new THREE.BufferAttribute(pool.neuron, 1));
  skelGeometry.setIndex(new THREE.BufferAttribute(pool.index, 1));
}
poolAttributes();
skelGeometry.setDrawRange(0, 0);
const skeletons = new THREE.LineSegments(skelGeometry, skelMaterial);
skeletons.frustumCulled = false; // bounds change as skeletons stream in
data.add(skeletons);

function appendVertices(n, vertices) {
  const nv = vertices.length / 3;
  n.skelBase = pool.used;
  if (pool.used + nv > pool.neuron.length) {
    const cap = Math.max(2 * pool.neuron.length, pool.used + nv);
    const positions = new Float32Array(3 * cap);
    positions.set(pool.positions.subarray(0, 3 * pool.used));
    const neuron = new Float32Array(cap);
    neuron.set(pool.neuron.subarray(0, pool.used));
    Object.assign(pool, { positions, neuron });
    pool.positions.set(vertices, 3 * pool.used);
    pool.neuron.fill(n.k, pool.used, pool.used + nv);
    poolAttributes();
  } else {
    pool.positions.set(vertices, 3 * pool.used);
    pool.neuron.fill(n.k, pool.used, pool.used + nv);
    const pos = skelGeometry.getAttribute("position"),
      id = skelGeometry.getAttribute("aNeuron");
    pos.addUpdateRange(3 * pool.used, 3 * nv); // upload only the appended slice
    id.addUpdateRange(pool.used, nv);
    pos.needsUpdate = id.needsUpdate = true;
  }
  pool.used += nv;
}

async function loadSkeleton(n) {
  n.skeletonState = "loading";
  const buf = await fetchBytes(`${SKELETONS}/${n.bodyId}`);
  if (!buf) {
    n.skeletonState = "missing";
    return;
  }
  perf.count("skeletons", buf.byteLength);
  const s = parseSkeleton(buf);
  const lod = await skeletonLod(s.vertices, s.edges);
  appendVertices(n, s.vertices);
  n.skelLod = { eps: lod.eps, levels: [s.edges, ...lod.coarser], bounds: lod.bounds, level: 0 };
  setSkeletonLevel(n, eyeView());
  n.skeletonState = "ready";
  skeletonsDirty = true;
}

/** Coarsest skeleton level whose tolerance stays under SKEL_ERROR_PX at the nearest point. */
function setSkeletonLevel(n, v) {
  const { eps, bounds } = n.skelLod;
  let d2 = 0;
  for (let a = 0; a < 3; a++) {
    const e = v.eye[a];
    const gap = e < bounds.min[a] ? bounds.min[a] - e : e > bounds.max[a] ? e - bounds.max[a] : 0;
    d2 += gap * gap;
  }
  const tolNm = (SKEL_ERROR_PX * Math.sqrt(d2)) / (v.pxPerUnit * nativeRatio);
  let level = 0;
  while (level + 1 < eps.length && eps[level + 1] <= tolNm) level++;
  if (level !== n.skelLod.level) {
    n.skelLod.level = level;
    skeletonsDirty = true;
  }
}

// A neuron shows its skeleton when the budget sends it there, or while it has no surface yet.
let skeletonWanted = new Set();
let skeletonsDirty = true,
  lastSkeletonBuild = 0;
const skeletonOn = (n) =>
  isShown(n) && (skeletonWanted.has(n.k) || n.shown.size === 0);
/** Rebuild the shared index when some neuron's skeleton turned on or off or changed level. */
function applySkeletonVisibility() {
  skeletonsDirty = false;
  let changed = false,
    total = 0;
  for (const n of neurons) {
    const st = n.skelLod && skeletonOn(n) ? n.skelLod.level : -1;
    if (st !== pool.state[n.k]) {
      pool.state[n.k] = st;
      changed = true;
    }
    if (st >= 0) total += n.skelLod.levels[st].length;
  }
  if (!changed) return;
  if (total > pool.index.length) {
    pool.index = new Uint32Array(Math.max(total, 2 * pool.index.length));
    poolAttributes();
  }
  let o = 0;
  for (const n of neurons) {
    const st = pool.state[n.k];
    if (st < 0) continue;
    const lv = n.skelLod.levels[st],
      base = n.skelBase;
    for (let i = 0; i < lv.length; i++) pool.index[o + i] = lv[i] + base;
    o += lv.length;
  }
  const index = skelGeometry.getIndex();
  index.clearUpdateRanges();
  index.addUpdateRange(0, total);
  index.needsUpdate = true;
  skelGeometry.setDrawRange(0, total);
  invalidate();
}

// ---------- neuropils at full resolution ----------
const shellMaterial = new THREE.ShaderMaterial({
  uniforms: {
    uOpacity: { value: 0.16 },
    uColor: { value: new THREE.Color("#6f7f98") },
  },
  vertexShader: /* glsl */ `
    varying vec3 vN;
    varying vec3 vV;
    void main() {
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      vN = normalize(normalMatrix * normal);
      vV = normalize(-mv.xyz);
      gl_Position = projectionMatrix * mv;
    }`,
  fragmentShader: /* glsl */ `
    uniform float uOpacity;
    uniform vec3 uColor;
    varying vec3 vN;
    varying vec3 vV;
    void main() {
      float rim = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.5);
      gl_FragColor = vec4(uColor, rim * uOpacity);
    }`,
  transparent: true,
  depthWrite: false,
  side: THREE.DoubleSide, // a see-through shell shows both sides on purpose
});
const shells = {}; // name -> {region, dir, id, mesh | null, visible, state}
// a shell is downloaded the first time it becomes visible
function ensureNeuropil(name) {
  const s = shells[name];
  if (!s.visible || s.state !== "idle") return;
  s.state = "loading";
  roiQueue.push(-1, () => loadNeuropil(s.dir, s.id, name)).catch(console.error); // after neurons
}
async function loadNeuropil(dir, id, name) {
  const manifest = await fetchJson(`${dir}/mesh/${id}:0`);
  if (!manifest) return;
  const parts = [];
  for (const frag of manifest.fragments) {
    const buf = await fetchBytes(`${dir}/mesh/${frag}`);
    if (buf) {
      parts.push(parseLegacyMesh(buf));
      perf.count("neuropils", buf.byteLength);
    }
  }
  if (!parts.length) return;
  const nv = parts.reduce((s, p) => s + p.vertices.length / 3, 0);
  const pos = new Float32Array(3 * nv);
  const idx = new Uint32Array(parts.reduce((s, p) => s + p.indices.length, 0));
  let v0 = 0,
    i0 = 0;
  for (const p of parts) {
    pos.set(p.vertices, 3 * v0);
    for (let i = 0; i < p.indices.length; i++) idx[i0 + i] = p.indices[i] + v0;
    v0 += p.vertices.length / 3;
    i0 += p.indices.length;
  }
  const mesh = new THREE.Mesh(
    geometryFrom(await finish(pos, idx, [1, 1, 1], [0, 0, 0])),
    shellMaterial,
  );
  mesh.renderOrder = 1;
  mesh.visible = shells[name].visible;
  shells[name].mesh = mesh;
  data.add(mesh);
  invalidate();
}
const neuropilsListed = (async () => {
  for (const [region, dir] of Object.entries(ROIS)) {
    const props = (await fetchJson(`${dir}/segment_properties/info`)).inline;
    props.ids.forEach((id, i) => {
      const name = props.properties[0].values[i];
      shells[name] = {
        region,
        dir,
        id,
        mesh: null,
        visible: settings.neuropils,
        state: "idle",
      };
      ensureNeuropil(name);
    });
  }
})();

// ---------- level-of-detail selection ----------
// Recomputed once the camera settles (or at most every 250 ms while it keeps moving) and when
// new manifests arrive.
let selectionDirty = true,
  lastSelection = 0;
controls.addEventListener("change", () => {
  selectionDirty = true;
  lastMove = performance.now();
  invalidate();
});

function eyeView() {
  const eye = data.worldToLocal(camera.position.clone()).toArray();
  const pxPerUnit =
    renderer.domElement.clientHeight /
    (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
  return { eye, pxPerUnit };
}

function priorityOf(n, v) {
  const onScreen = n.bounds ? Math.min(projectedPx(n.bounds, v), 1e6) : 1;
  return (n.group === "stimulus" ? 1e12 : 0) + (1 + (n.rate ?? 0)) * onScreen;
}

function updateSelection() {
  const now = performance.now();
  if (!selectionDirty || (now - lastMove < 120 && now - lastSelection < 250))
    return;
  selectionDirty = false;
  lastSelection = now;
  const v = eyeView();
  const candidates = neurons.filter(isShown);
  for (const n of candidates) {
    if (n.manifestState === "idle") {
      n.manifestState = "queued"; // mark now, or every pass would queue it again
      manifestQueue
        .push(priorityOf(n, v), () => loadManifest(n))
        .catch(console.error);
    }
  }
  const selectStart = performance.now();
  const sel = select(
    candidates.map((n) => ({
      key: n.k,
      priority: priorityOf(n, v),
      manifest: n.manifest,
    })),
    v,
    {
      detailPx: settings.detailPx,
      budgetTris: effectiveBudget(),
      trisPerByte: trisPerByte(),
      transform: meshInfo.transform,
    },
  );
  perf.selectMs.push(performance.now() - selectStart);
  skeletonWanted = new Set(sel.skeletons);
  for (const n of neurons) if (n.skelLod) setSkeletonLevel(n, v);
  for (const n of neurons) {
    const want = sel.meshes.get(n.k);
    if (!want) {
      if (n.shown.size || n.loadingSig) hideMeshes(n);
      continue;
    }
    const sig = want.map(({ lod, i }) => `${lod}:${i}`).join(",");
    if (sig !== n.shownSig && sig !== n.loadingSig) {
      n.loadingSig = sig; // the latest selection wins; older queued jobs see it and stop
      fragmentQueue
        .push(priorityOf(n, v), () => showFragments(n, want, sig))
        .catch(console.error);
    }
  }
  for (const n of candidates) {
    if (skeletonOn(n) && n.skeletonState === "idle") {
      n.skeletonState = "queued";
      skeletonQueue
        .push(priorityOf(n, v), () => loadSkeleton(n))
        .catch(console.error);
    }
  }
  skeletonsDirty = true;
}
setInterval(updateSelection, 50);

// ---------- colours, legend, stats ----------
function refreshColours() {
  const c = new THREE.Color();
  const d = skelColour.image.data;
  for (const n of neurons) {
    c.set(colourOf(n));
    for (const f of n.shown.values()) batched.setColorAt(f.iid, c);
    d.set([c.r, c.g, c.b, 1], 4 * n.k);
  }
  skelColour.needsUpdate = true;
  skeletonsDirty = true;
  const entries =
    view.colorBy === "group"
      ? groups.map((g, i) => [g, PALETTE[i % PALETTE.length]])
      : view.colorBy === "transmitter"
        ? [...new Set(meta.neurons.map((n) => n.nt))].map((t) => [
            t,
            NT_COLORS[t] ?? NT_COLORS.unknown,
          ])
        : view.colorBy === "dimorphism"
          ? Object.entries(DIMORPHISM_COLORS)
          : view.colorBy === "fru/dsx"
            ? Object.entries(FRU_DSX_COLORS)
            : [["coloured by cell type", "#d8dee9"]];
  document.getElementById("legend").innerHTML = entries
    .map(([l, col]) => `<span><i style="background:${col}"></i>${l}</span>`)
    .join("");
}
refreshColours();

const statsEl = document.getElementById("stats");
const perfEl = document.getElementById("perf");
function updateStats() {
  let surfaces = 0,
    tris = 0;
  for (const n of neurons) {
    if (n.shown.size) surfaces++;
    for (const f of n.shown.values()) tris += f.tris;
  }
  const lines = neurons.filter(skeletonOn).length;
  const loading = manifestQueue.size + fragmentQueue.size + skeletonQueue.size;
  const rois = Object.values(shells);
  if (surfaces) perf.mark("first_surface");
  if (
    neurons.every(
      (n) =>
        !isShown(n) ||
        n.shown.size ||
        ["ready", "missing"].includes(n.skeletonState),
    )
  ) {
    perf.mark("all_represented");
  }
  statsEl.textContent =
    `${surfaces} surfaces · ${lines} skeletons · ${(tris / 1e6).toFixed(1)} / ${settings.budgetM} M triangles` +
    ` · ${loading} loading · neuropils ${rois.filter((s) => s.mesh).length}/${rois.length}`;
  perfEl.textContent = perf.line(renderer.getPixelRatio(), samples);
}
setInterval(updateStats, 500);

// ---------- replay ----------
const A = meta.activity;
const spikes = actBuf ? new Uint8Array(actBuf) : null; // bins x N
const clock = {
  t: Number(query.get("t")) || 0,
  playing: replay && !query.has("paused"),
  speed: 40,
};
const clockEl = document.getElementById("clock");
let shownT = null; // replay time whose activity is on the GPU
function updateActivity(t) {
  const b = Math.min(Math.floor(t / A.bin_ms), A.bins - 1);
  for (let k = 0; k < N; k++) {
    let s = 0;
    for (let j = Math.max(0, b - HISTORY_BINS + 1); j <= b; j++) {
      const c = spikes[j * N + k];
      if (c) s += c * Math.exp(-Math.max(0, t - (j + 0.5) * A.bin_ms) / TAU_MS);
    }
    activity[k] = Math.min(1, 0.5 * s);
    skelActivity.image.data[4 * k] = activity[k];
  }
  skelActivity.needsUpdate = true;
  const inst = instanceActivity.image.data;
  for (const n of neurons)
    for (const f of n.shown.values()) inst[f.iid] = activity[n.k];
  instanceTexturesDirty = true;
  clockEl.textContent = `t = ${t.toFixed(0)} ms · stimulus ${t < A.stim_ms ? "on" : "off"}`;
  shownT = t;
  invalidate();
}

// ---------- picking: render neuron ids under the cursor ----------
const PICK = 11; // px window around the cursor, so 1 px skeleton lines can be hit
const pickTarget = new THREE.WebGLRenderTarget(PICK, PICK);
const idToColour = /* glsl */ `vec3(mod(id, 256.0), mod(floor(id / 256.0), 256.0), floor(id / 65536.0)) / 255.0`;
const pickMeshMaterial = new THREE.ShaderMaterial({
  uniforms: { uNeuron: { value: instanceNeuron } },
  vertexShader: /* glsl */ `
    #include <common>
    #include <batching_pars_vertex>
    uniform sampler2D uNeuron;
    flat varying vec3 vId;
    void main() {
      #include <batching_vertex>
      vec4 p = vec4(position, 1.0);
      float id = 0.0;
      #ifdef USE_BATCHING
        p = batchingMatrix * p;
        int iid = ${instanceIdGlsl};
        id = texelFetch(uNeuron, ${texelOf("iid")}, 0).r;
      #endif
      vId = ${idToColour};
      gl_Position = projectionMatrix * modelViewMatrix * p;
    }`,
  fragmentShader: /* glsl */ `
    flat varying vec3 vId;
    void main() { gl_FragColor = vec4(vId, 1.0); }`,
  side: THREE.FrontSide,
});
const pickLineMaterial = new THREE.ShaderMaterial({
  vertexShader: /* glsl */ `
    attribute float aNeuron;
    flat varying vec3 vId;
    void main() {
      float id = aNeuron + 1.0;
      vId = ${idToColour};
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }`,
  fragmentShader: /* glsl */ `
    flat varying vec3 vId;
    void main() { gl_FragColor = vec4(vId, 1.0); }`,
});

function pickAt(x, y) {
  const w = renderer.domElement.clientWidth,
    h = renderer.domElement.clientHeight;
  camera.setViewOffset(
    w,
    h,
    x - (PICK - 1) / 2,
    y - (PICK - 1) / 2,
    PICK,
    PICK,
  );
  flushInstanceTextures(); // the pick shader reads neuron ids from the GPU copy
  const saved = {
    background: world.background,
    shells: data.children.filter(
      (o) => o.material === shellMaterial && o.visible,
    ),
  };
  world.background = null;
  saved.shells.forEach((o) => (o.visible = false));
  batched.material = pickMeshMaterial;
  skeletons.material = pickLineMaterial;
  renderer.setRenderTarget(pickTarget);
  renderer.setClearColor(0x000000, 0);
  renderer.clear();
  renderer.render(world, camera);
  const px = new Uint8Array(4 * PICK * PICK);
  renderer.readRenderTargetPixels(pickTarget, 0, 0, PICK, PICK, px);
  renderer.setRenderTarget(null);
  batched.material = meshMaterial;
  skeletons.material = skelMaterial;
  saved.shells.forEach((o) => (o.visible = true));
  world.background = saved.background;
  camera.clearViewOffset();
  // nearest non-empty pixel to the centre wins
  let best = null,
    bestD = Infinity;
  for (let j = 0; j < PICK; j++)
    for (let i = 0; i < PICK; i++) {
      const o = 4 * (j * PICK + i);
      const id = px[o] + 256 * px[o + 1] + 65536 * px[o + 2];
      const d = (i - (PICK - 1) / 2) ** 2 + (j - (PICK - 1) / 2) ** 2;
      if (id && d < bestD) [best, bestD] = [id - 1, d];
    }
  invalidate();
  return best;
}

// ?check exposes internals for headless diagnostics (scripts/shoot.mjs EVAL=...)
if (query.has("check")) {
  window.flymsg = { THREE, neurons, renderer, composer, bloom, camera, world, data, skeletons, pickAt, pickTarget, pickMeshMaterial, meshMaterial, get batched() { return batched; } };
}
const info = document.getElementById("info");
let downAt = null;
renderer.domElement.addEventListener(
  "pointerdown",
  (e) => (downAt = [e.clientX, e.clientY]),
);
renderer.domElement.addEventListener("pointerup", (e) => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4)
    return; // a drag
  const rect = renderer.domElement.getBoundingClientRect();
  const k = pickAt(e.clientX - rect.left, e.clientY - rect.top);
  if (query.has("check")) console.log(`PICK ${e.clientX},${e.clientY} -> ${k === null ? "none" : neurons[k].bodyId}`);
  if (k === null) return;
  const n = neurons[k];
  const lods = [
    ...new Set([...n.shown.keys()].map((key) => key.split(":")[0])),
  ].sort();
  info.classList.remove("muted");
  info.textContent = [
    n.instance || n.type,
    `bodyId ${n.bodyId}`,
    n.nt,
    n.superclass,
    `group ${n.group}`,
    n.rate == null ? null : `${n.rate} Hz during stimulus`,
    n.shown.size ? `surface, LOD ${lods.join("/")}` : "skeleton",
  ]
    .filter(Boolean)
    .join(" · ");
});

// ---------- GUI ----------
const gui = new GUI({ title: "flymsg" });
gui
  .add(view, "colorBy", COLOR_MODES)
  .name("colour by")
  .onChange(refreshColours);
gui
  .add(view, "filter")
  .name("type filter")
  .onChange((v) => {
    view.filter = v.toLowerCase();
    selectionDirty = true;
    refreshColours();
  });
gui
  .add(settings, "detailPx", 32, 1024, 1)
  .name("detail (px)")
  .onChange(() => (selectionDirty = true));
gui
  .add(settings, "budgetM", 1, 40, 1)
  .name("budget (M tris)")
  .onFinishChange(() => {
    makeBatched();
    selectionDirty = true;
  });
gui
  .add(settings, "adaptive")
  .name("adaptive quality")
  .onChange((on) => on || setQuality(nativeRatio, MSAA));
if (replay) {
  gui.add(bloom, "strength", 0, 3).name("bloom").onChange(invalidate);
  gui.add(shared.uInactiveAlpha, "value", 0.05, 1, 0.05).name("silent surfaces").onChange(invalidate);
}
const gFolder = gui.addFolder("Groups");
groups.forEach((g) =>
  gFolder.add(view.groupsOn, g).onChange(() => {
    selectionDirty = true;
    refreshColours();
  }),
);
const pFolder = gui.addFolder("Neuropils");
pFolder
  .add(shellMaterial.uniforms.uOpacity, "value", 0, 1)
  .name("opacity")
  .onChange(invalidate);
neuropilsListed.then(() => {
  for (const region of Object.keys(ROIS)) {
    const names = Object.keys(shells).filter(
      (s) => shells[s].region === region,
    );
    const f = pFolder.addFolder(region).close();
    const toggles = Object.fromEntries(
      names.map((n) => [n, shells[n].visible]),
    );
    const boxes = {};
    const set = (name, v) => {
      shells[name].visible = v;
      if (shells[name].mesh) shells[name].mesh.visible = v;
      ensureNeuropil(name);
      invalidate();
    };
    f.add({ all: settings.neuropils }, "all").onChange((v) =>
      names.forEach((n) => {
        toggles[n] = v;
        set(n, v);
        boxes[n].updateDisplay();
      }),
    );
    names.forEach(
      (n) => (boxes[n] = f.add(toggles, n).onChange((v) => set(n, v))),
    );
  }
});
if (replay) {
  const rFolder = gui.addFolder("Replay");
  rFolder.add(clock, "playing");
  rFolder.add(clock, "speed", 5, 200).name("speed (sim ms / s)");
  rFolder
    .add(clock, "t", 0, A.bins * A.bin_ms - 1, 1)
    .name("time (ms)")
    .listen();
}

// ---------- adaptive quality ----------
// At rest every frame gets 4x multisampling at the native pixel ratio. While frames are live
// (moving camera, playing replay) and run over the 60 fps budget, multisampling goes first
// (it doubles the cost of the millions of skeleton lines), then the pixel ratio scales by
// sqrt(target / measured), down to MIN_RATIO. Geometry is never touched: only how many
// samples and pixels are rendered.
const MIN_RATIO = 0.5;
let ratio = nativeRatio,
  samples = MSAA,
  tuneFrames = 0,
  floorRatio = MIN_RATIO, // raised when a lower ratio did not pay off, until the next rest
  lastStep = null; // {ratio, frameMs} before the last ratio reduction
function setQuality(r, n) {
  if (r === ratio && n === samples) return;
  if (n !== samples)
    for (const t of [composer.renderTarget1, composer.renderTarget2]) {
      t.samples = n;
      t.dispose(); // recreated with the new sample count on next use
    }
  [ratio, samples] = [r, n];
  renderer.setPixelRatio(r);
  composer.setPixelRatio(r);
  tuneFrames = 0; // wait for frames measured at the new quality
  invalidate();
}
const scaled = (frameMs) => Math.round(ratio * Math.sqrt(TARGET_FRAME_MS / frameMs) * 20) / 20;
function tuneQuality(live) {
  if (!settings.adaptive) return;
  if (!live) {
    floorRatio = MIN_RATIO;
    lastStep = null;
    setQuality(nativeRatio, MSAA);
    return;
  }
  if (++tuneFrames < 12) return;
  const frameMs = perf.recentGpuMs(8) ?? (perf.fps ? 1000 / perf.fps : 0);
  if (!frameMs) return;
  // fewer pixels only help when rasterization dominates; otherwise keep the sharper image
  if (lastStep && ratio < lastStep.ratio) {
    const step = lastStep;
    lastStep = null;
    if (frameMs > 0.9 * step.frameMs) {
      floorRatio = step.ratio;
      setQuality(step.ratio, samples);
      return;
    }
  }
  if (frameMs > TARGET_FRAME_MS * 1.2) {
    if (samples) setQuality(ratio, 0);
    else if (ratio > floorRatio) {
      lastStep = { ratio, frameMs };
      setQuality(Math.max(floorRatio, scaled(frameMs)), 0);
    }
  } else if (frameMs < TARGET_FRAME_MS * 0.7) {
    if (ratio < nativeRatio) setQuality(Math.min(nativeRatio, scaled(frameMs)), 0);
    else if (!samples && 2 * frameMs < TARGET_FRAME_MS * 0.9) setQuality(ratio, MSAA); // fits even doubled
  }
}

// ---------- camera, resize, loop ----------
const extent = Math.max(...volumeUm);
camera.position.set(extent * 0.7, extent * 0.25, extent * 0.55); // oblique: brain and VNC both visible
controls.target.set(0, 0, 0);
controls.update();

addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  composer.setSize(innerWidth, innerHeight);
  selectionDirty = true;
  invalidate();
});

// ?bench=<s>: log one JSON summary after that many seconds (read by scripts/shoot.mjs)
if (query.has("bench")) {
  setTimeout(
    () => {
      const summary = perf.summary({
        neurons: N,
        surfaces: neurons.filter((n) => n.shown.size).length,
        skeletons: neurons.filter(skeletonOn).length,
        queued: manifestQueue.size + fragmentQueue.size + skeletonQueue.size,
        pixel_ratio: renderer.getPixelRatio(),
        msaa: samples,
        winding: windingChecks,
      capacity: {
        hits: stats.capacityHits,
        effective_budget: Math.round(effectiveBudget()),
        verts_per_tri: +vertsPerTri().toFixed(3),
        tris_per_byte: +trisPerByte().toFixed(3),
        ...capacity,
      },
      });
      console.log(`BENCH ${JSON.stringify(summary)}`);
    },
    1000 * Number(query.get("bench")),
  );
}

const timer = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = timer.getDelta();
  const moved = controls.update(); // damping keeps moving after the pointer is released
  const playing = replay && clock.playing;
  if (playing) clock.t = (clock.t + dt * clock.speed) % (A.bins * A.bin_ms);
  if (replay && clock.t !== shownT) updateActivity(clock.t);
  const live = interacting || moved || playing;
  tuneQuality(live);
  const now = performance.now();
  // the index rebuild walks every drawn segment: coalesce streaming updates
  if (skeletonsDirty && now - lastSkeletonBuild >= IDLE_REDRAW_MS) {
    applySkeletonVisibility();
    lastSkeletonBuild = now;
  }
  if (!live && !(sceneDirty && now - lastRender >= IDLE_REDRAW_MS)) return;
  flushInstanceTextures();
  perf.begin();
  composer.render();
  perf.end();
  sceneDirty = false;
  lastRender = now;
});
