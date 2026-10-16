import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { observerPreflight } from "../../scripts/observer_preflight.mjs";

for (const damage of [
  "none",
  "source",
  "url",
  "hidden",
  "gpu",
  "loading",
  "anatomy",
  "callbacks",
  "suspended",
  "document",
  "rendering",
  "active",
])
  test(`preflight ${damage}`, async () => {
    const url = "http://localhost:8892/live/looming/?check";
    let debuggers = 0;
    const browser = {
      evaluate: async () => ({
        url: damage === "url" ? "http://localhost:1234/" : url,
        visibility: damage === "hidden" ? "hidden" : "visible",
        frame_callbacks: damage === "callbacks" ? 0 : 20,
        submitted_frames: damage === "rendering" ? 0 : 20,
        before: { document_id: "a" },
        after: {
          document_id: damage === "document" ? "b" : "a",
          suspended: damage === "suspended",
          capture_running: damage === "active",
          identity: { context_ready: true },
        },
        stats: damage === "loading" ? "1 loading" : "x · 0 loading · y",
        fidelity: {
          status: damage === "anatomy" ? "unsupported" : "ready",
          gpu_ready: damage !== "gpu",
        },
      }),
      loadedSources: async (names) => {
        debuggers++;
        return Object.fromEntries(
          names.map((n) => [
            n,
            damage === "source"
              ? "stale"
              : readFileSync(
                  new URL(`../../src/flymsg/viz_static/${n}`, import.meta.url),
                  "utf8",
                ),
          ]),
        );
      },
    };
    const r = await observerPreflight(browser, url, { requireRendering: true });
    assert.equal(r.eligible, damage === "none");
    if (damage === "active") assert.equal(debuggers, 0);
    await observerPreflight(browser, url, { verifySources: false });
    assert.equal(debuggers, damage === "none" || damage === "source" ? 1 : 0);
  });

test("explicit idle readback preparation cannot authorize cadence or immersive frames", async () => {
  const url = "http://localhost:8894/live/looming/?check";
  const state = {
    url,
    visibility: "visible",
    frame_callbacks: 0,
    submitted_frames: 0,
    before: { document_id: "a" },
    after: { document_id: "a", identity: { context_ready: true } },
    stats: "x · 0 loading · y",
    fidelity: { status: "ready", gpu_ready: true },
    immersive: false,
  };
  const browser = { evaluate: async () => state };
  const options = { verifySources: false, readbackOnly: true };
  assert((await observerPreflight(browser, url, options)).eligible);
  assert(
    !(await observerPreflight(browser, url, { verifySources: false })).eligible,
  );
  assert(
    !(
      await observerPreflight(browser, url, {
        ...options,
        requireRendering: true,
      })
    ).eligible,
  );
  state.immersive = true;
  assert(!(await observerPreflight(browser, url, options)).eligible);
  state.immersive = false;
  state.visibility = "hidden";
  assert(!(await observerPreflight(browser, url, options)).eligible);
});
