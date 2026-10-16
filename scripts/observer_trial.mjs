// Desktop cadence from the application's single loop; no readbacks while armed.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { localObserver } from "./observer_cdp.mjs";
import { observerPreflight } from "./observer_preflight.mjs";
import { frozenCameraProfile } from "./observer-camera.mjs";

export async function observerTrial(
  browser,
  out,
  { seconds = 30, view = "dense-all", camera = null } = {},
) {
  mkdirSync(out, { recursive: false });
  const write = (name, value) =>
    writeFileSync(join(out, name), JSON.stringify(value, null, 2) + "\n", {
      flag: "wx",
    });
  let saved, record, error;
  const cleanup = [];
  try {
    const preflight = await observerPreflight(browser, browser.url);
    write("preflight.json", preflight);
    if (!preflight.eligible)
      throw Error(`Preflight excluded: ${preflight.reasons.join(", ")}`);
    if (preflight.state.immersive) throw Error("Desktop observation required");
    saved =
      await browser.evaluate(`({state:flymsg.diagnosticState(),camera:flymsg.camera.matrixWorld.toArray(),
      projection:flymsg.camera.projectionMatrix.toArray(),near:flymsg.camera.near,far:flymsg.camera.far})`);
    const frozen = frozenCameraProfile(
      { camera_world: saved.camera, projection: saved.projection },
      camera,
      preflight.state.after.identity,
    );
    write("camera.json", frozen);
    const culling =
      view !== "dense-all" &&
      new URL(browser.url).searchParams.get("uploads") === "1";
    await browser.evaluate(
      `flymsg.diagnostic(${JSON.stringify({ suspended: false, continuous: true, time: 20, playing: false, pageCulling: culling })})`,
    );
    await browser.evaluate(
      `flymsg.observerView(${JSON.stringify({ name: view, cameraWorld: frozen.camera_world, projection: frozen.projection })})`,
    );
    // Warmup and all Debugger work precede the arm.
    await new Promise((r) => setTimeout(r, 3000));
    const warm = await observerPreflight(browser, browser.url, {
      verifySources: false,
      expectedDocument: preflight.state.after.document_id,
      requireRendering: true,
    });
    write("warmup.json", warm);
    if (!warm.eligible)
      throw Error(`Warmup excluded: ${warm.reasons.join(", ")}`);
    const settings =
      await browser.evaluate(`({pixel_ratio:flymsg.renderer.getPixelRatio(),
      samples:flymsg.observerStatus().identity.samples,
      composer_target_samples:flymsg.composer.renderTarget1.samples,bloom:flymsg.bloom.enabled})`);
    const sample = await browser.evaluate(`(async()=>{
      flymsg.observerCapture(${JSON.stringify(seconds)});
      let watchdog;
      try {
        await Promise.race([flymsg.observerWait(),new Promise(resolve=>{
          watchdog=setTimeout(resolve,${Math.ceil(seconds * 1000) + 30000});
        })]);
        return flymsg.observerResult();
      } finally {clearTimeout(watchdog);}})()`);
    write("application-samples.json", sample);
    const after = await observerPreflight(browser, browser.url, {
      requireRendering: true,
      expectedDocument: preflight.state.after.document_id,
    });
    const values = [...sample.raw_intervals_ms].sort((a, b) => a - b);
    const percentile = (p) =>
      values.length ? values[Math.ceil(values.length * p) - 1] : null;
    record = {
      schema: "flymsg.observer-trial/v1",
      url: browser.url,
      recorded_at: new Date().toISOString(),
      time_ms: 20,
      seconds,
      view,
      camera_profile: frozen,
      render_settings: settings,
      before: preflight.state,
      after: after.state,
      ...sample,
      source_sha256: Object.fromEntries(
        Object.entries(preflight.sources).map(([k, v]) => [k, v.loaded]),
      ),
      intervals_ms: {
        p50: percentile(0.5),
        p95: percentile(0.95),
        p99: percentile(0.99),
      },
      eligibility: {
        visible:
          preflight.state.visibility === "visible" &&
          after.state.visibility === "visible",
        full_anatomy:
          after.state.fidelity.status === "ready" &&
          after.state.fidelity.gpu_ready !== false,
        document_unchanged:
          sample.document_id === preflight.state.after.document_id,
        application_frames: sample.eligible,
        postflight: after.eligible,
      },
      qualification: "not-scored; desktop diagnostic, not immersive XR",
    };
    record.eligible = Object.values(record.eligibility).every(Boolean);
  } catch (e) {
    error = e;
    try {
      const partial = await browser.evaluate(
        `flymsg.observerStatus().capture_running?flymsg.observerResult():null`,
      );
      if (partial) write("partial.json", partial);
    } catch (e) {
      cleanup.push({ phase: "save-partial", error: e.message });
    }
  } finally {
    if (saved) {
      try {
        await browser.evaluate(`(()=>{flymsg.observerReset();
          flymsg.camera.matrix.fromArray(${JSON.stringify(saved.camera)}).decompose(flymsg.camera.position,flymsg.camera.quaternion,flymsg.camera.scale);
          flymsg.camera.near=${saved.near};flymsg.camera.far=${saved.far};
          flymsg.camera.projectionMatrix.fromArray(${JSON.stringify(saved.projection)});
          flymsg.camera.projectionMatrixInverse.copy(flymsg.camera.projectionMatrix).invert();
          flymsg.camera.updateMatrixWorld(true);flymsg.diagnostic(${JSON.stringify(saved.state)});})()`);
      } catch (e) {
        cleanup.push({ phase: "restore-observer", error: e.message });
      }
    }
    write("cleanup.json", { ok: cleanup.length === 0, errors: cleanup });
  }
  if (record) {
    record.cleanup_ok = cleanup.length === 0;
    record.eligible &&= record.cleanup_ok;
    write("trial.json", record);
  }
  if (error) {
    write("failure.json", {
      status: "excluded",
      reason: error.message,
      cleanup,
      qualification: "not-scored",
    });
    throw error;
  }
  return record;
}

if (
  process.argv[1] &&
  import.meta.url === new URL(`file://${process.argv[1]}`).href
) {
  const [
    endpoint,
    target,
    out,
    seconds = "30",
    view = "dense-all",
    cameraFile,
  ] = process.argv.slice(2);
  let browser;
  try {
    browser = await localObserver(endpoint, target);
    const result = await observerTrial(browser, out, {
      seconds: Number(seconds),
      view,
      camera: cameraFile ? JSON.parse(readFileSync(cameraFile, "utf8")) : null,
    });
    console.log(
      JSON.stringify({
        eligible: result.eligible,
        intervals_ms: result.intervals_ms,
        out,
      }),
    );
    if (!result.eligible) process.exitCode = 1;
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  } finally {
    browser?.close();
  }
}
