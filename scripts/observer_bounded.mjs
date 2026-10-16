// Explicit disposable diagnostic; the production entrypoint never imports this mode.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { localObserver } from "./observer_cdp.mjs";
import { observerPreflight } from "./observer_preflight.mjs";
const [endpoint, target, out, view = "dense"] = process.argv.slice(2);
if (!endpoint || !target || !out || !["dense", "close"].includes(view))
  throw Error(
    "usage: observer_bounded.mjs ENDPOINT TARGET NEW_DIRECTORY dense|close",
  );
mkdirSync(out, { recursive: false });
const write = (n, d) =>
  writeFileSync(join(out, n), JSON.stringify(d, null, 2) + "\n", {
    flag: "wx",
  });
const browser = await localObserver(endpoint, target);
try {
  const pre = await observerPreflight(browser, browser.url, {
    readbackOnly: true,
  });
  write("preflight.json", pre);
  if (!pre.eligible || new URL(browser.url).searchParams.get("uploads") === "1")
    throw Error("Ready original observer required");
  const saved = await browser.evaluate("flymsg.diagnosticState()");
  write("protocol.json", {
    schema: "flymsg.bounded-protocol/v1",
    view,
    repeats: 3,
    order: ["original", "bounded", "bounded", "original"],
    warmup: 5,
    iterations: 8,
    error_px: 0.5,
    normal_xr_qualification: false,
    rule: "Independent graph/projection verification required. Serialized median gain >=10% in every block is exploratory only. No moving camera, physical stereo or production admission.",
  });
  await browser.evaluate(
    "(async()=>{globalThis.flymsgBoundedModule=await import(new URL('bounded-experiment.js',location.href));return true;})()",
  );
  const names = [
    "bounded-paths.js",
    "bounded-path-oracle.js",
    "bounded-experiment.js",
  ];
  const loaded = await browser.loadedSources(names),
    hashes = {};
  for (const name of names) {
    const local = readFileSync(
      new URL("../src/flymsg/viz_static/" + name, import.meta.url),
    );
    const digest = (data) => createHash("sha256").update(data).digest("hex");
    if (digest(local) !== digest(loaded[name]))
      throw Error("Loaded diagnostic source mismatch: " + name);
    hashes[name] = digest(local);
  }
  write("sources.json", hashes);
  const result = await browser.evaluate(
    `flymsgBoundedModule.boundedExperiment(flymsg,${JSON.stringify({ close: view === "close" })})`,
  );
  write("experiment.json", result);
  const after = await browser.evaluate("flymsg.diagnosticState()");
  if (JSON.stringify(saved) !== JSON.stringify(after))
    throw Error("Observer state restoration mismatch");
  write("complete.json", {
    status: "complete",
    state_restored: true,
    normal_xr_qualification: false,
  });
  console.log(
    JSON.stringify({
      view,
      neurons: result.neurons.length,
      original_edges: result.neurons.reduce((s, n) => s + n.original_edges, 0),
      candidate_edges: result.neurons.reduce(
        (s, n) => s + n.candidate_edges,
        0,
      ),
      maximum_error_px: Math.max(
        ...result.neurons.map((n) => n.maximum_error_px),
      ),
    }),
  );
} finally {
  await browser
    .evaluate("delete globalThis.flymsgBoundedModule")
    .catch(() => {});
  browser.close();
}
