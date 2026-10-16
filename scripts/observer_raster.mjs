// node scripts/observer_raster.mjs LOCAL_CDP_ENDPOINT TARGET_ID NEW_DIRECTORY
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { localObserver } from "./observer_cdp.mjs";
const [endpoint, target, out] = process.argv.slice(2);
if (!endpoint || !target || !out)
  throw Error(
    "usage: observer_raster.mjs LOCAL_CDP_ENDPOINT TARGET_ID NEW_DIRECTORY",
  );
const browser = await localObserver(endpoint, target);
const files = [
  "raster.js",
  "raster-painter.js",
  "raster-reference.js",
  "raster-oracle.js",
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
        hashes,
        rule: "Require all RGBA bytes equal against frozen original 63c63d6 at 16 layout/DPR/selection cases and repeated, changing and backward bins. A/B/B/A serialized canvas wall times include identical sink readback; not browser frame or XR performance.",
      },
      null,
      2,
    ),
  );
  for (const name of files) writeFileSync(join(out, name), source[name]);
  const served =
    await browser.evaluate(`(async()=>Object.fromEntries(await Promise.all(${JSON.stringify(files)}.map(async name=>{
    const response=await fetch(new URL(name,location.href));if(!response.ok)throw Error(name);
    const hash=await crypto.subtle.digest('SHA-256',await response.arrayBuffer());
    return [name,[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('')];
  }))))()`);
  if (JSON.stringify(hashes) !== JSON.stringify(served))
    throw Error("Served source differs from local source");
  const result = await browser.evaluate(
    "import('./raster-oracle.js').then(m=>m.rasterOracle())",
  );
  for (const name of files)
    if (
      !source[name].equals(
        readFileSync(
          new URL(`../src/flymsg/viz_static/${name}`, import.meta.url),
        ),
      )
    )
      throw Error("Source changed during trial");
  if (result.status !== "pass") throw Error("Raster oracle failed");
  writeFileSync(
    join(out, "raster.json"),
    JSON.stringify(
      {
        ...result,
        served_sources: served,
        recorded_at: new Date().toISOString(),
      },
      null,
      2,
    ),
    { flag: "wx" },
  );
  console.log(`Raster oracle passed: ${out}`);
} finally {
  browser.close();
}
