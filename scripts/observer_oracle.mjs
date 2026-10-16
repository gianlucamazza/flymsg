// Full selected anatomy, original renderer oracle. Never used as a cadence trial.
import { verifyRasterFootprint } from "../src/flymsg/viz_static/bounded-raster-oracle.js";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { localObserver } from "./observer_cdp.mjs";
import { observerPreflight } from "./observer_preflight.mjs";

export function verifyCoverage(expected, pages) {
  const covered = new Map(Object.keys(expected).map((k) => [k, 0]));
  for (const page of pages)
    for (const span of page.spans) {
      if (!(span.source in expected)) continue; // Context is independently included in colour/depth captures.
      if (
        span.first !== covered.get(span.source) ||
        !Number.isInteger(span.count) ||
        span.count < 1
      )
        throw Error(`Primitive coverage gap/overlap: ${span.source}`);
      covered.set(span.source, span.first + span.count);
    }
  for (const [key, count] of Object.entries(expected))
    if (covered.get(key) !== count)
      throw Error(`Incomplete original primitive coverage: ${key}`);
}

export async function observerOracle(
  browser,
  out,
  { readbackOnly = false } = {},
) {
  mkdirSync(out, { recursive: false });
  const write = (n, x) =>
    writeFileSync(join(out, n), JSON.stringify(x, null, 2) + "\n", {
      flag: n === "progress.json" ? "w" : "wx",
    });
  let saved;
  const report = {
    schema: "flymsg.observer-hardware-oracle/v1",
    status: "running",
    cases: [],
    qualification: "correctness only; no performance claim",
    readback_only: readbackOnly,
    normal_xr_qualification: false,
  };
  try {
    const pre = await observerPreflight(browser, browser.url, { readbackOnly });
    write("preflight.json", pre);
    if (!pre.eligible || !pre.state.resources.gpu_resources.complete)
      throw Error("Complete paged observer required");
    const bounded = pre.state.fidelity.representation === "skeleton-bounded";
    report.representation = pre.state.fidelity.representation;
    saved = await browser.evaluate("flymsg.diagnosticState()");
    await browser.evaluate(
      "flymsg.diagnostic({suspended:true,playing:false,time:20,pageCulling:false})",
    );
    const camera = await browser.evaluate(
      "({camera_world:flymsg.camera.matrixWorld.toArray(),projection:flymsg.camera.projectionMatrix.toArray()})",
    );
    write("camera.json", camera);
    let first;
    for (const time of [0, 20, 350])
      for (const eye of [-1, 1]) {
        const world = [...camera.camera_world];
        world[12] += eye * 0.015 * Math.hypot(world[12], world[13], world[14]);
        const options = {
          width: 256,
          height: 256,
          time,
          cameraWorld: world,
          projection: camera.projection,
        };
        const reference = await browser.evaluate(
          `flymsg.reference(${JSON.stringify({ ...options, pipeline: "original" })})`,
        );
        let geometryProof = null;
        if (bounded) {
          await browser.evaluate(
            `flymsg.prepareBounded(${JSON.stringify(options)})`,
          );
          geometryProof = await browser.evaluate(`(async()=>{
            const {auditBoundedRuntime}=await import('./bounded-runtime-oracle.js');
            const modelView=new flymsg.THREE.Matrix4().fromArray(${JSON.stringify(world)}).invert().multiply(flymsg.data.matrixWorld).toArray();
            return auditBoundedRuntime(flymsg,[{modelView,projection:${JSON.stringify(camera.projection)},width:256,height:256}]);})()`);
        }
        const candidate = await browser.evaluate(
          `flymsg.reference(${JSON.stringify({ ...options, pipeline: "paged", culling: true })})`,
        );
        write(`reference-${time}-${eye}.json`, reference);
        write(`candidate-${time}-${eye}.json`, candidate);
        const matches = Object.fromEntries(
          Object.keys(reference.images).map((k) => [
            k,
            reference.images[k].sha256 === candidate.images[k].sha256,
          ]),
        );
        const pixels = Buffer.from(reference.images.neuron_id.base64, "base64");
        let witness = false;
        for (let i = 0; i < pixels.length; i += 4)
          if (pixels[i] || pixels[i + 1] || pixels[i + 2]) witness = true;
        const footprint = bounded
          ? verifyRasterFootprint(
              reference.images.colour,
              candidate.images.colour,
              reference.images.neuron_id,
              256,
              256,
            )
          : null;
        report.cases.push({
          time,
          eye,
          matches,
          nonempty_ids: witness,
          geometry_proof: geometryProof,
          footprint,
        });
        write("progress.json", report);
        if (
          !(
            bounded
              ? [matches.neuron_id, matches.packed_depth]
              : Object.values(matches)
          ).every(Boolean) ||
          !witness
        )
          throw Error("Original/candidate stereo mismatch or empty scene");
        first ??= reference;
      }
    const expected = await browser.evaluate(`(()=>{
      const expected={};const selected=${JSON.stringify(first.neurons)};
      for(const entry of selected){const n=flymsg.neurons.find(n=>n.k===entry.k);
        if(['skeleton','skeleton-bounded'].includes(flymsg.fidelity().representation))expected['skeleton:'+entry.k]=n.skelLod.levels[0].length/2;
        else for(const key of entry.surfaces)expected['surface:'+entry.k+':'+key]=n.shown.get(key).geometry.index.array.length/3;
      }return expected;})()`);
    const inventory = await browser.evaluate("flymsg.gpuInventory()");
    write("gpu-inventory.json", inventory);
    write("original-primitive-counts.json", expected);
    verifyCoverage(expected, inventory);
    report.primitive_count = Object.values(expected).reduce((a, b) => a + b, 0);
    report.selected_neurons = first.neurons.length;
    report.scene_sha256 = first.scene_sha256;
    report.activity_sha256 = first.activity_sha256;
    for (const time of [0, 20, 350]) {
      const original = await browser.evaluate(
        `flymsg.desktopReference({time:${time},pipeline:'original'})`,
      );
      if (bounded) await browser.evaluate("flymsg.prepareBounded()");
      const candidate = await browser.evaluate(
        `flymsg.desktopReference({time:${time},pipeline:'paged'})`,
      );
      let footprint = null,
        sourceNeuronId = null;
      if (bounded) {
        const source = await browser.evaluate(
          `flymsg.reference(${JSON.stringify({ time, width: original.width, height: original.height, projection: original.projection, cameraWorld: original.camera_world, pipeline: "original" })})`,
        );
        sourceNeuronId = source.images.neuron_id;
        const radius = await browser.evaluate(
          `(async()=>{const {bloomFootprint}=await import('./bounded-raster-oracle.js');return bloomFootprint(flymsg,${original.width},${original.height});})()`,
        );
        footprint = verifyRasterFootprint(
          original.rgba,
          candidate.rgba,
          source.images.neuron_id,
          original.width,
          original.height,
          radius,
        );
      }
      write(`desktop-${time}.json`, {
        original,
        candidate,
        footprint,
        source_neuron_id: sourceNeuronId,
      });
      if (
        (!bounded && original.rgba.sha256 !== candidate.rgba.sha256) ||
        original.samples !== candidate.samples ||
        JSON.stringify(original.projection) !==
          JSON.stringify(candidate.projection) ||
        JSON.stringify(original.camera_world) !==
          JSON.stringify(candidate.camera_world)
      )
        throw Error("Full-quality desktop mismatch");
    }
    report.status = "pass";
    write("oracle.json", report);
    return report;
  } catch (error) {
    report.status = "excluded";
    report.error = error.message;
    write("failure.json", report);
    throw error;
  } finally {
    const cleanup = { ok: true };
    try {
      if (saved)
        await browser.evaluate(`flymsg.diagnostic(${JSON.stringify(saved)})`);
    } catch (error) {
      cleanup.ok = false;
      cleanup.error = error.message;
    }
    write("cleanup.json", cleanup);
    if (!cleanup.ok && report.status === "pass")
      throw Error("Oracle observer restoration failed; retained cleanup.json");
  }
}

if (
  process.argv[1] &&
  import.meta.url === new URL(`file://${process.argv[1]}`).href
) {
  const [endpoint, target, out, ...flags] = process.argv.slice(2);
  let browser;
  try {
    browser = await localObserver(endpoint, target);
    console.log(
      JSON.stringify(
        await observerOracle(browser, out, {
          readbackOnly: flags.includes("--readback-only"),
        }),
      ),
    );
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  } finally {
    browser?.close();
  }
}
