// node scripts/observer_residency.mjs LOCAL_CDP_ENDPOINT TARGET_ID NEW_DIRECTORY
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { localObserver } from "./observer_cdp.mjs";
import { residentLineProbe } from "../src/flymsg/viz_static/resident-probe.js";
import { localEyePlanes } from "../src/flymsg/viz_static/page-views.js";

const [endpoint, target, out] = process.argv.slice(2);
if (!endpoint || !target || !out)
  throw Error(
    "usage: observer_residency.mjs LOCAL_CDP_ENDPOINT TARGET_ID NEW_DIRECTORY",
  );
const browser = await localObserver(endpoint, target);
const options = { size: 512, warmup: 3, repeats: 8, time: 20 };
const files = [
  "main.js",
  "resident-lines.js",
  "resident-probe.js",
  "geometry-pages.js",
  "page-views.js",
];
try {
  mkdirSync(out, { recursive: false });
  const source = Object.fromEntries(
    files.map((name) => [
      name,
      readFileSync(
        new URL(`../src/flymsg/viz_static/${name}`, import.meta.url),
      ),
    ]),
  );
  const hashes = Object.fromEntries(
    files.map((name) => [
      name,
      createHash("sha256").update(source[name]).digest("hex"),
    ]),
  );
  writeFileSync(
    join(out, "protocol.json"),
    JSON.stringify(
      {
        options,
        hashes,
      rule: "Require full-source colour/ID/depth parity, identical moving colour output, zero resident steady-state index uploads and bounded ranges. Compare compact/resident/resident/compact selection and serialized wall times per view. Reject >10% dense or close-static wall regression; timing remains diagnostic, not XR qualification.",
      },
      null,
      2,
    ) + "\n",
    { flag: "wx" },
  );
  for (const name of files)
    writeFileSync(join(out, name), source[name], { flag: "wx" });
  const before = await browser.evaluate(
    `({state:flymsg.diagnosticState(),fidelity:flymsg.fidelity(),resources:flymsg.resources(),visibility:document.visibilityState})`,
  );
  const served =
    await browser.evaluate(`(async()=>Object.fromEntries(await Promise.all(${JSON.stringify(files)}.map(async name=>{
    const response=await fetch(new URL(name,location.href));if(!response.ok)throw Error(name);
    const digest=await crypto.subtle.digest('SHA-256',await response.arrayBuffer());
    return [name,[...new Uint8Array(digest)].map(v=>v.toString(16).padStart(2,'0')).join('')];
  }))))()`);
  if (JSON.stringify(served) !== JSON.stringify(hashes))
    throw Error("Served application differs from recorded source");
  const result = await browser.evaluate(
    `(${residentLineProbe.toString()})(flymsg,(${localEyePlanes.toString()}),${JSON.stringify(options)})`,
  );
  const after = await browser.evaluate(
    `({state:flymsg.diagnosticState(),fidelity:flymsg.fidelity(),resources:flymsg.resources(),visibility:document.visibilityState})`,
  );
  const restored = await browser.evaluate(
    "flymsg.reference({width:32,height:32,time:20,culling:false})",
  );
  if (JSON.stringify(restored) !== JSON.stringify(result.source_reference))
    throw Error("Reference restoration differs; no completed artifact");
  if (JSON.stringify(before.state) !== JSON.stringify(after.state))
    throw Error("Observer state restoration failed");
  for (const name of files)
    if (
      !source[name].equals(
        readFileSync(
          new URL(`../src/flymsg/viz_static/${name}`, import.meta.url),
        ),
      )
    )
      throw Error("Source changed during diagnostic; no completed artifact");
  writeFileSync(
    join(out, "probe.json"),
    JSON.stringify(
      {
        url: browser.url,
        recorded_at: new Date().toISOString(),
        before,
        after,
        served_sources: served,
        restoration_reference_identical: true,
        ...result,
      },
      null,
      2,
    ) + "\n",
    { flag: "wx" },
  );
  const median = (xs) => {
    const sorted = [...xs].sort((a, b) => a - b), middle = Math.floor(xs.length / 2);
    return xs.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  };
  console.log(
    JSON.stringify(
      result.records.map((r) => ({
        name: r.name,
        mode: r.mode,
        order: r.order,
        selection_ms: median(r.samples.map((s) => s.selection_ms)),
        wall_ms: median(r.samples.map((s) => s.serialized_wall_ms)),
        index_bytes: r.samples.reduce((n, s) => n + s.index_upload_bytes, 0),
      })),
    ),
  );
} finally {
  browser.close();
}
