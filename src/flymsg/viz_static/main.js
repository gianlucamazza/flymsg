// flymsg 3D viewer. Neuron surfaces (multi-resolution Draco meshes), skeletons and neuropil
// meshes are streamed from the public MaleCNS volumes on GCS; scene.json (and activity.bin for
// replays) come from `flymsg viz`. See precomputed.js (formats), lod.js (level of detail),
// geometry.js (fragment finishing, run in geometry-worker.js) and perf.js (measurements).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { Pass, FullScreenQuad } from "three/addons/postprocessing/Pass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { CopyShader } from "three/addons/shaders/CopyShader.js";
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
import { priorityOf, select } from "./lod.js";
import {
  FOCUS_COLORS,
  REGION_COLORS,
  colourOf as colourIn,
  isShown as shownIn,
  legendEntries,
} from "./colors.js";
import {
  applyChrome,
  autoplay,
  clearHint,
  COARSE,
  hint,
  isTap,
  NARROW,
  showChrome,
} from "./chrome.js";
import {
  effectiveBudget,
  scaledRatio,
  trisPerByte,
  vertsPerTri,
} from "./budget.js";
import { activityAt } from "./activity.js";
import { gradedAt } from "./graded.js";
import { sceneCaption } from "./caption.js";
import {
  compareClass,
  difference,
  differenceLines,
  neuronLines,
  runLines,
  totals,
} from "./compare.js";
import { findNeuron, focusRoles, panelLines, selectParam } from "./partners.js";
import { binAt, rasterRows, selectionExport, selectionRows } from "./raster.js";
import { centroid, signedVolume } from "./geometry.js";
import { Perf } from "./perf.js";
import { installXrObserver } from "./xr.js";
import { XrMetrics } from "./xr-metrics.js";
import { visibleLinePages, writeVisibleEdges } from "./geometry-pages.js";
import { RasterPainter } from "./raster-painter.js";
import { ResidentLineIndex } from "./resident-lines.js";
import { localEyePlanes, sameEyePlanes } from "./page-views.js";
import { selectFidelity } from "./fidelity.js";
import { bufferBytes, geometryArrays } from "./resource-bytes.js";
import { PagedScene } from "./paged-scene.js";
import { SourceSlots } from "./source-slots.js";
import {
  base64,
  capturePasses,
  geometryInventory,
  sha256,
} from "./render-reference.js";
import { BUTTON, motion, padHint, pressedSince, tvMode } from "./gamepad.js";

const SEG = "v1.0/segmentation";
const MESHES = `${SEG}/multi-res-meshes`;
const SKELETONS = `${SEG}/skeletons-malecns/skeletons-precomputed`;
const ROIS = {
  brain: "rois/fullbrain-roi-v4",
  vnc: "rois/malecns-vnc-neuropil-roi-v0",
};

const TAU_MS = 15; // display decay of a spike's glow
const HISTORY_BINS = 5;
const MAX_INSTANCES = 65536; // loaded fragments at once
const DECODED_CACHE_BYTES = 128 * 1024 * 1024;
const GEOMETRY_WORKERS = Math.max(
  1,
  Math.min(4, (navigator.hardwareConcurrency || 4) - 1),
);
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
const coarse = matchMedia(COARSE).matches;
const representation = query.get("representation") ?? "surface";
if (!["surface", "skeleton", "mixed"].includes(representation))
  throw new Error("Unknown anatomical representation");
const pagedEnabled = query.get("uploads") === "1";
let pagedInputsDirty = true;
if (pagedEnabled && representation === "mixed")
  throw new Error("Paged uploads require an explicit original representation");
const gpuPageMiB = Number(query.get("gpuPageMiB") ?? 4);
if (![4, 16, 64].includes(gpuPageMiB))
  throw new Error("GPU page size must be 4, 16 or 64 MiB");
