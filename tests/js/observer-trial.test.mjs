import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { observerTrial } from "../../scripts/observer_trial.mjs";

test("a cadence arm refuses actual viewport drift before capture and restores state", async () => {
  const root = mkdtempSync(join(tmpdir(), "observer-trial-"));
  const calls = [],
    matrix = Array.from({ length: 16 }, (_, i) => (i % 5 === 0 ? 1 : 0));
  const url = "http://localhost:8892/live/looming/?check";
  const browser = {
    url,
    loadedSources: async (names) =>
      Object.fromEntries(
        names.map((name) => [
          name,
          readFileSync(
            new URL(`../../src/flymsg/viz_static/${name}`, import.meta.url),
            "utf8",
          ),
        ]),
      ),
    evaluate: async (expression) => {
      calls.push(expression);
      if (expression.includes("const api=window.flymsg"))
        return {
          url,
          visibility: "visible",
          before: { document_id: "a" },
          after: {
            document_id: "a",
            identity: { width: 640, height: 670, pixel_ratio: 1, samples: 4 },
          },
          frame_callbacks: 20,
          submitted_frames: 20,
          stats: "x · 0 loading · y",
          fidelity: { status: "ready", gpu_ready: true },
          resources: { gpu_resources: { complete: true } },
          immersive: false,
        };
      if (expression.includes("state:flymsg.diagnosticState()"))
        return {
          state: {},
          camera: matrix,
          projection: matrix,
          near: 0.1,
          far: 100,
        };
      if (expression.includes("flymsg.observerStatus().capture_running"))
        return null;
      return {};
    },
  };
  try {
    const out = join(root, "evidence"),
      camera = {
        camera_world: matrix,
        projection: matrix,
        viewport: { width: 1280, height: 670, pixel_ratio: 1, samples: 4 },
      };
    await assert.rejects(
      observerTrial(browser, out, { camera }),
      /viewport|quality/,
    );
    assert(!calls.some((c) => c.includes("flymsg.observerCapture(")));
    assert(!existsSync(join(out, "trial.json")));
    assert.equal(JSON.parse(readFileSync(join(out, "cleanup.json"))).ok, true);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
