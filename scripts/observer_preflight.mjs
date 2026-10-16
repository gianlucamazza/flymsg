// Read-only preflight: loaded code must equal this checkout, not merely its server.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { localObserver } from "./observer_cdp.mjs";

export async function observerPreflight(browser, expectedUrl) {
  const state = await browser.evaluate(`(() => ({url:location.href,
    visibility:document.visibilityState, fidelity:flymsg.fidelity(),
    resources:flymsg.resources(), immersive:flymsg.renderer.xr.isPresenting,
    stats:document.getElementById('stats').textContent}))()`);
  const reasons = [];
  if (state.url !== expectedUrl) reasons.push("unexpected-url");
  if (state.visibility !== "visible") reasons.push("hidden-page");
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
