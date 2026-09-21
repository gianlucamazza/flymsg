// flymsg 3D viewer. Neuron surfaces (multi-resolution Draco meshes), skeletons and neuropil
// meshes are streamed from the public MaleCNS volumes on GCS; scene.json (and activity.bin for
// replays) come from `flymsg viz`. See precomputed.js (formats) and lod.js (level of detail).
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

const query = new URLSearchParams(location.search);
const settings = {
  detailPx: Number(query.get("detail")) || 256, // refine a fragment when its chunk exceeds this on screen
  budgetM: Number(query.get("budget")) || 8, // million triangles held on the GPU
  neuropils: query.get("neuropils") !== "0", // ?neuropils=0 starts with every shell hidden (and not downloaded)
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
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);

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
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(world, camera));
// threshold 1: lit surfaces stay below it, only emissive activity blooms
const bloom = new UnrealBloomPass(
  new THREE.Vector2(innerWidth, innerHeight),
  replay ? 0.8 : 0.4,
  0.5,
  1.0,
);
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
  skeletonState: "idle",
}));
const N = neurons.length;
const hash = (s) =>
  [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
const view = {
  colorBy: "group",
  filter: "",
  groupsOn: Object.fromEntries(groups.map((g) => [g, true])),
};
const colourOf = (n) =>
  view.colorBy === "group"
    ? PALETTE[groups.indexOf(n.group) % PALETTE.length]
    : view.colorBy === "transmitter"
      ? (NT_COLORS[n.nt] ?? NT_COLORS.unknown)
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
  side: THREE.DoubleSide,
});
const shared = {
  uActivity: { value: null },
  uGain: { value: replay ? 4.0 : 0.0 },
};
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
        { int id = int(getIndirectIndex(gl_DrawID));
          vActivity = texelFetch(uActivity, ivec2(id % ${INST_TEX_W}, id / ${INST_TEX_W}), 0).r; }
      #else
        vActivity = 0.0;
      #endif`,
    );
  shader.fragmentShader = shader.fragmentShader
    .replace(
      "#include <common>",
      "#include <common>\nuniform float uGain;\nvarying float vActivity;",
    )
    .replace(
      "#include <emissivemap_fragment>",
      "#include <emissivemap_fragment>\ntotalEmissiveRadiance += diffuseColor.rgb * vActivity * uGain;",
    );
};

let batched = null;
const instanceOwner = new Int32Array(MAX_INSTANCES).fill(-1);
const instanceActivity = new THREE.DataTexture(
  new Float32Array(MAX_INSTANCES),
  INST_TEX_W,
  INST_TEX_W,
  THREE.RedFormat,
  THREE.FloatType,
);
shared.uActivity.value = instanceActivity;
let capacityScale = 1; // shrinks if the estimate of triangles per byte undershoots

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
  batched = new THREE.BatchedMesh(
    MAX_INSTANCES,
    Math.ceil(tris * 0.75),
    Math.ceil(tris * 3.3),
    meshMaterial,
  );
  batched.sortObjects = false;
  batched.frustumCulled = false; // its bounds are computed once, while still empty; fragments cull individually
  data.add(batched);
  instanceOwner.fill(-1);
  capacityScale = 1;
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

const stats = { bytes: 0, tris: 0, capacityHits: 0 };
const trisPerByte = () => (stats.bytes > 1e5 ? stats.tris / stats.bytes : 0.6); // 0.6: GF coarsest LOD

function addFragment(n, key, geometry) {
  let gid;
  try {
    gid = batched.addGeometry(geometry);
  } catch {
    batched.optimize(); // compact the holes left by deleted fragments
    try {
      gid = batched.addGeometry(geometry);
    } catch {
      stats.capacityHits++;
      capacityScale *= 0.9;
      remember(`${key}@${n.k}`, geometry);
      return false;
    }
  }
  const iid = batched.addInstance(gid);
  batched.setColorAt(iid, new THREE.Color(colourOf(n)));
  instanceOwner[iid] = n.k;
  n.shown.set(key, { gid, iid, geometry, tris: geometry.index.count / 3 });
  return true;
}

function removeFragment(n, key) {
  const f = n.shown.get(key);
  batched.deleteGeometry(f.gid);
  instanceOwner[f.iid] = -1;
  n.shown.delete(key);
  remember(`${key}@${n.k}`, f.geometry);
}

