// flymsg 3D viewer: skeletons + neuropil shells, optional replay of simulated spikes.
// Data files are written by `flymsg viz` next to this page (see src/flymsg/viz.py).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import GUI from "lil-gui";

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
const TEX_W = 1024; // per-neuron data lives in TEX_W-wide float textures
const TAU_MS = 15; // display decay of a spike's glow
const HISTORY_BINS = 5;

// ---------- load ----------
const fetchBin = async (name) => {
  const r = await fetch(name);
  return r.ok ? r.arrayBuffer() : null;
};
const meta = await (await fetch("scene.json")).json();
const [skelBuf, pilBuf, actBuf] = await Promise.all([
  fetchBin("skeletons.bin"),
  meta.neuropils.length ? fetchBin("neuropils.bin") : null,
  meta.activity ? fetchBin("activity.bin") : null,
]);
document.getElementById("loading").remove();

// ---------- renderer ----------
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);

const world = new THREE.Scene();
world.background = new THREE.Color("#05070a");
const root = new THREE.Group();
root.rotation.x = Math.PI; // EM y grows ventrally; a rotation (not a mirror) puts dorsal up
world.add(root);

const camera = new THREE.PerspectiveCamera(
  40,
  innerWidth / innerHeight,
  1,
  50000,
);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(world, camera));
const bloom = new UnrealBloomPass(
  new THREE.Vector2(innerWidth, innerHeight),
  meta.activity ? 0.6 : 1.2, // many neurons light up at once in a replay: keep the glow local
  0.5,
  0.15, // threshold keeps the dim shells out of the glow
);
composer.addPass(bloom);
composer.addPass(new OutputPass());

// ---------- neurons ----------
const N = meta.neurons.length;
const owner = new Float32Array(meta.vertices);
meta.neurons.forEach((n, k) => owner.fill(k, n.v0, n.v0 + n.nv));
const neuronGeo = new THREE.BufferGeometry();
neuronGeo.setAttribute(
  "position",
  new THREE.BufferAttribute(new Float32Array(skelBuf, 0, meta.vertices * 3), 3),
);
neuronGeo.setAttribute("aNeuron", new THREE.BufferAttribute(owner, 1));
neuronGeo.setIndex(
  new THREE.BufferAttribute(
    new Uint32Array(skelBuf, meta.vertices * 12, meta.edges * 2),
    1,
  ),
);

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
const colorTex = makeTex(); // rgb = colour, a = visible
const actTex = makeTex(); // r = activity 0..1

const replay = Boolean(meta.activity);
const neuronMat = new THREE.ShaderMaterial({
  uniforms: {
    uColor: { value: colorTex },
    uAct: { value: actTex },
    uBase: { value: replay ? 0.05 : 1.0 },
    uGain: { value: replay ? 1.3 : 0.0 },
    uBright: { value: 1.0 },
    uAlpha: { value: 0.6 },
  },
  vertexShader: /* glsl */ `
    attribute float aNeuron;
    uniform sampler2D uColor;
    uniform sampler2D uAct;
    uniform float uBase, uGain, uBright;
    varying vec3 vColor;
    void main() {
      ivec2 p = ivec2(int(mod(aNeuron, ${TEX_W}.0)), int(aNeuron / ${TEX_W}.0));
      vec4 c = texelFetch(uColor, p, 0);
      float a = texelFetch(uAct, p, 0).r;
      vColor = c.rgb * uBright * (uBase + uGain * a);
      // hidden neurons are pushed outside the clip volume
      gl_Position = c.a > 0.5 ? projectionMatrix * modelViewMatrix * vec4(position, 1.0) : vec4(2.0, 2.0, 2.0, 1.0);
    }`,
  fragmentShader: /* glsl */ `
    uniform float uAlpha;
    varying vec3 vColor;
    void main() { gl_FragColor = vec4(vColor, uAlpha); }`,
  // normal (not additive) blending: overlapping neurons must not sum to white; only
  // active neurons exceed 1.0 and pass the bloom threshold
  transparent: true,
  depthWrite: false,
});
const lines = new THREE.LineSegments(neuronGeo, neuronMat);
root.add(lines);