// a console's browser (or ?tv=1): larger text, the panel closed, controller hints
const tv = tvMode(location.search, navigator.userAgent);
if (tv) document.documentElement.classList.add("tv");
const settings = {
  representation,
  // a console's browser stops a tab far below a desktop's memory (Edge on a Series S at
  // the desktop defaults: SBOX_FATAL_MEMORY_EXCEEDED), so the TV layout starts leaner
  detailPx: Number(query.get("detail")) || (tv ? 512 : 256), // refine a fragment when its chunk exceeds this on screen
  budgetM: Number(query.get("budget")) || (tv ? 1 : 8), // million triangles held on the GPU
  // ?neuropils=0|1: start with every shell hidden (and not downloaded) or shown; by default
  // shown in anatomy views and hidden in replays, where the silent skeletons already outline
  // the whole CNS and the 11 M translucent shell triangles cost ~40 ms per frame on an Iris Xe
  neuropils: query.has("neuropils") ? query.get("neuropils") !== "0" : null,
  adaptive: representation === "mixed" && query.get("adaptive") !== "0",
  pageCulling: query.get("pages") === "1", // qualification candidate; full reference remains the default until visual/device gates pass
  residentLines: query.get("resident") !== "0", // applies only to strict skeleton page culling
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
  skeletonPreparationQueue = new Queue(GEOMETRY_WORKERS),
  roiQueue = new Queue(6);

// ---------- fragment finishing off the main thread ----------
const workers = Array.from(
  {
    length: GEOMETRY_WORKERS,
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
    const job = jobs.get(data.id);
    if (!job) return;
    if (data.error) job.reject(new Error(data.error));
    else job.resolve(data);
    jobs.delete(data.id);
  };
}
/** Dequantize + normals in a worker; `q` and `index` are transferred (not usable afterwards). */
function finish(q, index, scale, offset) {
  if (q.buffer === index.buffer) index = index.slice(); // both are transferred
  return new Promise((resolve, reject) => {
    const id = ++jobId;
    jobs.set(id, { resolve, reject });
    workers[id % workers.length].postMessage({ id, q, index, scale, offset }, [
      q.buffer,
      index.buffer,
    ]);
  });
}
/** Skeleton levels of detail in a worker (see skeletonLevels); `edges` stays usable here. */
function skeletonLod(vertices, edges) {
  return new Promise((resolve, reject) => {
    const id = ++jobId;
    jobs.set(id, { resolve, reject });
    workers[id % workers.length].postMessage({
      kind: "skeleton",
      id,
      vertices,
      edges,
      base: SKEL_EPS_NM,
      count: representation === "mixed" ? SKEL_LEVELS : 0,
    });
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
const SCENE_SCHEMA = "flymsg.scene/v1"; // viz.SCENE_SCHEMA
const meta = await (await fetch("scene.json")).json();
if (meta.schema !== SCENE_SCHEMA)
  console.warn(
    `scene.json is ${meta.schema ?? "unversioned"}, this page reads ${SCENE_SCHEMA}; ` +
      "re-export it with this flymsg version",
  );
const actBuf = meta.activity
  ? await (await fetch("activity.bin")).arrayBuffer()
  : null;
// graded (non-spiking) neurons: signed potential per bin, from flymsg viz --eye
const gradedSteps = meta.graded
  ? new Int8Array(await (await fetch("graded.bin")).arrayBuffer())
  : null;
const comparison = meta.comparison ?? null; // two runs, from flymsg viz-compare
const actBufB = comparison
  ? await (await fetch("activity_b.bin")).arrayBuffer()
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
// The canvas itself is not antialiased: the scene is drawn into a multisampled target and
// resolved. The composer buffers stay single-sampled (see ScenePass).
const renderer = new THREE.WebGLRenderer({ antialias: false });
renderer.setPixelRatio(nativeRatio);
renderer.setSize(innerWidth, innerHeight);
// setSize updates the viewport but leaves the default scissor (300×150). It is off, and stays
// off; keep the rectangle equal to the canvas so turning it on cannot clip the picture.
renderer.setScissor(0, 0, innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
const perf = new Perf(renderer);

const world = new THREE.Scene();
world.background = new THREE.Color("#05070a");
const camera = new THREE.PerspectiveCamera(
  40,
  innerWidth / innerHeight,
  0.5,
  5000,
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
// Composer targets stay single-sampled. The scene is drawn into the multisampled target and
// resolved once; bloom only ever samples that resolved picture.
const composer = new EffectComposer(
  renderer,
  new THREE.WebGLRenderTarget(innerWidth, innerHeight, {
    type: THREE.HalfFloatType,
  }),
);
const msaaTarget = new THREE.WebGLRenderTarget(1, 1, {
  type: THREE.HalfFloatType,
  samples: MSAA,
});
const sceneRender = new RenderPass(world, camera);
const resolveMaterial = new THREE.ShaderMaterial({
  uniforms: THREE.UniformsUtils.clone(CopyShader.uniforms),
  vertexShader: CopyShader.vertexShader,
  fragmentShader: CopyShader.fragmentShader,
  depthTest: false,
  depthWrite: false,
  toneMapped: false,
});
const resolveQuad = new FullScreenQuad(resolveMaterial);
class ScenePass extends Pass {
  constructor() {
    super();
    this.needsSwap = false; // RenderPass draws into the read buffer; bloom reads it back
  }
  setSize(width, height) {
    msaaTarget.setSize(width, height);
  }
  render(renderer, writeBuffer, readBuffer, deltaTime, maskActive) {
    const dest = samples > 0 ? msaaTarget : readBuffer;
    sceneRender.render(renderer, writeBuffer, dest, deltaTime, maskActive);
    if (dest === readBuffer) return;
    resolveMaterial.uniforms.tDiffuse.value = msaaTarget.texture;
    renderer.setRenderTarget(readBuffer);
    resolveQuad.render(renderer);
  }
}
composer.setSize(innerWidth, innerHeight); // sizes the targets with the pixel ratio
composer.addPass(new ScenePass());
// threshold 1: lit surfaces stay below it, only emissive activity blooms; nothing glows
// without a replay, so the pass is off there
const bloom = new UnrealBloomPass(
  new THREE.Vector2(innerWidth, innerHeight),
  0.8,
  0.5,
  1.0,
);
bloom.enabled = replay;
// The stock radius-11 blur wrote NaN into its 44×29 mip on this GPU. The composite stretched
// that NaN over the empty part of the frame, and adding the glow back turned those pixels
// black (a paused pIP10 replay, 4× MSAA still on). Weights are inlined and the taps unrolled,
// and a non-finite sample adds nothing, so a bad mip cannot erase the picture. ONE, ONE adds
// the glow rgb as computed; SRC_ALPHA would scale it by the mip alpha.
bloom.blendMaterial.depthTest = false;
bloom.blendMaterial.depthWrite = false;
bloom.blendMaterial.premultipliedAlpha = true;
const kernelRadii = [3, 5, 7, 9, 11];
const blurShader = (radius) => {
  const coef = Array.from(
    { length: radius },
    (_, i) =>
      (0.39894 * Math.exp((-0.5 * (i * i)) / (radius * radius))) / radius,
  );
  const lit = (n) => n.toExponential(8);
  let taps = "";
  for (let i = 1; i < radius; i++) {
    taps += `
      {
        vec2 off = direction * invSize * float(${i});
        vec3 a = texture2D(colorTexture, vUv + off).rgb;
        vec3 b = texture2D(colorTexture, vUv - off).rgb;
        if (a.x == a.x) { diffuseSum += a * ${lit(coef[i])}; weightSum += ${lit(coef[i])}; }
        if (b.x == b.x) { diffuseSum += b * ${lit(coef[i])}; weightSum += ${lit(coef[i])}; }
      }`;
  }
  return `
    uniform sampler2D colorTexture;
    uniform vec2 invSize;
    uniform vec2 direction;
    varying vec2 vUv;
    void main() {
      vec3 center = texture2D(colorTexture, vUv).rgb;
      float weightSum = 0.0;
      vec3 diffuseSum = vec3(0.0);
      if (center.x == center.x) { diffuseSum = center * ${lit(coef[0])}; weightSum = ${lit(coef[0])}; }
      ${taps}
      vec3 color = diffuseSum / max(weightSum, 1.0e-4);
      gl_FragColor = vec4(color.x == color.x ? color : vec3(0.0), 1.0);
    }`;
};
bloom.separableBlurMaterials.forEach((material, i) => {
  material.fragmentShader = blurShader(kernelRadii[i]);
  material.depthTest = false;
  material.depthWrite = false;
  material.needsUpdate = true;
});
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
const COLOR_MODES = ["group", "transmitter", "type", "dimorphism", "fru/dsx"];
const view = {
  colorBy: COLOR_MODES.includes(query.get("color"))
    ? query.get("color")
    : "group", // ?color=
  filter: "",
  groupsOn: Object.fromEntries(groups.map((g) => [g, true])),
  focus: null, // row -> role while a neuron is selected
};
const colourOf = (n) => colourIn(n, view, groups);
const isShown = (n) => shownIn(n, view);
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
// glow of a hyperpolarized graded neuron (negative activity); depolarization keeps the
// neuron's own colour
const HYPER_GLSL = /* glsl */ `vec3(0.62, 0.32, 1.00)`; // violet, apart from every group colour
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
      if (bayer4(gl_FragCoord.xy) >= mix(uInactiveAlpha, 1.0, clamp(4.0 * abs(vActivity), 0.0, 1.0))) discard;`,
    )
    .replace(
      "#include <emissivemap_fragment>",
      `#include <emissivemap_fragment>
      totalEmissiveRadiance += (vActivity >= 0.0 ? diffuseColor.rgb : ${HYPER_GLSL}) * abs(vActivity) * uGain;`,
    );
};

let batched = null;
const sourceSlots = new SourceSlots(MAX_INSTANCES);
let referenceSurfacesDirty = true;
const capacity = { vertices: 0, indices: 0 }; // of the BatchedMesh buffers (allocated lazily by three)
function flushInstanceTextures() {
  if (!instanceTexturesDirty) return;
  instanceActivity.needsUpdate = instanceNeuron.needsUpdate = true;
  instanceTexturesDirty = false;
}
let instanceTexturesDirty = false;

function makeBatched() {
  sourceSlots.reset();
  referenceSurfacesDirty = true;
  if (batched) {
    data.remove(batched);
    batched.dispose();
    for (const n of neurons) {
      n.shown.clear();
      n.shownSig = n.loadingSig = "";
    }
  }
  const tris =
    settings.representation === "skeleton" ? 0 : settings.budgetM * 1e6;
  capacity.vertices = Math.ceil(tris * 0.65); // measured 0.54 vertices per triangle, see vertsPerTri
  capacity.indices = Math.ceil(tris * 3);
  batched = new THREE.BatchedMesh(
    MAX_INSTANCES,
    capacity.vertices,
    capacity.indices,
    meshMaterial,
  );
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
let lruBytes = 0;
function remember(key, geometry) {
  if (lru.has(key)) {
    const previous = lru.get(key);
    lruBytes -= bufferBytes(geometryArrays(previous));
    lru.delete(key);
    if (previous !== geometry) previous.dispose();
  }
  lru.set(key, geometry);
  lruBytes += bufferBytes(geometryArrays(geometry));
  while (lruBytes > DECODED_CACHE_BYTES && lru.size) {
    const [k, g] = lru.entries().next().value;
    lru.delete(k);
    lruBytes -= bufferBytes(geometryArrays(g));
    g.dispose();
  }
}
function recall(key) {
  const g = lru.get(key);
  if (g) {
    lru.delete(key);
    lruBytes -= bufferBytes(geometryArrays(g));
  }
  return g;
}

// Learned from decoded fragments: the selection budgets triangles from compressed sizes, and the
// GPU buffer runs out of vertices or indices, whichever comes first.
const stats = { bytes: 0, tris: 0, verts: 0, capacityHits: 0 };

function addFragment(n, key, geometry) {
  if (pagedEnabled) {
    const iid = sourceSlots.allocate();
    n.shown.set(key, {
      gid: null,
      iid,
      geometry,
      tris: geometry.index.count / 3,
    });
    instanceNeuron.image.data[iid] = n.k + 1;
    instanceActivity.image.data[iid] = activity[n.k];
    instanceTexturesDirty = referenceSurfacesDirty = pagedInputsDirty = true;
    invalidate();
    return true;
  }
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
  pagedInputsDirty = true;
  invalidate();
  return true;
}

function removeFragment(n, key) {
  const f = n.shown.get(key);
  if (pagedEnabled) {
    sourceSlots.release(f.iid);
    referenceSurfacesDirty = true;
  } else batched.deleteGeometry(f.gid);
  instanceNeuron.image.data[f.iid] = 0;
  instanceTexturesDirty = true;
  n.shown.delete(key);
  pagedInputsDirty = true;
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
  for (const g of geoms)
    volume += signedVolume(
      g.getAttribute("position").array,
      g.index.array,
      origin,
    );
  windingChecks.push({
    bodyId: n.bodyId,
    fragments: keys.length,
    volume_um3: +(volume / 1e9).toFixed(1),
  });
  console.log(`WINDING ${JSON.stringify(windingChecks.at(-1))}`);
}

// ---------- original skeletons; LOD/fallback only in the mixed diagnostic ----------
// One vertex arena and LineSegments object. The compact reference draws once;
// resident page scheduling uses at most eight public geometry groups, preserving
// original order. Hidden neurons remain hard barriers between eligible ranges.
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
      float act = texelFetch(uAct, p, 0).r; // negative: a hyperpolarized graded neuron
      vOn = clamp(4.0 * abs(act), 0.0, 1.0);
      vec3 c = texelFetch(uColor, p, 0).rgb;
      if (act < 0.0) c = ${HYPER_GLSL};
      c = mix(vec3(dot(c, vec3(0.299, 0.587, 0.114))), c, mix(${replay ? "0.35" : "1.0"}, 1.0, vOn));
      vColor = c * (uBase + uGain * abs(act));
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
  positions: new Float32Array(pagedEnabled ? 0 : 3 << 20),
  neuron: new Float32Array(pagedEnabled ? 0 : 1 << 20), // aNeuron: neuron index per vertex
  used: 0, // vertices
  index: new Uint32Array(pagedEnabled ? 0 : 1 << 22),
  state: new Int8Array(N).fill(-1), // level drawn per neuron, -1 = off
};
const skelGeometry = new THREE.BufferGeometry();
const residentLines = new ResidentLineIndex(8);
let residentGeometry = null,
  compactGeneration = -1;
let lineSubmission = { mode: "compact", draws: 0 };
function releaseResidentGeometry() {
  if (!residentGeometry) return;
  // Vertex attributes belong to skelGeometry; dispose only this index/VAO owner.
  for (const name of Object.keys(residentGeometry.attributes))
    residentGeometry.deleteAttribute(name);
  residentGeometry.dispose();
  residentGeometry = null;
}
function poolAttributes() {
  releaseResidentGeometry();
  compactGeneration = -1;
  residentLines.releaseArena();
  skelGeometry.dispose(); // frees the GPU buffers of the arrays being replaced
  skelGeometry.setAttribute(
    "position",
    new THREE.BufferAttribute(pool.positions, 3),
  );
  skelGeometry.setAttribute(
    "aNeuron",
    new THREE.BufferAttribute(pool.neuron, 1),
  );
  skelGeometry.setIndex(new THREE.BufferAttribute(pool.index, 1));
}
function ensureCompactCapacity(count) {
  if (count <= pool.index.length) return;
  const attributes = { ...skelGeometry.attributes };
  for (const name of Object.keys(attributes))
    skelGeometry.deleteAttribute(name);
  skelGeometry.dispose(); // shared vertices and their other VAO remain resident
  for (const [name, attribute] of Object.entries(attributes))
    skelGeometry.setAttribute(name, attribute);
  pool.index = new Uint32Array(Math.max(count, 2 * pool.index.length));
  skelGeometry.setIndex(new THREE.BufferAttribute(pool.index, 1));
  compactGeneration = -1;
}
poolAttributes();
skelGeometry.setDrawRange(0, 0);
// Arrays make geometry groups apply to colour AND picking/depth passes.
const skeletons = new THREE.LineSegments(skelGeometry, [skelMaterial]);
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
  const { s, lod } = await skeletonPreparationQueue.push(
    priorityOf(n, eyeView()),
    async () => {
      const s = parseSkeleton(buf);
      const lod = await skeletonLod(s.vertices, s.edges);
      return { s, lod };
    },
  );
  if (!pagedEnabled) appendVertices(n, s.vertices);
  n.skelLod = {
    vertices: pagedEnabled ? s.vertices : null, // immutable worker source; never transfer the reference
    eps: lod.eps,
    levels: [s.edges, ...lod.coarser],
    bounds: lod.bounds,
    pages: lod.pages,
    level: 0,
  };
  setSkeletonLevel(n, eyeView());
  n.skeletonState = "ready";
  pagedInputsDirty = true;
  skeletonsDirty = true;
}

/** Coarsest skeleton level whose tolerance stays under SKEL_ERROR_PX at the nearest point. */
function setSkeletonLevel(n, v) {
  if (settings.representation !== "mixed") {
    if (n.skelLod.level !== 0) {
      n.skelLod.level = 0;
      skeletonsDirty = true;
    }
    return;
  }
  const { eps, bounds } = n.skelLod;
  let d2 = 0;
  for (let a = 0; a < 3; a++) {
    const e = v.eye[a];
    const gap =
      e < bounds.min[a]
        ? bounds.min[a] - e
        : e > bounds.max[a]
          ? e - bounds.max[a]
          : 0;
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
let lastSkeletonEyes, lastSkeletonRepresentation, lastResidentEnabled;
const skeletonOn = (n) =>
  isShown(n) &&
  (settings.representation === "skeleton" ||
    (settings.representation === "mixed" &&
      (skeletonWanted.has(n.k) || n.shown.size === 0)));
function skeletonEyes(
  c = camera,
  width = renderer.domElement.width,
  height = renderer.domElement.height,
) {
  world.updateMatrixWorld(true);
  c.updateMatrixWorld(true);
  const cameras = c.isArrayCamera ? c.cameras : [c];
  return localEyePlanes(
    THREE,
    data.matrixWorld,
    cameras.map((eye) => ({
      projection: eye.projectionMatrix,
      inverseWorld: eye.matrixWorldInverse,
      width: eye.viewport?.z ?? width,
      height: eye.viewport?.w ?? height,
    })),
  );
}
/** Rebuild the shared index when some neuron's skeleton turned on or off or changed level. */
function applySkeletonVisibility(eyes = null) {
  if (
    !skeletonsDirty &&
    !selectionDirty &&
    lastSkeletonRepresentation === settings.representation &&
    lastResidentEnabled === settings.residentLines &&
    sameEyePlanes(lastSkeletonEyes, eyes)
  ) {
    if (
      lineSubmission.mode === "resident" &&
      lineSubmission.backend === "groups" &&
      (lineSubmission.bridged_indices || lineSubmission.draws > 1)
    ) {
      ensureCompactCapacity(residentLines.visibleIndices);
      const count = residentLines.copyVisible(pool.index);
      const index = skelGeometry.getIndex();
      index.clearUpdateRanges();
      index.addUpdateRange(0, count);
      index.needsUpdate = true;
      skelGeometry.clearGroups();
      if (count) skelGeometry.addGroup(0, count, 0);
      skelGeometry.setDrawRange(0, count);
      compactGeneration = residentLines.generation;
      skeletons.geometry = skelGeometry;
      lineSubmission = {
        ...lineSubmission,
        backend: "cached-compact",
        draws: Number(count > 0),
        ranges: Number(count > 0),
        submitted_indices: count,
        bridged_indices: 0,
      };
      invalidate();
    }
    return;
  }
  // Copy the stamp: diagnostic callers may reuse and mutate their plane arrays.
  lastSkeletonEyes = eyes?.map((eye) => eye.map((plane) => [...plane])) ?? null;
  lastSkeletonRepresentation = settings.representation;
  lastResidentEnabled = settings.residentLines;
  skeletonsDirty = false;
  let fallback = null;
  if (
    eyes !== null &&
    settings.residentLines &&
    settings.representation === "skeleton" &&
    neurons.every((n) => !isShown(n) || n.skeletonState === "ready")
  ) {
    const rebuilt = residentLines.sync(neurons);
    if (rebuilt || !residentGeometry) {
      releaseResidentGeometry();
      residentGeometry = new THREE.BufferGeometry();
      for (const [name, attribute] of Object.entries(skelGeometry.attributes))
        residentGeometry.setAttribute(name, attribute);
      residentGeometry.setIndex(
        new THREE.BufferAttribute(residentLines.index, 1),
      );
      compactGeneration = -1;
    }
    const plan = residentLines.plan(eyes, skeletonOn, visibleLinePages);
    if (!plan.fallback) {
      const cached = compactGeneration === plan.generation;
      if (rebuilt || plan.changed || lineSubmission.mode !== "resident") {
        residentGeometry.clearGroups();
        for (const r of plan.ranges)
          residentGeometry.addGroup(r.start, r.count, 0);
        residentGeometry.setDrawRange(0, residentLines.count);
        invalidate();
      }
      skeletons.geometry = cached ? skelGeometry : residentGeometry;
      lineSubmission = {
        mode: "resident",
        backend: cached ? "cached-compact" : "groups",
        draws: cached ? Number(plan.visibleIndices > 0) : plan.ranges.length,
        ranges: cached ? Number(plan.visibleIndices > 0) : plan.ranges.length,
        visible_indices: plan.visibleIndices,
        submitted_indices: cached ? plan.visibleIndices : plan.submittedIndices,
        bridged_indices: cached
          ? 0
          : plan.submittedIndices - plan.visibleIndices,
        catalog_builds: residentLines.builds,
      };
      return;
    }
    fallback = plan.fallback;
  }
  // Legacy/reference writes invalidate only the single compact-view cache.
  let changed = lineSubmission.mode === "resident",
    total = 0;
  skeletons.geometry = skelGeometry;
  for (const n of neurons) {
    const st = n.skelLod && skeletonOn(n) ? n.skelLod.level : -1;
    if (st !== pool.state[n.k]) {
      pool.state[n.k] = st;
      changed = true;
    }
    if (st >= 0) {
      const pages = n.skelLod.pages[st];
      const result = visibleLinePages(pages, eyes);
      const previous = n.visiblePages;
      if (
        !previous ||
        previous.length !== result.visible.length ||
        result.visible.some((v, i) => v !== previous[i])
      )
        changed = true;
      n.visiblePages = result.visible;
      total += 2 * result.edges;
    }
  }
  if (!changed) {
    lineSubmission = { ...lineSubmission, mode: "compact", fallback };
    return;
  }
  ensureCompactCapacity(total);
  compactGeneration = -1;
  let o = 0;
  for (const n of neurons) {
    const st = pool.state[n.k];
    if (st < 0) continue;
    o = writeVisibleEdges(
      pool.index,
      o,
      n.skelLod.levels[st],
      n.skelLod.pages[st],
      n.visiblePages,
      n.skelBase,
    );
  }
  const index = skelGeometry.getIndex();
  index.clearUpdateRanges();
  index.addUpdateRange(0, total);
  index.needsUpdate = true;
  skelGeometry.setDrawRange(0, total);
  skelGeometry.clearGroups();
  if (total) skelGeometry.addGroup(0, total, 0);
  lineSubmission = {
    mode: "compact",
    draws: Number(total > 0),
    visible_indices: total,
    submitted_indices: total,
    bridged_indices: 0,
    fallback,
  };
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
  roiQueue
    .push(-1, () => loadNeuropil(s.dir, s.id, name))
    .catch((error) => {
      s.state = "error";
      s.error = String(error);
      pagedInputsDirty = true;
      invalidate();
      console.error(error);
    }); // after neurons
}
async function loadNeuropil(dir, id, name) {
  const manifest = await fetchJson(`${dir}/mesh/${id}:0`);
  if (!manifest)
    throw new Error(`Neuropil ${name}: source manifest unavailable`);
  const parts = [];
  for (const frag of manifest.fragments) {
    const buf = await fetchBytes(`${dir}/mesh/${frag}`);
    if (!buf) throw new Error(`Neuropil ${name}: source fragment unavailable`);
    if (buf) {
      parts.push(parseLegacyMesh(buf));
      perf.count("neuropils", buf.byteLength);
    }
  }
  if (!parts.length) throw new Error(`Neuropil ${name}: empty source mesh`);
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
  shells[name].state = "ready";
  data.add(mesh);
  pagedInputsDirty = true;
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

// ---------- whole CNS: every soma as a point ----------
// docs/live/cns/somata.bin (scripts/build_somata.py): float32 x, y, z per soma in scale-0
// voxels, then a uint8 region code each. The site serves it next to the scenes; a local
// export has none unless ?somata=<url>. ?somata=0 hides the layer. Context only: points are
// neither picked nor coloured by activity.
const somataQuery = query.get("somata");
const somata = {
  visible: somataQuery !== "0",
  opacity: 0.12, // context: the active neurons stay in front
  size: 1.5,
  points: null,
  count: 0,
};
const somataMaterial = new THREE.PointsMaterial({
  size: somata.size,
  sizeAttenuation: false, // pixels, so the cloud reads the same at every zoom
  vertexColors: true,
  transparent: true,
  opacity: somata.opacity,
  depthWrite: false,
});
const somataLoaded = (async () => {
  if (!somata.visible) return;
  const url =
    somataQuery && somataQuery !== "1" ? somataQuery : "../cns/somata.bin";
  let buf;
  try {
    const r = await fetch(url);
    if (!r.ok) return;
    buf = await r.arrayBuffer();
  } catch {
    return; // no layer for this page
  }
  const n = buf.byteLength / 13;
  if (!Number.isInteger(n)) return console.warn(`${url}: not a soma file`);
  const vox = new Float32Array(buf, 0, 3 * n);
  const codes = new Uint8Array(buf, 12 * n, n);
  const pos = new Float32Array(3 * n);
  const col = new Float32Array(3 * n);
  const palette = Object.values(REGION_COLORS).map((c) => new THREE.Color(c));
  for (let i = 0; i < n; i++) {
    for (let a = 0; a < 3; a++)
      pos[3 * i + a] = vox[3 * i + a] * scale0.resolution[a];
    const c = palette[Math.min(codes[i], palette.length - 1)];
    col.set([c.r, c.g, c.b], 3 * i);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  somata.points = new THREE.Points(g, somataMaterial);
  somata.points.renderOrder = 2;
  somata.count = n;
  perf.count("somata", buf.byteLength);
  data.add(somata.points);
  pagedInputsDirty = true;
  renderLegend();
  invalidate();
})();

// ---------- level-of-detail selection ----------
// Recomputed once the camera settles (or at most every 250 ms while it keeps moving) and when
// new manifests arrive.
let selectionDirty = true,
  lastSelection = 0;
let fidelityState = { status: "loading", reasons: [] };
controls.addEventListener("change", () => {
  selectionDirty = true;
  lastMove = performance.now();
  invalidate();
});

function eyeView() {
  const xrCamera = renderer.xr.isPresenting ? renderer.xr.getCamera() : null;
  const eye = data
    .worldToLocal((xrCamera ?? camera).getWorldPosition(new THREE.Vector3()))
    .toArray();
  // XR owns the framebuffer: use actual per-eye viewports and projection, never desktop CSS.
  const pxPerUnit = xrCamera?.cameras.length
    ? Math.max(
        ...xrCamera.cameras.map(
          (c) => (c.viewport.w * c.projectionMatrix.elements[5]) / 2,
        ),
      )
    : renderer.domElement.clientHeight /
      (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
  return { eye, pxPerUnit };
}

function updateSelection() {
  const now = performance.now();
  if (!selectionDirty || (now - lastMove < 120 && now - lastSelection < 250))
    return;
  selectionDirty = false;
  pagedInputsDirty = true;
  lastSelection = now;
  const v = eyeView();
  const candidates = neurons.filter(isShown);
  for (const n of candidates) {
    if (settings.representation !== "skeleton" && n.manifestState === "idle") {
      n.manifestState = "queued"; // mark now, or every pass would queue it again
      manifestQueue
        .push(priorityOf(n, v), () => loadManifest(n))
        .catch((error) => {
          n.manifestState = "missing";
          selectionDirty = true;
          console.error(error);
        });
    }
  }
  const selectStart = performance.now();
  const selectedNeurons = candidates.map((n) => ({
    key: n.k,
    priority: priorityOf(n, v),
    manifest: n.manifest,
    missing: n.manifestState === "missing",
  }));
  const sel =
    settings.representation !== "mixed"
      ? selectFidelity(
          selectedNeurons,
          settings.representation,
          effectiveBudget(stats, capacity, settings.budgetM),
          trisPerByte(stats),
        )
      : select(
          candidates.map((n) => ({
            key: n.k,
            priority: priorityOf(n, v),
            manifest: n.manifest,
          })),
          v,
          {
            detailPx: settings.detailPx,
            budgetTris: effectiveBudget(stats, capacity, settings.budgetM),
            trisPerByte: trisPerByte(stats),
            transform: meshInfo.transform,
          },
        );
  fidelityState =
    settings.representation === "mixed"
      ? {
          status: "unqualified",
          reasons: [
            { reason: "mixed representation changes with resource pressure" },
          ],
        }
      : sel;
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
    if (!n.surfaceError && sig !== n.shownSig && sig !== n.loadingSig) {
      n.loadingSig = sig; // the latest selection wins; older queued jobs see it and stop
      fragmentQueue
        .push(priorityOf(n, v), () => showFragments(n, want, sig))
        .catch((error) => {
          n.surfaceError = String(error);
          n.loadingSig = "";
          console.error(error);
          invalidate();
        });
    }
  }
  for (const n of candidates) {
    if (skeletonOn(n) && n.skeletonState === "idle") {
      n.skeletonState = "queued";
      skeletonQueue
        .push(priorityOf(n, v), () => loadSkeleton(n))
        .catch((error) => {
          n.skeletonState = "missing";
          console.error(error);
          invalidate();
        });
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
    if (!pagedEnabled || !referenceSurfacesDirty)
      for (const f of n.shown.values()) batched.setColorAt(f.iid, c);
    d.set([c.r, c.g, c.b, 1], 4 * n.k);
  }
  skelColour.needsUpdate = true;
  skeletonsDirty = true;
  renderLegend();
}

// The legend names what is on screen: the neuron colours (same precedence as colourOf), what
// the glow means in a replay, and the soma layer's regions while it is shown. Labels come from
// the scene, so they are set as text.
function swatches(entries) {
  const row = document.createElement("div");
  for (const [label, colour] of entries) {
    const span = document.createElement("span");
    const dot = document.createElement("i");
    dot.style.background = colour;
    span.append(dot, label);
    row.append(span);
  }
  return row;
}
// A comparison describes its two runs in its own panel; a single scene says what it is here.
if (!comparison)
  fetch("manifest.json")
    .then((r) => (r.ok ? r.json() : null))
    .then(
      (m) => (document.getElementById("caption").textContent = sceneCaption(m)),
    )
    .catch(() => {});

function renderLegend() {
  const rows = [swatches(legendEntries(view, groups, neurons))];
  if (replay) {
    const glow = document.createElement("div");
    glow.className = "muted";
    glow.textContent = `glow: spikes per ${meta.activity.bin_ms} ms bin (model replay, not a recording)`;
    rows.push(glow);
    if (meta.graded) {
      const g = document.createElement("div");
      g.className = "muted";
      g.textContent =
        "graded neurons: glow ∝ potential from rest (medulla: from its dark anchor), full at its " +
        "measured range; own colour = depolarized, violet = hyperpolarized";
      rows.push(g);
    }
  }
  if (somata.points?.visible) {
    const row = swatches(Object.entries(REGION_COLORS));
    row.className = "muted";
    row.prepend("somata: ");
    rows.push(row);
  }
  document.getElementById("legend").replaceChildren(...rows);
}
refreshColours();

const statsEl = document.getElementById("stats");
const perfEl = document.getElementById("perf");
function fidelityReport() {
  const selected = neurons.filter(isShown);
  const represented = selected.filter((n) =>
    settings.representation === "skeleton"
      ? n.skeletonState === "ready"
      : settings.representation === "surface"
        ? n.shown.size > 0 &&
          n.shown.size === fidelityState.meshes?.get(n.k)?.length
        : n.shown.size > 0 || n.skeletonState === "ready",
  ).length;
  const unavailable = selected.filter((n) =>
    settings.representation === "skeleton"
      ? n.skeletonState === "missing"
      : n.manifestState === "missing" || !!n.surfaceError,
  ).length;
  return {
    representation: settings.representation,
    source_geometry: settings.representation !== "mixed",
    status:
      settings.representation === "mixed"
        ? "unqualified"
        : unavailable ||
            stats.capacityHits ||
            fidelityState.status === "unsupported"
          ? "unsupported"
          : represented === selected.length
            ? "ready"
            : "loading",
    selected: selected.length,
    represented,
    unavailable,
    capacity_hits: stats.capacityHits,
    reasons: fidelityState.reasons,
    page_culling: settings.pageCulling,
    renderer_qualified: false,
    gpu_ready: pagedScene
      ? pagedScene.state === "ready" && pagedScene.complete
      : null,
  };
}
function resourceReport() {
  const arrays = [];
  world.traverse((o) => {
    if (o.geometry) arrays.push(...geometryArrays(o.geometry));
  });
  for (const n of neurons) {
    for (const f of n.shown.values())
      arrays.push(...geometryArrays(f.geometry));
    if (n.skelLod) {
      arrays.push(n.skelLod.vertices);
      arrays.push(...n.skelLod.levels);
      for (const p of n.skelLod.pages)
        arrays.push(p.edgePage, p.bounds, p.sizes, p.runs);
    }
  }
  for (const g of lru.values()) arrays.push(...geometryArrays(g));
  arrays.push(...geometryArrays(skelGeometry));
  if (residentGeometry) arrays.push(...geometryArrays(residentGeometry));
  arrays.push(...residentLines.arrays());
  return {
    managed_geometry_cpu_bytes: bufferBytes(arrays),
    decoded_cache_bytes: lruBytes,
    decoded_cache_limit_bytes: DECODED_CACHE_BYTES,
    gpu_total_bytes: null,
    gpu_resources: pagedScene?.report() ?? {
      state: "untracked",
      complete: false,
    },
    line_submission: pagedScene
      ? {
          mode: "immutable-pages",
          draws: pagedScene.pages.filter(
            (p) => p.layer === skeletonLayer && p.object.visible,
          ).length,
          submitted_indices: pagedScene.pages
            .filter((p) => p.layer === skeletonLayer && p.object.visible)
            .reduce((sum, p) => sum + p.object.geometry.index.count, 0),
        }
      : { ...lineSubmission },
    browser_heap_bytes: performance.memory?.usedJSHeapSize ?? null,
  };
}
function updateStats() {
  xrObserver?.refresh?.();
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
  if (fidelityReport().status === "ready") {
    perf.mark("all_represented");
  }
  if (pagedScene?.state === "ready") perf.mark("gpu_resources_ready");
  statsEl.textContent =
    `${surfaces} surfaces · ${lines} skeletons · ${(tris / 1e6).toFixed(1)} / ${settings.budgetM} M triangles` +
    ` · ${loading} loading · neuropils ${rois.filter((s) => s.mesh).length}/${rois.length}` +
    ` · ${settings.representation}: ${fidelityReport().status}` +
    (pagedScene ? ` · GPU: ${pagedScene.state}` : "") +
    (stats.capacityHits
      ? " · capacity exhausted; incomplete representation"
      : "") +
    (fidelityState.reasons.length
      ? ` · ${fidelityState.reasons[0].reason}`
      : "");
  perfEl.textContent = perf.line(renderer.getPixelRatio(), samples);
}
setInterval(updateStats, 500);

// ---------- replay ----------
const A = meta.activity;
const runSpikes = { a: actBuf ? new Uint8Array(actBuf) : null }; // bins x N
if (comparison) {
  runSpikes.b = new Uint8Array(actBufB);
  runSpikes.difference = difference(runSpikes.a, runSpikes.b);
}
const RUNS = ["a", "b", "difference"];
const startRun =
  comparison && RUNS.includes(query.get("run")) ? query.get("run") : "a";
let spikes = runSpikes[startRun];
// per neuron: more / less / same spikes in B than in A, or held by one export only
const compareClasses = comparison
  ? (() => {
      const shape = { n: N, bins: A.bins };
      const ta = totals(runSpikes.a, shape),
        tb = totals(runSpikes.b, shape);
      return neurons.map((n) =>
        compareClass(n.in[0], n.in[1], ta[n.k], tb[n.k]),
      );
    })()
  : null;
if (comparison) {
  view.compare = startRun === "difference" ? compareClasses : null;
  refreshColours();
  const banner = document.getElementById("compare");
  banner.hidden = false;
  banner.querySelector("pre").textContent = [
    ...runLines(comparison),
    `${comparison.dataset.name} ${comparison.dataset.release} · difference view: |A − B| per bin`,
    ...differenceLines(comparison),
  ].join("\n");
}
function showRun(run) {
  spikes = runSpikes[run];
  view.compare = run === "difference" ? compareClasses : null;
  refreshColours();
  shownT = null; // re-upload the glow
  if (selected) showRaster(selected.k, selected.entry);
  const url = new URL(location.href);
  url.searchParams.set("run", run);
  history.replaceState(null, "", url);
}
const clock = {
  t: Number(query.get("t")) || 0,
  playing:
    replay &&
    autoplay(
      location.search,
      matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
  speed: 40,
};
const clockEl = document.getElementById("clock");
let diagnosticContinuous = false;
let shownT = null; // replay time whose activity is on the GPU
function updateActivity(t) {
  activityAt(
    spikes,
    { n: N, bins: A.bins, binMs: A.bin_ms },
    t,
    activity,
    TAU_MS,
    HISTORY_BINS,
  );
  if (gradedSteps)
    gradedAt(
      gradedSteps,
      { k: meta.graded.k, bins: A.bins, binMs: A.bin_ms },
      t,
      activity,
    );
  for (let k = 0; k < N; k++) skelActivity.image.data[4 * k] = activity[k];
  skelActivity.needsUpdate = true;
  const inst = instanceActivity.image.data;
  for (const n of neurons)
    for (const f of n.shown.values()) inst[f.iid] = activity[n.k];
  instanceTexturesDirty = true;
  const label = `t = ${t.toFixed(0)} ms · stimulus ${t < A.stim_ms ? "on" : "off"}`;
  if (clockEl.textContent !== label) clockEl.textContent = label;
  shownT = t;
  drawRaster();
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

// The page layout removes per-fragment matrix/indirection fetches (all source
// fragment transforms are identity after worker finishing). It reads exactly
// the same neuron colour/activity values; images are qualified independently.
const pagedMeshMaterial = meshMaterial.clone();
pagedMeshMaterial.onBeforeCompile = (shader) => {
  Object.assign(shader.uniforms, shared, {
    uNeuronColor: { value: skelColour },
    uNeuronAct: { value: skelActivity },
  });
  shader.vertexShader = shader.vertexShader
    .replace(
      "#include <common>",
      `#include <common>
    attribute float aNeuron;
    uniform sampler2D uNeuronColor, uNeuronAct;
    varying float vActivity;
    varying vec3 vNeuronColor;`,
    )
    .replace(
      "#include <begin_vertex>",
      `#include <begin_vertex>
    ivec2 neuronPixel = ${neuronIndexGlsl};
    vActivity = texelFetch(uNeuronAct, neuronPixel, 0).r;
    vNeuronColor = texelFetch(uNeuronColor, neuronPixel, 0).rgb;`,
    );
  shader.fragmentShader = shader.fragmentShader
    .replace(
      "#include <common>",
      `#include <common>
    uniform float uGain, uInactiveAlpha;
    varying float vActivity;
    varying vec3 vNeuronColor;
    ${BAYER4}`,
    )
    .replace(
      "#include <color_fragment>",
      `#include <color_fragment>
    diffuseColor.rgb *= vNeuronColor;`,
    )
    .replace(
      "#include <clipping_planes_fragment>",
      `#include <clipping_planes_fragment>
    if (bayer4(gl_FragCoord.xy) >= mix(uInactiveAlpha, 1.0, clamp(4.0 * abs(vActivity), 0.0, 1.0))) discard;`,
    )
    .replace(
      "#include <emissivemap_fragment>",
      `#include <emissivemap_fragment>
    totalEmissiveRadiance += (vActivity >= 0.0 ? diffuseColor.rgb : ${HYPER_GLSL}) * abs(vActivity) * uGain;`,
    );
};
const pagedMeshId = pickLineMaterial.clone();
pagedMeshId.side = THREE.FrontSide;
const pageDepth = (material) => {
  const depth = material.clone();
  depth.fragmentShader = `#include <packing>
    void main() { gl_FragColor = packDepthToRGBA(gl_FragCoord.z); }`;
  return depth;
};
const surfaceLayer = {
  primitiveSize: 3,
  material: pagedMeshMaterial,
  neuron_id: pagedMeshId,
  packed_depth: pageDepth(pagedMeshId),
};
const skeletonLayer = {
  primitiveSize: 2,
  material: skelMaterial,
  neuron_id: pickLineMaterial,
  packed_depth: pageDepth(pickLineMaterial),
};
const contextLayers = new WeakMap();
const pagedScene = pagedEnabled
  ? new PagedScene(THREE, renderer, data, {
      maxPageBytes: gpuPageMiB * 1024 * 1024,
    })
  : null;
function originalObjects() {
  return data.children.filter((o) => o.geometry);
}
function diagnosticRender(draw) {
  if (!pagedScene) return draw();
  if (pagedScene.state !== "ready")
    throw new Error("Diagnostic requires ready GPU resources");
  return pagedScene.render(originalObjects(), draw);
}
function prepareOriginalOracle() {
  if (!pagedEnabled) return;
  // Only an explicit diagnostic allocates the legacy global arenas. Production
  // page preparation must not pay their unbounded CPU allocation/copy cost.
  for (const n of neurons)
    if (n.skelLod && !n.referenceSkeletonReady) {
      appendVertices(n, n.skelLod.vertices);
      n.referenceSkeletonReady = true;
    }
  if (!referenceSurfacesDirty) return;
  const entries = neurons
    .flatMap((n) => [...n.shown.values()].map((f) => ({ n, f })))
    .sort((a, b) => a.f.iid - b.f.iid);
  if (!entries.length) {
    referenceSurfacesDirty = false;
    return;
  }
  const next = new THREE.BatchedMesh(
    MAX_INSTANCES,
    capacity.vertices,
    capacity.indices,
    meshMaterial,
  );
  next.sortObjects = false;
  next.frustumCulled = false;
  const assigned = [],
    last = entries.at(-1).f.iid;
  let at = 0,
    firstGid = null,
    reservedFirstGid = null;
  try {
    for (let id = 0; id <= last; id++) {
      const entry = entries[at];
      if (entry?.f.iid === id) {
        const gid = reservedFirstGid ?? next.addGeometry(entry.f.geometry);
        reservedFirstGid = null;
        firstGid ??= gid;
        if (next.addInstance(gid) !== id)
          throw new Error("Reference instance order differs from source");
        next.setColorAt(id, new THREE.Color(colourOf(entry.n)));
        assigned.push([entry.f, gid]);
        at++;
      } else {
        // Reserve holes so texture IDs and original tie ownership stay exact.
        // If the first live slot is nonzero its geometry supplies hidden slots.
        if (firstGid === null) {
          firstGid = next.addGeometry(entries[0].f.geometry);
          reservedFirstGid = firstGid;
        }
        next.addInstance(firstGid);
        next.setVisibleAt(id, false);
      }
    }
  } catch (error) {
    next.dispose();
    throw error;
  }
  data.remove(batched);
  batched.dispose();
  batched = next;
  data.add(batched);
  for (const [fragment, gid] of assigned) fragment.gid = gid;
  referenceSurfacesDirty = false;
}
function syncPagedScene() {
  if (!pagedScene || !pagedInputsDirty) return;
  pagedInputsDirty = false;
  const sources = [];
  if (settings.representation === "skeleton") {
    for (const n of neurons)
      if (isShown(n) && n.skelLod)
        sources.push({
          key: `skeleton:${n.k}`,
          layer: skeletonLayer,
          attributes: {
            position: { array: n.skelLod.vertices, itemSize: 3 },
            aNeuron: { constant: n.k, itemSize: 1 },
          },
          index: n.skelLod.levels[0],
        });
  } else {
    const fragments = neurons
      .filter(isShown)
      .flatMap((n) => [...n.shown.entries()].map(([key, f]) => ({ n, key, f })))
      .sort((a, b) => a.f.iid - b.f.iid);
    for (const { n, key, f } of fragments)
      sources.push({
        key: `surface:${n.k}:${key}`,
        layer: surfaceLayer,
        attributes: {
          position: {
            array: f.geometry.attributes.position.array,
            itemSize: 3,
          },
          normal: { array: f.geometry.attributes.normal.array, itemSize: 3 },
          aNeuron: { constant: n.k, itemSize: 1 },
        },
        index: f.geometry.index.array,
      });
  }
  for (const o of originalObjects()) {
    if (o === batched || o === skeletons || !o.visible) continue;
    let layer = contextLayers.get(o);
    if (!layer) {
      layer = {
        primitiveSize: o.isPoints ? 1 : 3,
        material: o.material,
        renderOrder: o.renderOrder,
        context: true,
      };
      contextLayers.set(o, layer);
    }
    sources.push({
      key: `context:${o.id}`,
      layer,
      attributes: Object.fromEntries(
        Object.entries(o.geometry.attributes).map(([name, a]) => [
          name,
          { array: a.array, itemSize: a.itemSize },
        ]),
      ),
      index: o.geometry.index?.array ?? null,
    });
  }
  const fidelity = fidelityReport();
  const anatomyReady = fidelity.status === "ready";
  const contexts = Object.values(shells).filter((s) => s.visible);
  const contextsReady = contexts.every((s) => s.state === "ready");
  const contextError = contexts.find((s) => s.state === "error")?.error;
  pagedScene.sync(
    sources,
    anatomyReady && contextsReady,
    contextError ??
      (fidelity.status === "unsupported"
        ? "Selected source anatomy exceeds admission capacity or is unavailable"
        : null),
  );
}

function pickAt(x, y) {
  if (renderer.xr.isPresenting) return null; // the stereo cameras own the view in XR
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
  const somataShown = somata.points?.visible ?? false;
  if (somata.points) somata.points.visible = false; // context, not pickable
  batched.material = pickMeshMaterial;
  skeletons.material = [pickLineMaterial];
  renderer.setRenderTarget(pickTarget);
  renderer.setClearColor(0x000000, 0);
  renderer.clear();
  if (pagedScene)
    pagedScene.render(originalObjects(), () => renderer.render(world, camera), {
      pass: "neuron_id",
    });
  else renderer.render(world, camera);
  const px = new Uint8Array(4 * PICK * PICK);
  renderer.readRenderTargetPixels(pickTarget, 0, 0, PICK, PICK, px);
  renderer.setRenderTarget(null);
  batched.material = meshMaterial;
  skeletons.material = [skelMaterial];
  saved.shells.forEach((o) => (o.visible = true));
  if (somata.points) somata.points.visible = somataShown;
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
  window.flymsg = {
    THREE,
    neurons,
    renderer,
    composer,
    bloom,
    camera,
    world,
    data,
    skeletons,
    pickAt,
    pickTarget,
    pickMeshMaterial,
    meshMaterial,
    fidelity: fidelityReport,
    resources: resourceReport,
    paged: pagedScene,
    gpuInventory: () => pagedScene?.inventory(sha256) ?? null,
    renderScene: (c = camera) =>
      diagnosticRender(() => renderer.render(world, c)),
    renderDesktop: () => diagnosticRender(() => composer.render()),
    raster: () => rasterPainter.report(),
    scheduleLines: (eyes) => {
      prepareOriginalOracle();
      applySkeletonVisibility(eyes);
      return { ...lineSubmission };
    },
    diagnosticState: () => ({
      continuous: diagnosticContinuous,
      time: clock.t,
      playing: clock.playing,
      pageCulling: settings.pageCulling,
      residentLines: settings.residentLines,
    }),
    diagnostic({
      continuous = false,
      time = 0,
      playing = false,
      pageCulling = settings.pageCulling,
      residentLines = settings.residentLines,
    } = {}) {
      if (
        !Number.isFinite(time) ||
        time < 0 ||
        (replay && time >= A.bins * A.bin_ms)
      )
        throw new RangeError("Diagnostic timestamp outside scene");
      const previous = {
        continuous: diagnosticContinuous,
        time: clock.t,
        playing: clock.playing,
        pageCulling: settings.pageCulling,
        residentLines: settings.residentLines,
      };
      diagnosticContinuous = continuous;
      clock.playing = playing;
      clock.t = time;
      settings.pageCulling = pageCulling;
      settings.residentLines = residentLines;
      skeletonsDirty = true;
      invalidate();
      return previous;
    },
    async reference({
      width = 512,
      height = 512,
      time = 0,
      culling = false,
      projection = null,
      cameraWorld = null,
      pipeline = "original",
    } = {}) {
      if (renderer.xr.isPresenting || document.hidden)
        throw new Error("Reference requires a visible non-immersive page");
      if (!["original", "paged"].includes(pipeline))
        throw new Error("Unknown capture pipeline");
      if (pipeline === "paged" && pagedScene?.report().state !== "ready")
        throw new Error("Paged GPU resources are not ready");
      if (
        manifestQueue.size +
        fragmentQueue.size +
        skeletonQueue.size +
        roiQueue.size
      )
        throw new Error("Reference requires completed geometry loading");
      if (
        settings.representation !== "mixed" &&
        fidelityReport().status !== "ready"
      )
        throw new Error("Reference requires complete selected anatomy");
      if (
        !Number.isFinite(time) ||
        time < 0 ||
        (replay && time >= A.bins * A.bin_ms)
      )
        throw new RangeError("Reference replay timestamp outside scene");
      const saved = { playing: clock.playing, t: clock.t };
      prepareOriginalOracle();
      const objects = [];
      world.updateMatrixWorld(true);
      world.traverse((o) => {
        if (o.geometry && o.visible && !pagedScene?.group.children.includes(o))
          objects.push(o);
      });
      const materials = objects.map((o) => [o, o.material]);
      const depthFragment = `#include <packing>
        void main() { gl_FragColor = packDepthToRGBA(gl_FragCoord.z); }`;
      const depthMesh = pickMeshMaterial.clone();
      const depthLine = pickLineMaterial.clone();
      depthMesh.fragmentShader = depthLine.fragmentShader = depthFragment;
      const c = camera.clone();
      c.aspect = width / height;
      c.clearViewOffset();
      c.updateProjectionMatrix();
      if (projection) c.projectionMatrix.fromArray(projection);
      if (cameraWorld)
        c.matrix
          .fromArray(cameraWorld)
          .decompose(c.position, c.quaternion, c.scale);
      c.updateMatrixWorld(true);
      try {
        clock.playing = false;
        clock.t = time;
        if (replay) updateActivity(time);
        applySkeletonVisibility(
          culling ? skeletonEyes(c, width, height) : null,
        );
        flushInstanceTextures();
        const geometry = geometryInventory(objects);
        const replace = (mesh, line) => () => {
          const context = objects.filter(
            (o) => o !== batched && o !== skeletons,
          );
          context.forEach((o) => {
            o.visible = false;
          });
          batched.material = mesh;
          skeletons.material = [line];
          const background = world.background;
          world.background = null;
          renderer.setClearColor(0, 0);
          return () => {
            materials.forEach(([o, material]) => {
              o.material = material;
            });
            context.forEach((o) => {
              o.visible = true;
            });
            world.background = background;
          };
        };
        const buffers = capturePasses(
          THREE,
          renderer,
          world,
          c,
          {
            colour: () => () => {},
            neuron_id: replace(pickMeshMaterial, pickLineMaterial),
            packed_depth: replace(depthMesh, depthLine),
          },
          width,
          height,
          pipeline === "paged"
            ? (pass) =>
                pagedScene.render(
                  originalObjects(),
                  () => renderer.render(world, c),
                  {
                    pass,
                    eyes: culling ? skeletonEyes(c, width, height) : null,
                  },
                )
            : undefined,
        );
        const activityCopy = activity.slice();
        return {
          schema: "flymsg.render-reference/v1",
          pipeline,
          page_culling: culling,
          width,
          height,
          time_ms: time,
          pixel_format:
            "RGBA8 bottom-left origin; depth = three.js packDepthToRGBA",
          colour_pipeline: "direct scene render; no desktop compositor",
          depth_policy:
            "opaque geometry depth; ID/depth exclude contextual shells and somata",
          projection: c.projectionMatrix.toArray(),
          camera_world: c.matrixWorld.toArray(),
          data_world: data.matrixWorld.toArray(),
          settings: { ...settings },
          scene_sha256: await sha256(
            new TextEncoder().encode(JSON.stringify(meta)),
          ),
          activity_sha256: await sha256(activityCopy),
          geometry: await geometry,
          neurons: neurons.filter(isShown).map((n) => ({
            bodyId: n.bodyId,
            k: n.k,
            surfaces: [...n.shown.keys()],
            skeleton_level: n.skelLod?.level ?? null,
          })),
          images: Object.fromEntries(
            await Promise.all(
              Object.entries(buffers).map(async ([key, bytes]) => [
                key,
                { sha256: await sha256(bytes), base64: base64(bytes) },
              ]),
            ),
          ),
        };
      } finally {
        clock.playing = saved.playing;
        clock.t = saved.t;
        if (replay) updateActivity(saved.t);
        depthMesh.dispose();
        depthLine.dispose();
        skeletonsDirty = true;
        invalidate();
      }
    },
    get batched() {
      return batched;
    },
  };
}
const info = document.getElementById("info");
info.textContent = tv ? padHint() : hint(coarse);
let downAt = null;
renderer.domElement.addEventListener(
  "pointerdown",
  (e) => (downAt = [e.clientX, e.clientY]),
);
renderer.domElement.addEventListener("pointerup", (e) => {
  if (
    !downAt ||
    !isTap(e.pointerType, e.clientX - downAt[0], e.clientY - downAt[1])
  )
    return; // a drag
  const rect = renderer.domElement.getBoundingClientRect();
  const k = pickAt(e.clientX - rect.left, e.clientY - rect.top);
  if (query.has("check"))
    console.log(
      `PICK ${e.clientX},${e.clientY} -> ${k === null ? "none" : neurons[k].bodyId}`,
    );
  if (k === null) return;
  const n = neurons[k];
  const lods = [
    ...new Set([...n.shown.keys()].map((key) => key.split(":")[0])),
  ].sort();
  info.classList.remove("muted");
  info.textContent = `${n.instance || n.type} · ${
    n.shown.size ? `surface, LOD ${lods.join("/")}` : "skeleton"
  } · ${clearHint(coarse)}`;
  selectNeuron(k);
});

// ---------- selection: partners from partners.json, loaded on first use ----------
const panel = document.getElementById("selection");
let partnerTable = null;
let selected = null; // {k, entry}, so a run switch can redraw the raster
const loadPartners = () =>
  (partnerTable ??= fetch("partners.json")
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null));

async function selectNeuron(k) {
  const n = neurons[k];
  const table = await loadPartners();
  const entry = table?.neurons?.[String(n.bodyId)];
  view.focus = focusRoles(k, entry);
  refreshColours();
  invalidate();
  showRaster(k, entry);
  panel.hidden = false;
  selected = { k, entry };
  const extra = comparison
    ? neuronLines(n, k, {
        spikesA: runSpikes.a,
        spikesB: runSpikes.b,
        shape: { n: N, bins: A.bins },
        binMs: A.bin_ms,
        labels: comparison.runs.map((r) => r.label),
      })
    : [];
  panel.querySelector("pre").textContent = [
    ...panelLines(n, entry, table?.source),
    ...extra,
  ].join("\n");
  const url = new URL(location.href);
  url.searchParams.set("select", String(n.bodyId));
  history.replaceState(null, "", url);
}

function clearSelection() {
  if (!view.focus) return;
  selected = null;
  view.focus = null;
  refreshColours();
  invalidate();
  panel.hidden = true;
  hideRaster();
  const url = new URL(location.href);
  url.searchParams.delete("select");
  history.replaceState(null, "", url);
}

function find(text) {
  const hit = findNeuron(neurons, text);
  if (hit) return selectNeuron(hit.k);
  panel.hidden = false;
  panel.querySelector("pre").textContent =
    `no neuron in this scene matches "${text}"`;
}

panel.querySelector("button").addEventListener("click", clearSelection);

// ---------- raster: the selection's spikes per bin, in step with the replay ----------
const rasterEl = document.getElementById("raster");
const rasterCanvas = rasterEl.querySelector("canvas");
const RASTER_LABEL_PX = 120;
const rasterPainter = new RasterPainter(rasterCanvas);
let rasterState = null;
function showRaster(k, entry) {
  if (!replay) return;
  const { rows, hidden } = selectionRows(k, entry);
  rasterState = {
    rows: rasterRows(spikes, { n: N, bins: A.bins }, rows).map((row) => ({
      ...row,
      label: (neurons[row.k].instance || neurons[row.k].type).slice(0, 18),
      colour: FOCUS_COLORS[view.focus?.get(row.k) ?? "context"],
    })),
    bins: A.bins,
    binMs: A.bin_ms,
    stimMs: A.stim_ms,
    hidden,
  };
  rasterEl.querySelector("header span").textContent =
    `spikes per ${A.bin_ms} ms bin (model replay) · drag to move in time${
      coarse ? "" : " · ← → step one bin"
    }`;
  rasterEl.querySelector(".more").textContent = hidden
    ? `${hidden} more partners in the scene are not shown`
    : "";
  rasterEl.hidden = false;
  drawRaster();
}
function hideRaster() {
  rasterState = null;
  rasterPainter.clear();
  rasterEl.hidden = true;
}
const rasterSpanMs = () => A.bins * A.bin_ms;
function rasterX(ms, width) {
  return (
    RASTER_LABEL_PX + (ms / rasterSpanMs()) * (width - RASTER_LABEL_PX - 4)
  );
}
function drawRaster() {
  if (!rasterState) return;
  rasterPainter.draw(rasterState, {
    width: Math.min(560, innerWidth - 48),
    ratio: devicePixelRatio || 1,
    time: clock.t,
  });
}
function rasterTime(e) {
  const r = rasterCanvas.getBoundingClientRect();
  const frac =
    (e.clientX - r.left - RASTER_LABEL_PX) / (r.width - RASTER_LABEL_PX - 4);
  return Math.max(0, Math.min(rasterSpanMs() - 1, frac * rasterSpanMs()));
}
let scrubbing = false;
rasterCanvas.addEventListener("pointerdown", (e) => {
  clock.playing = false;
  clock.t = rasterTime(e);
  scrubbing = true;
  try {
    rasterCanvas.setPointerCapture(e.pointerId); // keep the drag when it leaves the panel
  } catch {
    // a pointer that is not active (synthetic events) cannot be captured; the click still counts
  }
});
rasterCanvas.addEventListener("pointermove", (e) => {
  if (scrubbing) clock.t = rasterTime(e);
});
rasterCanvas.addEventListener("pointerup", () => (scrubbing = false));
// one bin back or forward, paused: the arrow keys, and LB/RB on a controller
function stepBin(step) {
  clock.playing = false;
  const b = binAt(clock.t, A.bin_ms, A.bins) + step;
  clock.t = Math.max(0, Math.min(A.bins - 1, b)) * A.bin_ms; // the start of that bin
}
addEventListener("keydown", (e) => {
  if (!rasterState || e.target.closest?.("input")) return;
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  stepBin(e.key === "ArrowRight" ? 1 : -1);
});
addEventListener("resize", drawRaster);
rasterCanvas.addEventListener("contextrestored", () => {
  rasterPainter.clear();
  drawRaster();
});
rasterEl.querySelector("button").addEventListener("click", async () => {
  const manifest = await fetch("manifest.json")
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  const doc = selectionExport({
    neurons,
    rows: rasterState.rows,
    activity: A,
    t: clock.t,
    manifest,
  });
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(doc, null, 1)], { type: "application/json" }),
  );
  const link = Object.assign(document.createElement("a"), {
    href: url,
    download: `flymsg-selection-${neurons[rasterState.rows[0].k].bodyId}.json`,
  });
  link.click();
  URL.revokeObjectURL(url);
});
addEventListener("keydown", (e) => {
  if (e.key === "Escape") clearSelection();
});
const initial = selectParam(location.search);
if (initial) find(initial);

// ---------- GUI ----------
// ?chrome=0 is a gallery frame: the panel is not built, and the performance
// readout is hidden. The colour legend stays.
applyChrome(
  {
    stats: document.getElementById("stats"),
    perf: document.getElementById("perf"),
  },
  location.search,
);
let guiPanel = null; // the lil-gui panel, which the controller's View button opens and closes
if (showChrome(location.search)) {
  const gui = new GUI({ title: "flymsg" });
  gui
    .add(settings, "representation", {
      "full surfaces": "surface",
      "full skeletons": "skeleton",
    })
    .name("anatomy")
    .onChange((value) => {
      const url = new URL(location.href);
      url.searchParams.set("representation", value);
      location.assign(url);
    });
  guiPanel = gui;
  // the open panel would cover the scene on a phone, and wants a pointer on a TV
  if (matchMedia(NARROW).matches || tv) gui.close();
  gui
    .add(view, "colorBy", COLOR_MODES)
    .name("colour by")
    .onChange(refreshColours);
  gui
    .add({ find: "" }, "find")
    .name("select (bodyId/type)")
    .onFinishChange((v) => v.trim() && find(v));
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
      stats.capacityHits = 0;
      makeBatched();
      selectionDirty = true;
    });
  if (settings.representation === "mixed")
    gui
      .add(settings, "adaptive")
      .name("adaptive quality")
      .onChange((on) => on || setQuality(nativeRatio, MSAA));
  if (replay) {
    gui.add(bloom, "strength", 0, 3).name("bloom").onChange(invalidate);
    gui
      .add(shared.uInactiveAlpha, "value", 0.05, 1, 0.05)
      .name("silent surfaces")
      .onChange(invalidate);
  }
  const gFolder = gui.addFolder("Groups");
  groups.forEach((g) =>
    gFolder.add(view.groupsOn, g).onChange(() => {
      selectionDirty = true;
      refreshColours();
    }),
  );
  somataLoaded.then(() => {
    if (!somata.points) return;
    const f = gui
      .addFolder(`Whole CNS (${somata.count.toLocaleString()} somata)`)
      .close();
    f.add(somata.points, "visible")
      .name("show")
      .onChange(() => {
        pagedInputsDirty = true;
        renderLegend();
        invalidate();
      });
    f.add(somataMaterial, "opacity", 0, 1).onChange(invalidate);
    f.add(somataMaterial, "size", 0.5, 6).name("point px").onChange(invalidate);
  });
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
        pagedInputsDirty = true;
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
    if (comparison) {
      const labels = comparison.runs.map((r) => r.label);
      rFolder
        .add({ run: startRun }, "run", {
          [`A ${labels[0]}`]: "a",
          [`B ${labels[1]}`]: "b",
          "difference |A − B|": "difference",
        })
        .name("run")
        .onChange(showRun);
    }
    rFolder.add(clock, "playing");
    rFolder.add(clock, "speed", 5, 200).name("speed (sim ms / s)");
    rFolder
      .add(clock, "t", 0, A.bins * A.bin_ms - 1, 1)
      .name("time (ms)")
      .listen();
  }
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
  if (n !== samples) {
    msaaTarget.samples = n;
    msaaTarget.dispose(); // recreated with the new sample count on next use
  }
  [ratio, samples] = [r, n];
  renderer.setPixelRatio(r);
  composer.setPixelRatio(r);
  tuneFrames = 0; // wait for frames measured at the new quality
  invalidate();
}
const scaled = (frameMs) => scaledRatio(ratio, frameMs, TARGET_FRAME_MS);
function tuneQuality(live) {
  if (!settings.adaptive) return;
  if (!live) {
    floorRatio = MIN_RATIO;
    lastStep = null;
    setQuality(nativeRatio, MSAA);
    return;
  }
  if (++tuneFrames < 12) return;
  const frameMs = perf.recentGpuMs(8) ?? perf.recentFrameMs(8);
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
    if (ratio < nativeRatio)
      setQuality(Math.min(nativeRatio, scaled(frameMs)), 0);
    else if (!samples && 2 * frameMs < TARGET_FRAME_MS * 0.9)
      setQuality(ratio, MSAA); // fits even doubled
  }
}

// ---------- camera, resize, loop ----------
const extent = Math.max(...volumeUm);
// The volume is centered on the origin. A fixed far of 50 mm put the whole CNS in the last
// fraction of the depth range (near 0.5), so surfaces and skeletons z-fought. Every point of
// the volume lies between |camera| ± radius, whatever the camera is aimed at.
const sceneRadius = 0.5 * Math.hypot(...volumeUm) * 1.15;
function fitClip() {
  const dist = camera.position.length();
  camera.near = Math.max(0.05, dist - sceneRadius);
  camera.far = Math.max(dist + sceneRadius, camera.near + 1);
  camera.updateProjectionMatrix();
}
camera.position.set(extent * 0.7, extent * 0.25, extent * 0.55); // oblique: brain and VNC both visible
controls.target.set(0, 0, 0);
controls.update();
fitClip();
const home = camera.position.clone(); // the controller's Y returns here

// ---------- game controller ----------
// Polled each frame (the Gamepad API has no events for axes). The left stick orbits the
// target, the right stick and triggers zoom, and the buttons act on their press only.
let padButtons = null;
const orbit = new THREE.Spherical();
function steerWithPad(dt) {
  const pad = [...(navigator.getGamepads?.() ?? [])].find(
    (p) => p && p.mapping === "standard",
  );
  if (!pad) return false;
  const { now, fresh } = pressedSince(pad, padButtons);
  padButtons = now;
  if (fresh.has(BUTTON.A) && replay) clock.playing = !clock.playing;
  if (fresh.has(BUTTON.LB) && replay) stepBin(-1);
  if (fresh.has(BUTTON.RB) && replay) stepBin(1);
  if (fresh.has(BUTTON.X)) clearSelection();
  if (fresh.has(BUTTON.VIEW) && guiPanel) guiPanel.open(guiPanel._closed);
  if (fresh.has(BUTTON.Y)) {
    camera.position.copy(home);
    controls.target.set(0, 0, 0);
    camera.lookAt(controls.target);
    return true;
  }
  const m = motion(pad, dt);
  if (m.theta === 0 && m.phi === 0 && m.zoom === 1) return false;
  const offset = camera.position.clone().sub(controls.target);
  orbit.setFromVector3(offset);
  orbit.theta += m.theta;
  orbit.phi = Math.min(Math.PI - 1e-3, Math.max(1e-3, orbit.phi + m.phi));
  orbit.radius = Math.min(
    controls.maxDistance,
    Math.max(controls.minDistance, orbit.radius * m.zoom),
  );
  camera.position.copy(controls.target).add(offset.setFromSpherical(orbit));
  camera.lookAt(controls.target);
  return true;
}

addEventListener("resize", () => {
  if (renderer.xr.isPresenting) return; // XR runtime owns the stereo framebuffer size
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  renderer.setScissor(0, 0, innerWidth, innerHeight);
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
          effective_budget: Math.round(
            effectiveBudget(stats, capacity, settings.budgetM),
          ),
          verts_per_tri: +vertsPerTri(stats).toFixed(3),
          tris_per_byte: +trisPerByte(stats).toFixed(3),
          ...capacity,
        },
      });
      console.log(`BENCH ${JSON.stringify(summary)}`);
    },
    1000 * Number(query.get("bench")),
  );
}

// Mobile browsers drop the WebGL context under memory pressure or in a background tab.
// preventDefault asks for it back; three.js re-uploads every resource on restore.
const lostEl = document.getElementById("lost");
const xrMetrics = new XrMetrics(
  {
    url: location.href,
    user_agent: navigator.userAgent,
    scene_schema: meta.schema,
  },
  (record) => {
    console.log(`XR_BENCH ${JSON.stringify(record)}`);
    if (query.get("xrcollect") === "1")
      fetch("/__xr_evidence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(record),
      })
        .then((response) => {
          if (!response.ok)
            throw new Error(`collector HTTP ${response.status}`);
        })
        .catch((error) => console.warn("XR evidence delivery failed", error));
  },
);
if (query.get("xr") === "1") {
  // Read-only snapshot for the hardware collector; no control over scientific state.
  window.flymsgXrReport = () => xrMetrics.report();
  renderer.xr.addEventListener("sessionstart", () => {
    perf.resetContext();
    xrMetrics.start(renderer.xr.getSession());
  });
  window.addEventListener("pagehide", () => xrMetrics.finish("pagehide"));
}
renderer.domElement.addEventListener("webglcontextlost", (e) => {
  e.preventDefault();
  lostEl.hidden = false;
  pagedScene?.contextLost();
  xrMetrics.event("webglcontextlost");
});
renderer.domElement.addEventListener("webglcontextrestored", () => {
  lostEl.hidden = true;
  pagedScene?.contextRestored();
  pagedInputsDirty = true;
  xrMetrics.event("webglcontextrestored");
  perf.resetContext();
  selectionDirty = true;
  invalidate();
});

// A hidden tab pauses requestAnimationFrame. The time away is not replay time: restart the
// frame clock when the tab is shown, so the first frame back does not jump.
const timer = new THREE.Clock();
document.addEventListener("visibilitychange", () => {
  perf.last = null;
  perf.wasContinuous = false;
  if (!document.hidden) timer.getDelta();
});
renderer.setAnimationLoop((timestamp) => {
  const frameStart = performance.now();
  const dt = timer.getDelta();
  const inXR = renderer.xr.isPresenting;
  const steered = inXR ? false : steerWithPad(dt);
  const moved = inXR ? false : controls.update() || steered; // XR headset owns its camera pose
  if (inXR) {
    // head motion moves the camera without OrbitControls events: refine as the view
    // changes, at the selection's own rate
    selectionDirty = true;
    lastMove = performance.now();
  }
  const playing = replay && clock.playing;
  if (playing) clock.t = (clock.t + dt * clock.speed) % (A.bins * A.bin_ms);
  if (replay && clock.t !== shownT) updateActivity(clock.t);
  const live = inXR || interacting || moved || playing || diagnosticContinuous;
  if (!inXR) tuneQuality(live); // desktop adaptive compositor is not XR-qualified
  const now = performance.now();
  // the index rebuild walks every drawn segment: coalesce streaming updates
  if (!inXR) fitClip();
  if (settings.pageCulling && inXR) renderer.xr.updateCamera(camera);
  if (
    !pagedScene &&
    (settings.pageCulling ||
      (skeletonsDirty && now - lastSkeletonBuild >= IDLE_REDRAW_MS))
  ) {
    applySkeletonVisibility(
      settings.pageCulling
        ? skeletonEyes(inXR ? renderer.xr.getCamera() : camera)
        : null,
    );
    lastSkeletonBuild = now;
  }
  if (pagedScene) {
    const wasReady = pagedScene.state === "ready";
    syncPagedScene();
    pagedScene.tick();
    if (!wasReady || pagedScene.state !== "ready") invalidate();
    xrObserver?.refresh?.();
  }
  if (!live && !(sceneDirty && now - lastRender >= IDLE_REDRAW_MS)) return;
  flushInstanceTextures();
  perf.begin(frameStart); // include activity, visibility, index preparation and uploads
  const draw = () => {
    if (inXR) {
      // Three.js supplies the two eye cameras; never run desktop postprocessing
      // against the XR framebuffer. One existing animation loop owns both modes.
      renderer.render(world, camera);
    } else {
      composer.render();
    }
  };
  if (pagedScene)
    pagedScene.render(originalObjects(), draw, {
      eyes: settings.pageCulling
        ? skeletonEyes(inXR ? renderer.xr.getCamera() : camera)
        : null,
    });
  else draw();
  const measured = perf.end({ continuous: live });
  if (inXR)
    xrMetrics.frame(
      timestamp,
      performance.now() - frameStart,
      measured.gpu_ms,
      () => ({
        geometries: renderer.info.memory.geometries,
        textures: renderer.info.memory.textures,
        programs: renderer.info.programs?.length ?? null,
        triangles: renderer.info.render.triangles,
        draws: renderer.info.render.calls,
        lines: renderer.info.render.lines,
        fidelity: fidelityReport(),
        ...resourceReport(),
      }),
      fidelityReport(),
    );
  sceneDirty = false;
  lastRender = now;
});

// ?xr=1 with the chrome shown: installed after the loop starts, so a slow XR runtime never
// delays the first frame. The observer transforms only the presentation root; neural
// activity, manifests, scientific frames and simulation state are untouched.
const xrOptions = {
  search: location.search,
  renderer,
  root,
  camera,
  controls,
  extentUm: extent,
  entryError: () => {
    const fidelity = fidelityReport();
    if (pagedScene && pagedScene.report().state !== "ready")
      return `GPU resources are ${pagedScene.report().state}. VR requires completed uploads.`;
    return fidelity.status === "ready" ||
      (settings.representation === "mixed" && query.has("check"))
      ? null
      : `Selected anatomy is ${fidelity.status}. VR requires a complete representation.`;
  },
  onTransition: () => {
    selectionDirty = true;
    invalidate();
    if (!renderer.xr.isPresenting) {
      perf.resetContext();
      // the desktop may have been resized while the headset owned its framebuffer
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
      renderer.setScissor(0, 0, innerWidth, innerHeight);
      composer.setSize(innerWidth, innerHeight);
    }
  },
};
let xrObserver = null;
if (showChrome(location.search))
  installXrObserver(xrOptions)
    .then((observer) => {
      xrObserver = observer;
    })
    .catch((error) => console.warn("XR observer not installed:", error));