function decodeFragment(buf, n, lod, frag) {
  return new Promise((resolve, reject) =>
    draco.parse(
      buf,
      (g) => {
        const q = g.getAttribute("position").array;
        const t = fragmentTransform(
          n.manifest,
          lod,
          frag.pos,
          meshInfo.vertex_quantization_bits,
          meshInfo.transform,
        );
        const p = new Float32Array(q.length);
        for (let i = 0; i < q.length; i++)
          p[i] = t.offset[i % 3] + t.scale[i % 3] * q[i];
        const out = new THREE.BufferGeometry();
        out.setAttribute("position", new THREE.BufferAttribute(p, 3));
        out.setIndex(g.index);
        out.computeVertexNormals();
        g.dispose();
        stats.bytes += buf.byteLength;
        stats.tris += out.index.count / 3;
        resolve(out);
      },
      reject,
    ),
  );
}

async function loadManifest(n) {
  n.manifestState = "loading";
  const got = await reader.read(BigInt(n.bodyId));
  if (!got) {
    n.manifestState = "missing"; // skeleton only
    return;
  }
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
  dirty = true;
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
    for (const part of req.parts) {
      const slice = buf.slice(part.start - req.start, part.end - req.start);
      staged.set(
        `${part.lod}:${part.i}`,
        await decodeFragment(slice, n, part.lod, part.f),
      );
    }
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
  refreshSkeletonVisibility();
}

function hideMeshes(n) {
  for (const key of [...n.shown.keys()]) removeFragment(n, key);
  n.shownSig = n.loadingSig = "";
}

