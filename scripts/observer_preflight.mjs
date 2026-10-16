// Read-only preflight: loaded code must equal this checkout, not merely its server.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { localObserver } from "./observer_cdp.mjs";

export async function observerPreflight(browser, expectedUrl) {
  const state = await browser.evaluate(`(async() => {
    const immersive=flymsg.renderer.xr.isPresenting;
    const before=immersive?window.flymsgXrReport?.()?.frames:0;
    let callbacks=0,frame;
    const tick=()=>{callbacks++;frame=requestAnimationFrame(tick)};
    if(!immersive)frame=requestAnimationFrame(tick);
    await new Promise(resolve=>setTimeout(resolve,1200));
    if(frame!==undefined)cancelAnimationFrame(frame);
    if(immersive)callbacks=(window.flymsgXrReport?.()?.frames??before)-before;
    return {url:location.href, frame_callbacks:callbacks,
    visibility:document.visibilityState, fidelity:flymsg.fidelity(),
    resources:flymsg.resources(), immersive:flymsg.renderer.xr.isPresenting,
    stats:document.getElementById('stats').textContent};})()`);
  const reasons = [];
  if (state.url !== expectedUrl) reasons.push("unexpected-url");
  if (state.visibility !== "visible") reasons.push("hidden-page");
  if (!(state.frame_callbacks > 1)) reasons.push("no-frame-callbacks");
  if (state.fidelity.status !== "ready") reasons.push("incomplete-anatomy");
  if (state.fidelity.gpu_ready === false) reasons.push("gpu-not-ready");
  if (!/(?:^| · )0 loading(?: · |$)/.test(state.stats)) reasons.push("loading");
  const names = [
    "main.js",
    "paged-scene.js",
    "gpu-upload.js",
    "primitive-pages.js",
  ];
  const loaded = await browser.loadedSources(names);
  const sources = {};
  for (const name of names) {
    const hash = (s) => createHash("sha256").update(s).digest("hex");
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
  return { state, sources, reasons, eligible: reasons.length === 0 };
}

if (
  process.argv[1] &&
  import.meta.url === new URL(`file://${process.argv[1]}`).href
) {
  const [endpoint, target, expectedUrl] = process.argv.slice(2);
  const browser = await localObserver(endpoint, target);
  try {
    const result = await observerPreflight(browser, expectedUrl);
    console.log(JSON.stringify(result));
    if (!result.eligible) process.exitCode = 1;
  } finally {
    browser.close();
  }
}
