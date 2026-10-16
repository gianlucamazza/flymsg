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
])
  test(`preflight rejects ${damage}`, async () => {
    const expected = "http://localhost:8892/live/looming/?check";
    const browser = {
      evaluate: async () => ({
        url: damage === "url" ? "http://localhost:1234/" : expected,
        visibility: damage === "hidden" ? "hidden" : "visible",
        frame_callbacks: damage === "callbacks" ? 0 : 20,
        stats: damage === "loading" ? "1 loading" : "x · 0 loading · y",
        fidelity: {
          status: damage === "anatomy" ? "unsupported" : "ready",
          gpu_ready: damage !== "gpu",
        },
      }),
      loadedSources: async (names) =>
        Object.fromEntries(
          names.map((name) => [
            name,
            damage === "source"
              ? "stale"
              : readFileSync(
                  new URL(
                    `../../src/flymsg/viz_static/${name}`,
                    import.meta.url,
                  ),
                  "utf8",
                ),
          ]),
        ),
    };
    const result = await observerPreflight(browser, expected);
    assert.equal(result.eligible, damage === "none");
    assert.equal(result.reasons.length === 0, damage === "none");
  });