// ---------- neuropils ----------
const shellMat = new THREE.ShaderMaterial({
  uniforms: {
    uOpacity: { value: 0.18 },
    uColor: { value: new THREE.Color("#5b6b82") },
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
const shells = new THREE.Group();
root.add(shells);
const shellMeshes = {};
if (pilBuf) {
  const nv = meta.neuropils.reduce((s, p) => s + p.nv, 0);
  const pos = new Float32Array(pilBuf, 0, nv * 3);
  const tris = new Uint32Array(pilBuf, nv * 12);
  for (const p of meta.neuropils) {
    const g = new THREE.BufferGeometry();
    g.setAttribute(
      "position",
      new THREE.BufferAttribute(pos.subarray(p.v0 * 3, (p.v0 + p.nv) * 3), 3),
    );
    g.setIndex(
      new THREE.BufferAttribute(
        tris.subarray(p.t0 * 3, (p.t0 + p.nt) * 3).map((i) => i - p.v0),
        1,
      ),
    );
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, shellMat);
    m.renderOrder = -1;
    shells.add(m);
    shellMeshes[p.name] = m;
  }
}

// ---------- colours, visibility, legend ----------
const groups = [...new Set(meta.neurons.map((n) => n.group))];
const hash = (s) =>
  [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
const state = {
  colorBy: "group",
  filter: "",
  groupsOn: Object.fromEntries(groups.map((g) => [g, true])),
};
const colourOf = (n) =>
  state.colorBy === "group"
    ? PALETTE[groups.indexOf(n.group) % PALETTE.length]
    : state.colorBy === "transmitter"
      ? (NT_COLORS[n.nt] ?? NT_COLORS.unknown)
      : PALETTE[hash(n.type) % PALETTE.length];
const isVisible = (n) =>
  state.groupsOn[n.group] &&
  (!state.filter || n.type.toLowerCase().includes(state.filter));

function refreshColours() {
  const c = new THREE.Color();
  meta.neurons.forEach((n, k) => {
    c.set(colourOf(n));
    colorTex.image.data.set([c.r, c.g, c.b, isVisible(n) ? 1 : 0], k * 4);
  });
  colorTex.needsUpdate = true;
  const entries =
    state.colorBy === "group"
      ? groups.map((g, i) => [g, PALETTE[i % PALETTE.length]])
      : state.colorBy === "transmitter"
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

// ---------- replay ----------
const A = meta.activity;
const spikes = actBuf ? new Uint8Array(actBuf) : null; // bins x N, bin-major
// ?t=<ms>&paused opens the replay at a given moment (handy for sharing and screenshots)
const query = new URLSearchParams(location.search);
const clock = { t: Number(query.get("t")) || 0, playing: replay && !query.has("paused"), speed: 40 };
const clockEl = document.getElementById("clock");

function updateActivity(t) {
  const b = Math.min(Math.floor(t / A.bin_ms), A.bins - 1);
  const data = actTex.image.data;
  for (let k = 0; k < N; k++) {
    let s = 0;
    for (let j = Math.max(0, b - HISTORY_BINS + 1); j <= b; j++) {
      const n = spikes[j * N + k];
      if (n) s += n * Math.exp(-Math.max(0, t - (j + 0.5) * A.bin_ms) / TAU_MS);
    }
    data[k * 4] = Math.min(1, 0.5 * s);
  }
  actTex.needsUpdate = true;
  clockEl.textContent = `t = ${t.toFixed(0)} ms · stimulus ${t < A.stim_ms ? "on" : "off"}`;
}

// ---------- picking ----------
const raycaster = new THREE.Raycaster();
raycaster.params.Line.threshold = 1.5; // um
const info = document.getElementById("info");
let downAt = null;
renderer.domElement.addEventListener(
  "pointerdown",
  (e) => (downAt = [e.clientX, e.clientY]),
);
renderer.domElement.addEventListener("pointerup", (e) => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4)
    return; // a drag, not a click
  const ndc = new THREE.Vector2(
    (e.clientX / innerWidth) * 2 - 1,
    -(e.clientY / innerHeight) * 2 + 1,
  );
  raycaster.setFromCamera(ndc, camera);
  const hit = raycaster
    .intersectObject(lines)
    .find((h) => isVisible(meta.neurons[owner[h.index]]));
  if (!hit) return;
  const n = meta.neurons[owner[hit.index]];
  info.classList.remove("muted");
  info.textContent = [
    n.instance || n.type,
    `bodyId ${n.bodyId}`,
    n.nt,
    n.superclass,
    `group ${n.group}`,
    n.rate == null ? null : `${n.rate} Hz during stimulus`,
  ]
    .filter(Boolean)
    .join(" · ");
});

// ---------- GUI ----------
const gui = new GUI({ title: "flymsg" });
gui
  .add(state, "colorBy", ["group", "transmitter", "type"])
  .name("colour by")
  .onChange(refreshColours);
gui
  .add(state, "filter")
  .name("type filter")
  .onChange((v) => {
    state.filter = v.toLowerCase();
    refreshColours();
  });
gui.add(neuronMat.uniforms.uBright, "value", 0.1, 3).name("neuron brightness");
gui.add(bloom, "strength", 0, 3).name("bloom");
const gFolder = gui.addFolder("Groups");
groups.forEach((g) => gFolder.add(state.groupsOn, g).onChange(refreshColours));
if (pilBuf) {
  const pFolder = gui.addFolder("Neuropils");
  pFolder.add(shellMat.uniforms.uOpacity, "value", 0, 1).name("opacity");
  for (const region of ["brain", "vnc"]) {
    const names = meta.neuropils
      .filter((p) => p.region === region)
      .map((p) => p.name);
    if (!names.length) continue;
    const f = pFolder.addFolder(region).close();
    const all = { all: true };
    const boxes = {};
    const toggles = Object.fromEntries(names.map((n) => [n, true]));
    f.add(all, "all").onChange((v) =>
      names.forEach((n) => {
        toggles[n] = v;
        shellMeshes[n].visible = v;
        boxes[n].updateDisplay();
      }),
    );
    names.forEach(
      (n) =>
        (boxes[n] = f
          .add(toggles, n)
          .onChange((v) => (shellMeshes[n].visible = v))),
    );
  }
}
if (replay) {
  const rFolder = gui.addFolder("Replay");
  rFolder.add(clock, "playing");
  rFolder.add(clock, "speed", 5, 200).name("speed (sim ms / s)");
  rFolder
    .add(clock, "t", 0, A.bins * A.bin_ms - 1, 1)
    .name("time (ms)")
    .listen();
}

// ---------- camera fit, resize, loop ----------
const box = new THREE.Box3().setFromObject(pilBuf ? shells : lines);
const centre = box.getCenter(new THREE.Vector3());
const size = box.getSize(new THREE.Vector3()).length();
// oblique view so the brain and the ventral nerve cord are both visible
camera.position.copy(centre).add(new THREE.Vector3(size * 0.75, size * 0.25, size * 0.6));
controls.target.copy(centre);
controls.update();

addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  composer.setSize(innerWidth, innerHeight);
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
});