// ---------- skeletons: coarsest LOD, and the placeholder while meshes load ----------
const skel = { cap: 1 << 20, nv: 0, ne: 0 };
skel.pos = new Float32Array(3 * skel.cap);
skel.owner = new Float32Array(skel.cap);
skel.idx = new Uint32Array(2 * skel.cap);
const skelGeo = new THREE.BufferGeometry();
const texH = Math.max(1, Math.ceil(N / TEX_W));
const makeTex = () => {
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
const skelColour = makeTex(); // rgb colour, a = visible
const skelActivity = makeTex(); // r = activity
function bindSkeletonBuffers() {
  skelGeo.setAttribute("position", new THREE.BufferAttribute(skel.pos, 3));
  skelGeo.setAttribute("aNeuron", new THREE.BufferAttribute(skel.owner, 1));
  skelGeo.setIndex(new THREE.BufferAttribute(skel.idx, 1));
}
bindSkeletonBuffers();
skelGeo.setDrawRange(0, 0);
const skelMaterial = new THREE.ShaderMaterial({
  uniforms: {
    uColor: { value: skelColour },
    uAct: { value: skelActivity },
    uGain: { value: replay ? 4.0 : 0.0 },
    uBase: { value: replay ? 0.15 : 0.8 }, // in a replay only activity should stand out
  },
  vertexShader: /* glsl */ `
    attribute float aNeuron;
    uniform sampler2D uColor;
    uniform sampler2D uAct;
    uniform float uBase, uGain;
    varying vec3 vColor;
    void main() {
      ivec2 p = ivec2(int(mod(aNeuron, ${TEX_W}.0)), int(aNeuron / ${TEX_W}.0));
      vec4 c = texelFetch(uColor, p, 0);
      vColor = c.rgb * (uBase + uGain * texelFetch(uAct, p, 0).r);
      gl_Position = c.a > 0.5 ? projectionMatrix * modelViewMatrix * vec4(position, 1.0) : vec4(2.0, 2.0, 2.0, 1.0);
    }`,
  fragmentShader: /* glsl */ `
    varying vec3 vColor;
    void main() { gl_FragColor = vec4(vColor, 1.0); }`,
});
const skeletonLines = new THREE.LineSegments(skelGeo, skelMaterial);
skeletonLines.frustumCulled = false;
data.add(skeletonLines);

function appendSkeleton(n, s) {
  const nv = s.vertices.length / 3,
    ne = s.edges.length / 2;
  if (skel.nv + nv > skel.cap || skel.ne + ne > skel.cap) {
    const cap = Math.max(2 * skel.cap, skel.nv + nv, skel.ne + ne);
    const grow = (a, k) => {
      const b = new a.constructor(k * cap);
      b.set(a);
      return b;
    };
    skel.pos = grow(skel.pos, 3);
    skel.owner = grow(skel.owner, 1);
    skel.idx = grow(skel.idx, 2);
    skel.cap = cap;
    bindSkeletonBuffers();
  }
  skel.pos.set(s.vertices, 3 * skel.nv);
  skel.owner.fill(n.k, skel.nv, skel.nv + nv);
  for (let i = 0; i < s.edges.length; i++)
    skel.idx[2 * skel.ne + i] = s.edges[i] + skel.nv;
  skel.nv += nv;
  skel.ne += ne;
  for (const name of ["position", "aNeuron"])
    skelGeo.getAttribute(name).needsUpdate = true;
  skelGeo.index.needsUpdate = true;
  skelGeo.setDrawRange(0, 2 * skel.ne);
}

async function loadSkeleton(n) {
  n.skeletonState = "loading";
  const buf = await fetchBytes(`${SKELETONS}/${n.bodyId}`);
  if (!buf) {
    n.skeletonState = "missing";
    return;
  }
  appendSkeleton(n, parseSkeleton(buf));
  n.skeletonState = "ready";
  refreshSkeletonVisibility();
}

// A neuron shows its skeleton when the budget sends it there, or while it has no surface yet.
let skeletonWanted = new Set();
const skeletonOn = (n) =>
  isShown(n) && (skeletonWanted.has(n.k) || n.shown.size === 0);
function refreshSkeletonVisibility() {
  const c = new THREE.Color();
  const d = skelColour.image.data;
  for (const n of neurons) {
    c.set(colourOf(n));
    d.set([c.r, c.g, c.b, skeletonOn(n) ? 1 : 0], 4 * n.k);
  }
  skelColour.needsUpdate = true;
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
  side: THREE.DoubleSide,
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
    if (buf) parts.push(parseLegacyMesh(buf));
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
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  g.computeVertexNormals();
  const mesh = new THREE.Mesh(g, shellMaterial);
  mesh.renderOrder = 1;
  mesh.visible = shells[name].visible;
  shells[name].mesh = mesh;
  data.add(mesh);
}
const neuropilsListed = (async () => {
  for (const [region, dir] of Object.entries(ROIS)) {
    const props = (await fetchJson(`${dir}/segment_properties/info`)).inline;
    props.ids.forEach((id, i) => {
      const name = props.properties[0].values[i];
      shells[name] = { region, dir, id, mesh: null, visible: settings.neuropils, state: "idle" };
      ensureNeuropil(name);
    });
  }
})();

// ---------- level-of-detail loop ----------
let dirty = true;
controls.addEventListener("change", () => (dirty = true));

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
  if (!dirty) return;
  dirty = false;
  const v = eyeView();
  const candidates = neurons.filter(isShown);
  for (const n of candidates) {
    if (n.manifestState === "idle") {
      n.manifestState = "queued"; // mark now, or every pass would queue it again
      manifestQueue.push(priorityOf(n, v), () => loadManifest(n)).catch(console.error);
    }
  }
  const sel = select(
    candidates.map((n) => ({
      key: n.k,
      priority: priorityOf(n, v),
      manifest: n.manifest,
    })),
    v,
    {
      detailPx: settings.detailPx,
      budgetTris: settings.budgetM * 1e6 * capacityScale,
      trisPerByte: trisPerByte(),
      transform: meshInfo.transform,
    },
  );
  skeletonWanted = new Set(sel.skeletons);
  for (const n of neurons) {
    const want = sel.meshes.get(n.k);
    if (!want) {
      if (n.shown.size || n.loadingSig) hideMeshes(n);
      continue;
    }
    const sig = want.map(({ lod, i }) => `${lod}:${i}`).join(",");
    if (sig !== n.shownSig && sig !== n.loadingSig) {
      n.loadingSig = sig; // the latest selection wins; older queued jobs see it and stop
      fragmentQueue.push(priorityOf(n, v), () => showFragments(n, want, sig)).catch(console.error);
    }
  }
  for (const n of candidates) {
    if (skeletonOn(n) && n.skeletonState === "idle") {
      n.skeletonState = "queued";
      skeletonQueue.push(priorityOf(n, v), () => loadSkeleton(n)).catch(console.error);
    }
  }
  refreshSkeletonVisibility();
}
setInterval(updateSelection, 250);

// ---------- colours, legend, stats ----------
function refreshColours() {
  const c = new THREE.Color();
  for (const n of neurons) {
    c.set(colourOf(n));
    for (const f of n.shown.values()) batched.setColorAt(f.iid, c);
  }
  refreshSkeletonVisibility();
  const entries =
    view.colorBy === "group"
      ? groups.map((g, i) => [g, PALETTE[i % PALETTE.length]])
      : view.colorBy === "transmitter"
        ? [...new Set(meta.neurons.map((n) => n.nt))].map((t) => [
            t,
            NT_COLORS[t] ?? NT_COLORS.unknown,
          ])
        : [["coloured by cell type", "#d8dee9"]];
  document.getElementById("legend").innerHTML = entries
    .map(([l, col]) => `<span><i style="background:${col}"></i>${l}</span>`)
    .join("");
}
refreshColours();

