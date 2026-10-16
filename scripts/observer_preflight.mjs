// Source verification is a preparation phase. Health checks never enable Debugger.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { localObserver } from "./observer_cdp.mjs";

export async function observerPreflight(
  browser,
  expectedUrl,
  {
    verifySources = true,
    expectedDocument = null,
    requireRendering = false,
  } = {},
) {
  const state = await browser.evaluate(`(async() => {
    const api=window.flymsg;
    if(!api?.observerStatus)return {url:location.href,visibility:document.visibilityState,initializing:true};
    const before=api.observerStatus();
    await new Promise(resolve=>setTimeout(resolve,1200));
    const after=api.observerStatus();
    return {url:location.href,visibility:document.visibilityState,
      before,after,frame_callbacks:after.loop_callbacks-before.loop_callbacks,
      submitted_frames:after.submitted_frames-before.submitted_frames,
      fidelity:api.fidelity(),resources:api.resources(),immersive:after.immersive,
      stats:document.getElementById('stats').textContent};})()`);
  const reasons = [];
  if (state.url !== expectedUrl) reasons.push("unexpected-url");
  if (state.visibility !== "visible") reasons.push("hidden-page");
  if (state.initializing)
    return {
      state,
      reasons: [...reasons, "observer-initializing"],
      sources: {},
      eligible: false,
    };
  if (
    state.before.document_id !== state.after.document_id ||
    (expectedDocument && state.after.document_id !== expectedDocument)
  )
    reasons.push("document-changed");
  if (state.after.capture_running) reasons.push("measurement-active");
  if (state.after.suspended) reasons.push("application-suspended");
  if (!(state.frame_callbacks > 1)) reasons.push("no-application-callbacks");
  if ((requireRendering || state.immersive) && !(state.submitted_frames > 1))
    reasons.push("no-submitted-frames");
  if (state.fidelity.status !== "ready") reasons.push("incomplete-anatomy");
  if (state.fidelity.gpu_ready === false) reasons.push("gpu-not-ready");
  if (state.after.identity?.context_ready === false)
    reasons.push("context-not-ready");
  if (!/(?:^| · )0 loading(?: · |$)/.test(state.stats)) reasons.push("loading");
  const sources = {};
  if (verifySources && (state.immersive || state.after.capture_running))
    reasons.push("source-verification-requires-idle-desktop");
  if (verifySources && reasons.length === 0) {
    const names = [
      "main.js",
      "perf.js",
      "observer-frames.js",
      "paged-scene.js",
      "gpu-upload.js",
      "primitive-pages.js",
      "context-readiness.js",
    ];
    const loaded = await browser.loadedSources(names);
    for (const name of names) {
      const hash = (value) => createHash("sha256").update(value).digest("hex");
      sources[name] = {
        loaded: hash(loaded[name]),
        expected: hash(
          readFileSync(
            new URL(`../src/flymsg/viz_static/${name}`, import.meta.url),
          ),
        ),
      };
      if (sources[name].loaded !== sources[name].expected)
        reasons.push(`source-mismatch:${name}`);
    }
  }
  return {
    state,
    sources,
    source_verification: verifySources && Object.keys(sources).length > 0,
    reasons,
    eligible: reasons.length === 0,
  };
}

if (
  process.argv[1] &&
  import.meta.url === new URL(`file://${process.argv[1]}`).href
) {
  const [endpoint, target, expectedUrl, ...flags] = process.argv.slice(2);
  let browser;
  try {
    browser = await localObserver(endpoint, target);
    const result = await observerPreflight(browser, expectedUrl, {
      verifySources: !flags.includes("--health"),
      requireRendering: flags.includes("--rendering"),
    });
    console.log(JSON.stringify(result));
    if (!result.eligible) process.exitCode = 1;
  } catch (error) {
    console.log(
      JSON.stringify({
        eligible: false,
        reasons: ["browser-preflight-error"],
        error: error.message,
      }),
    );
    process.exitCode = 1;
  } finally {
    browser?.close();
  }
}
