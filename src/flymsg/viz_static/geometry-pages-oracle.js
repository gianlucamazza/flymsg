// Independent raster oracle: reference renders ORIGINAL indices, without any page
// selection. Synthetic geometry exercises clipping, stereo and equal-depth ties.
// Diagnostic only; never imported by the production viewer.
import {
  linePages,
  visibleLinePages,
  writeVisibleEdges,
} from "./geometry-pages.js";
import { localEyePlanes } from "./page-views.js";
import { capturePasses, sha256 } from "./render-reference.js";
import { ResidentLineIndex } from "./resident-lines.js";

export async function geometryPageOracle(THREE) {
  const renderer = new THREE.WebGLRenderer();
  renderer.setSize(192, 128);
  const world = new THREE.Scene();
  world.background = new THREE.Color(0x05070a);
  const root = new THREE.Group();
  root.rotation.z = 0.19;
  root.scale.set(1.1, 0.9, 1);
  world.add(root);
  let seed = 281;
  const rand = () => (seed = (1664525 * seed + 1013904223) >>> 0) / 2 ** 32;
  const vertices = [],
    ids = [],
    edges = [];
  for (let y = -4; y <= 4; y++)
    for (let x = -4; x <= 4; x++)
      for (let j = 0; j < 24; j++) {
        const base = vertices.length / 3,
          id = 1 + ((x + 4 + 9 * (y + 4)) % 251);
        for (let v = 0; v < 2; v++) {
          vertices.push(x * 12 + rand() * 3, y * 12 + rand() * 3, -rand() * 4);
          ids.push(id);
        }
        edges.push(base, base + 1);
      }
  // Long crossing edge, duplicate, and opposite ownership at identical depth.
  vertices.push(-100, 0, 0, 100, 0, 0, -100, 0, 0, 100, 0, 0);
  ids.push(252, 252, 253, 253);
  const end = vertices.length / 3;
  edges.push(end - 4, end - 3, end - 4, end - 3, end - 2, end - 1);
  const position = new Float32Array(vertices),
    original = new Uint32Array(edges);
  const pages = linePages(position, original, 32);
  const residency = new ResidentLineIndex(8);
  residency.sync([
    { skelBase: 0, skelLod: { levels: [original], pages: [pages] } },
  ]);
  const residentAttribute = new THREE.BufferAttribute(residency.index, 1);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
  geometry.setAttribute(
    "neuron",
    new THREE.BufferAttribute(new Float32Array(ids), 1),
  );
  const material = new THREE.ShaderMaterial({
    uniforms: { mode: { value: 0 } },
    vertexShader: `attribute float neuron; flat varying float id;
      void main(){id=neuron;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `#include <packing>
      uniform int mode; flat varying float id;
      void main(){
        if(mode==2){gl_FragColor=packDepthToRGBA(gl_FragCoord.z);return;}
        if(mode==1){gl_FragColor=vec4(id/255.0,0.0,0.0,1.0);return;}
        // Screen-door transparency retains fragment-coordinate dependence.
        if(mod(floor(gl_FragCoord.x)+2.0*floor(gl_FragCoord.y),4.0)==0.0)discard;
        gl_FragColor=vec4(fract(id*.31),fract(id*.17),fract(id*.13),1.0);
      }`,
  });
  const lines = new THREE.LineSegments(geometry, material);
  lines.frustumCulled = false;
  root.add(lines);
  world.updateMatrixWorld(true);
  const records = [];
  try {
    for (const [name, x, z, fov, offset] of [
      ["dense-full-view", 0, 180, 75, 0],
      ["close", 0, 12, 45, 0],
      ["left-eye", -0.035, 40, 50, 0.12],
      ["right-eye", 0.035, 40, 50, -0.12],
      ["near-plane", 0, 1, 75, 0],
      ["off-axis", 25, 35, 40, 0.35],
    ]) {
      const camera = new THREE.PerspectiveCamera(fov, 192 / 128, 0.1, 300);
      camera.position.set(x, 0, z);
      camera.lookAt(x, 0, 0);
      camera.updateMatrixWorld(true);
      camera.projectionMatrix.elements[8] += offset;
      const eyes = localEyePlanes(THREE, root.matrixWorld, [
        {
          projection: camera.projectionMatrix,
          inverseWorld: camera.matrixWorldInverse,
          width: 192,
          height: 128,
        },
      ]);
      const selected = visibleLinePages(pages, eyes);
      const index = new Uint32Array(2 * selected.edges);
      writeVisibleEdges(index, 0, original, pages, selected.visible);
      const passes = Object.fromEntries(
        ["colour", "neuron_id", "packed_depth"].map((key, mode) => [
          key,
          () => {
            material.uniforms.mode.value = mode;
            return () => {};
          },
        ]),
      );
      lines.material = material;
      geometry.clearGroups();
      geometry.setDrawRange(0, Infinity);
      geometry.setIndex(new THREE.BufferAttribute(original, 1));
      const reference = capturePasses(
        THREE,
        renderer,
        world,
        camera,
        passes,
        192,
        128,
      );
      geometry.setIndex(new THREE.BufferAttribute(index, 1));
      const candidate = capturePasses(
        THREE,
        renderer,
        world,
        camera,
        passes,
        192,
        128,
      );
      const plan = residency.plan(eyes, () => true, visibleLinePages);
      if (plan.fallback) throw new Error("Unexpected resident oracle fallback");
      geometry.setIndex(residentAttribute);
      geometry.clearGroups();
      for (const r of plan.ranges) geometry.addGroup(r.start, r.count, 0);
      lines.material = [material];
      const resident = capturePasses(
        THREE,
        renderer,
        world,
        camera,
        passes,
        192,
        128,
      );
      const cachedIndex = new Uint32Array(plan.visibleIndices);
      residency.copyVisible(cachedIndex);
      geometry.setIndex(new THREE.BufferAttribute(cachedIndex, 1));
      geometry.clearGroups();
      if (cachedIndex.length) geometry.addGroup(0, cachedIndex.length, 0);
      const cached = capturePasses(
        THREE,
        renderer,
        world,
        camera,
        passes,
        192,
        128,
      );
      if (residentAttribute.version !== 0)
        throw new Error("Camera selection dirtied the resident index");
      const idPixels = reference.neuron_id;
      if (
        !idPixels.some(
          (v, i) =>
            i % 4 === 0 &&
            v > 0 &&
            idPixels[i + 1] === 0 &&
            idPixels[i + 2] === 0,
        )
      )
        throw new Error(`${name}: reference has no neuron-ID witness`);
      const checks = {};
      for (const key of Object.keys(reference)) {
        let different = 0;
        reference[key].forEach((v, i) => {
          if (v !== candidate[key][i]) different++;
        });
        checks[key] = {
          different_bytes: different,
          reference_sha256: await sha256(reference[key]),
          candidate_sha256: await sha256(candidate[key]),
        };
        if (different)
          throw new Error(`${name}/${key}: ${different} changed bytes`);
        let residentDifferent = 0;
        reference[key].forEach((v, i) => {
          if (v !== resident[key][i]) residentDifferent++;
        });
        if (residentDifferent)
          throw new Error(
            `${name}/${key}: ${residentDifferent} resident bytes changed`,
          );
        checks[key].resident_sha256 = await sha256(resident[key]);
        checks[key].resident_different_bytes = residentDifferent;
        const cachedDifferent = reference[key].reduce(
          (n, v, i) => n + Number(v !== cached[key][i]),
          0,
        );
        if (cachedDifferent)
          throw new Error(`${name}/${key}: cached compact output changed`);
        checks[key].cached_different_bytes = cachedDifferent;
        checks[key].cached_sha256 = await sha256(cached[key]);
      }
      records.push({
        name,
        source_edges: original.length / 2,
        submitted_edges: selected.edges,
        resident_submitted_edges: plan.submittedIndices / 2,
        resident_draws: plan.ranges.length,
        checks,
      });
    }
    if (!records.some((r) => r.submitted_edges < r.source_edges))
      throw new Error("Oracle did not exercise culling");
    if (!records.some((r) => r.submitted_edges === r.source_edges))
      throw new Error("Oracle did not exercise all-visible case");
    return {
      schema: "flymsg.geometry-page-oracle/v1",
      status: "pass",
      fixture: "synthetic; not headset qualification",
      records,
    };
  } finally {
    geometry.dispose();
    material.dispose();
    renderer.dispose();
  }
}