const statsEl = document.getElementById("stats");
let frames = 0,
  fps = 0,
  fpsSince = performance.now();
function updateStats() {
  let surfaces = 0,
    tris = 0;
  for (const n of neurons) {
    if (n.shown.size) surfaces++;
    for (const f of n.shown.values()) tris += f.tris;
  }
  const skeletons = neurons.filter(skeletonOn).length;
  const loading = manifestQueue.size + fragmentQueue.size + skeletonQueue.size;
  const rois = Object.values(shells);
  statsEl.textContent =
    `${surfaces} surfaces · ${skeletons} skeletons · ${(tris / 1e6).toFixed(1)} / ${settings.budgetM} M triangles` +
    ` · ${loading} loading · neuropils ${rois.filter((s) => s.mesh).length}/${rois.length} · ${fps} fps`;
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
  instanceActivity.needsUpdate = true;
  clockEl.textContent = `t = ${t.toFixed(0)} ms · stimulus ${t < A.stim_ms ? "on" : "off"}`;
}

// ---------- picking ----------
const raycaster = new THREE.Raycaster();
raycaster.params.Line.threshold = 1500; // nm, in the data frame
const info = document.getElementById("info");
let downAt = null;
renderer.domElement.addEventListener(
  "pointerdown",
  (e) => (downAt = [e.clientX, e.clientY]),
);
renderer.domElement.addEventListener("pointerup", (e) => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4)
    return; // a drag
  raycaster.setFromCamera(
    new THREE.Vector2(
      (e.clientX / innerWidth) * 2 - 1,
      -(e.clientY / innerHeight) * 2 + 1,
    ),
    camera,
  );
  const owner = (h) =>
    h.object === batched ? instanceOwner[h.batchId] : skel.owner[h.index];
  const hit = raycaster.intersectObjects([batched, skeletonLines]).find((h) => {
    const k = owner(h);
    return (
      k >= 0 &&
      (h.object === batched ? isShown(neurons[k]) : skeletonOn(neurons[k]))
    );
  });
  if (!hit) return;
  const n = neurons[owner(hit)];
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
  .add(view, "colorBy", ["group", "transmitter", "type"])
  .name("colour by")
  .onChange(refreshColours);
gui
  .add(view, "filter")
  .name("type filter")
  .onChange((v) => {
    view.filter = v.toLowerCase();
    dirty = true;
    refreshColours();
  });
gui
  .add(settings, "detailPx", 32, 1024, 1)
  .name("detail (px)")
  .onChange(() => (dirty = true));
gui
  .add(settings, "budgetM", 1, 40, 1)
  .name("budget (M tris)")
  .onFinishChange(() => {
    makeBatched();
    dirty = true;
  });
gui.add(bloom, "strength", 0, 3).name("bloom");
const gFolder = gui.addFolder("Groups");
groups.forEach((g) =>
  gFolder.add(view.groupsOn, g).onChange(() => {
    dirty = true;
    refreshColours();
  }),
);
const pFolder = gui.addFolder("Neuropils");
pFolder.add(shellMaterial.uniforms.uOpacity, "value", 0, 1).name("opacity");
neuropilsListed.then(() => {
  for (const region of Object.keys(ROIS)) {
    const names = Object.keys(shells).filter(
      (s) => shells[s].region === region,
    );
    const f = pFolder.addFolder(region).close();
    const toggles = Object.fromEntries(names.map((n) => [n, shells[n].visible]));
    const boxes = {};
    const set = (name, v) => {
      shells[name].visible = v;
      if (shells[name].mesh) shells[name].mesh.visible = v;
      ensureNeuropil(name);
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
  dirty = true;
});

const timer = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = timer.getDelta();
  if (replay) {
    if (clock.playing)
      clock.t = (clock.t + dt * clock.speed) % (A.bins * A.bin_ms);
    updateActivity(clock.t);
  }
  controls.update();
  composer.render();
  frames++;
  const now = performance.now();
  if (now - fpsSince > 1000) {
    fps = Math.round((frames * 1000) / (now - fpsSince));
    frames = 0;
    fpsSince = now;
  }
});
