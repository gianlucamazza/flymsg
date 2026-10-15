// Independent source geometry is rendered and expanded separately from the
// candidate packer. Software WebGL establishes correctness, never device speed.
import { PagedScene } from "./paged-scene.js";
import { capturePasses, sha256 } from "./render-reference.js";

export async function pagedSceneOracle(T) {
  const renderer = new T.WebGLRenderer({ antialias: false });
  renderer.setSize(128, 128);
  const world = new T.Scene(),
    data = new T.Group();
  world.add(data);
  const camera = new T.PerspectiveCamera(60, 1, 0.1, 20);
  camera.position.z = 3;
  const materials = [];
  const material = (fragmentShader, side = T.DoubleSide) => {
    const m = new T.ShaderMaterial({
      side,
      vertexShader: `attribute float aNeuron; flat varying float vId;
        void main() { vId = aNeuron + 1.0; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader,
    });
    materials.push(m);
    return m;
  };
  const colour = material(
    `flat varying float vId; void main(){gl_FragColor=vec4(vId/7.0,0.5,0.25,1.0);}`,
  );
  const id = material(
    `flat varying float vId; void main(){gl_FragColor=vec4(vId/255.0,0.0,0.0,1.0);}`,
  );
  const depth = material(`#include <packing>
    void main(){gl_FragColor=packDepthToRGBA(gl_FragCoord.z);}`);
  const results = [];
  const gl = renderer.getContext(),
    read = (buffer, count, Type) => {
      const array = new Type(count),
        previous = gl.getParameter(gl.COPY_READ_BUFFER_BINDING);
      try {
        gl.bindBuffer(gl.COPY_READ_BUFFER, buffer);
        gl.getBufferSubData(gl.COPY_READ_BUFFER, 0, array);
      } finally {
        gl.bindBuffer(gl.COPY_READ_BUFFER, previous);
      }
      return array;
    };
  const same = (a, b) =>
    a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  for (const primitiveSize of [2, 3]) {
    const layer = {
      primitiveSize,
      material: colour,
      neuron_id: id,
      packed_depth: depth,
    };
    const sources = [0, 1, 2].map((n) => {
      // Repeated overlapping primitives exercise exact depth ties; the long
      // edge and near-plane crossing must survive page boundaries.
      const vertices = new Float32Array([
        -2, -0.8, 0, 2, 0.8, 0, -0.8, 0.8, 0, 0, 0, 2.99,
      ]);
      const index = Uint32Array.from(
        { length: primitiveSize * 101 },
        (_, i) => i % (primitiveSize === 3 ? 3 : 4),
      );
      const normals = new Float32Array(vertices.length);
      for (let i = 2; i < normals.length; i += 3) normals[i] = 1;
      return {
        key: `neuron:${n}`,
        layer,
        index,
        attributes: {
          position: { itemSize: 3, array: vertices },
          normal: { itemSize: 3, array: normals },
          aNeuron: { itemSize: 1, constant: n },
        },
      };
    });
    const contextMaterial = colour.clone();
    contextMaterial.fragmentShader = contextMaterial.fragmentShader.replace(
      "0.25,1.0",
      "0.25,0.35",
    );
    contextMaterial.transparent = true;
    contextMaterial.depthWrite = false;
    materials.push(contextMaterial);
    sources[2].layer = { ...layer, material: contextMaterial, context: true };
    const originals = sources.map((s) => {
      const g = new T.BufferGeometry();
      for (const [name, a] of Object.entries(s.attributes))
        g.setAttribute(
          name,
          new T.BufferAttribute(
            a.array ?? new Float32Array(4).fill(a.constant),
            a.itemSize,
          ),
        );
      g.setIndex(new T.BufferAttribute(s.index, 1));
      const o =
        primitiveSize === 2
          ? new T.LineSegments(g, s.layer.material)
          : new T.Mesh(g, s.layer.material);
      o.frustumCulled = false;
      data.add(o);
      return o;
    });
    const candidate = new PagedScene(T, renderer, data, { maxPageBytes: 512 });
    renderer.setAnimationLoop(() => {
      candidate.tick();
      if (candidate.state === "warming")
        candidate.render(originals, () => renderer.render(world, camera));
    });
    async function ready() {
      const deadline = performance.now() + 10000;
      while (
        ["preparing", "warming"].includes(candidate.state) &&
        performance.now() < deadline
      )
        await new Promise((r) => setTimeout(r, 5));
      assert(
        candidate.state === "ready",
        `Preparation failed: ${JSON.stringify(candidate.report())}`,
      );
    }
    try {
      candidate.sync(sources, true);
      await ready();
      const baseline = capturePasses(
        T,
        renderer,
        world,
        camera,
        Object.fromEntries(
          [
            ["colour", colour],
            ["neuron_id", id],
            ["packed_depth", depth],
          ].map(([name, m]) => [
            name,
            () => {
              originals.forEach((o, i) => {
                o.material = name === "colour" ? sources[i].layer.material : m;
                o.visible = name === "colour" || !sources[i].layer.context;
              });
              return () =>
                originals.forEach((o, i) => {
                  o.material = sources[i].layer.material;
                  o.visible = true;
                });
            },
          ]),
        ),
        128,
        128,
      );
      const actual = capturePasses(
        T,
        renderer,
        world,
        camera,
        { colour: () => {}, neuron_id: () => {}, packed_depth: () => {} },
        128,
        128,
        (pass) =>
          candidate.render(originals, () => renderer.render(world, camera), {
            pass,
          }),
      );
      for (const pass of Object.keys(baseline))
        assert(
          same(actual[pass], baseline[pass]),
          `${primitiveSize}: ${pass} raster mismatch`,
        );
      assert(
        baseline.neuron_id.some((v, i) => i % 4 === 0 && v > 0),
        "Empty ID oracle",
      );
      const expected = sources.flatMap((s) =>
        Array.from(s.index, (vertex) => [
          ...s.attributes.position.array.subarray(vertex * 3, vertex * 3 + 3),
          ...s.attributes.normal.array.subarray(vertex * 3, vertex * 3 + 3),
          s.attributes.aNeuron.constant,
        ]),
      );
      const uploaded = [];
      for (const page of candidate.pages) {
        const p = read(
          page.record.buffers[0].buffer,
          page.counts[0],
          Float32Array,
        );
        const n = read(
          page.record.buffers[1].buffer,
          page.counts[1],
          Float32Array,
        );
        const ids = read(
          page.record.buffers[2].buffer,
          page.counts[2],
          Float32Array,
        );
        const indices = read(
          page.record.buffers[3].buffer,
          page.counts[3],
          Uint32Array,
        );
        for (const vertex of indices)
          uploaded.push([
            ...p.subarray(vertex * 3, vertex * 3 + 3),
            ...n.subarray(vertex * 3, vertex * 3 + 3),
            ids[vertex],
          ]);
      }
      assert(
        JSON.stringify(uploaded) === JSON.stringify(expected),
        "Uploaded GPU geometry differs from source stream",
      );
      const inventory = await candidate.inventory(sha256);
      assert(
        inventory.length === candidate.pages.length,
        "Incomplete GPU inventory",
      );
      const owned = candidate.report().owned_gpu_bytes;
      for (let cycle = 0; cycle < 5; cycle++) {
        candidate.reset();
        assert(
          candidate.report().owned_gpu_bytes === 0,
          "GPU resources leaked on release",
        );
        candidate.sync(sources, true);
        await ready();
        assert(
          candidate.report().owned_gpu_bytes === owned,
          "GPU resources accumulate across cycles",
        );
      }
      let contextRestored = false;
      if (primitiveSize === 3) {
        const extension = gl.getExtension("WEBGL_lose_context");
        assert(extension, "Context-loss oracle unavailable");
        const lost = new Promise((resolve) =>
          renderer.domElement.addEventListener(
            "webglcontextlost",
            (event) => {
              event.preventDefault();
              candidate.contextLost();
              resolve();
            },
            { once: true },
          ),
        );
        extension.loseContext();
        await lost;
        assert(
          candidate.report().owned_gpu_bytes === 0 &&
            candidate.state === "context-lost",
          "Lost-context handles retained",
        );
        await new Promise((resolve) => setTimeout(resolve, 1100));
        const restored = new Promise((resolve) =>
          renderer.domElement.addEventListener(
            "webglcontextrestored",
            () => {
              candidate.contextRestored();
              resolve();
            },
            { once: true },
          ),
        );
        extension.restoreContext();
        await restored;
        candidate.sync(sources, true);
        await ready();
        candidate.render(originals, () => renderer.render(world, camera));
        const recovered = capturePasses(
          T,
          renderer,
          world,
          camera,
          { colour: () => {}, neuron_id: () => {}, packed_depth: () => {} },
          128,
          128,
          (pass) =>
            candidate.render(originals, () => renderer.render(world, camera), {
              pass,
            }),
        );
        for (const pass of Object.keys(baseline))
          assert(
            same(recovered[pass], baseline[pass]),
            `Context restore changed ${pass}`,
          );
        assert(
          gl.getError() === gl.NO_ERROR,
          "Invalid GPU state after restoration",
        );
        assert(
          candidate.report().owned_gpu_bytes === owned,
          "Context restore changed resource ownership",
        );
        contextRestored = true;
      }
      candidate.sync(sources.slice(0, 1), true);
      candidate.sync(sources.slice(1), true); // cancellation while a worker is pending
      await ready();
      assert(
        candidate.pages
          .flatMap((p) => p.spans)
          .every((s) => s.source !== "neuron:0"),
        "Stale generation published",
      );
      results.push({
        primitiveSize,
        source_primitives: 303,
        passes: ["colour", "neuron_id", "packed_depth"],
        gpu_stream_exact: true,
        lifecycle_cycles: 5,
        stale_generation_rejected: true,
        contextual_alpha_exact: true,
        context_restored: contextRestored,
        owned_gpu_bytes: owned,
      });
    } finally {
      renderer.setAnimationLoop(null);
      candidate.dispose();
      for (const original of originals) {
        data.remove(original);
        original.geometry.dispose();
      }
    }
  }
  materials.forEach((m) => m.dispose());
  renderer.dispose();
  return { status: "pass", backend: "software correctness only", results };
}
