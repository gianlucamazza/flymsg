import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { observerOracle } from "../../scripts/observer_oracle.mjs";

test("oracle completes all stereo timestamps and retains repeated progress updates", async () => {
  const root = mkdtempSync(join(tmpdir(), "observer-oracle-"));
  const url = "http://localhost:8892/live/looming/?check";
  let captures = 0;
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
      if (expression.includes("const api=window.flymsg"))
        return {
          url,
          visibility: "visible",
          before: { document_id: "a" },
          after: { document_id: "a" },
          frame_callbacks: 20,
          submitted_frames: 20,
          stats: "x · 0 loading · y",
          fidelity: { status: "ready", gpu_ready: true },
          resources: { gpu_resources: { complete: true } },
        };
      if (expression.startsWith("flymsg.reference(")) {
        captures++;
        return {
          neurons: [{ k: 0 }],
          images: {
            colour: { sha256: "same" },
            packed_depth: { sha256: "same" },
            neuron_id: { sha256: "same", base64: "AQAAAA==" },
          },
        };
      }
      if (expression.startsWith("flymsg.desktopReference("))
        return {
          rgba: { sha256: "same" },
          samples: 4,
          projection: [1],
          camera_world: [1],
        };
      if (expression === "flymsg.gpuInventory()")
        return [{ spans: [{ source: "skeleton:0", first: 0, count: 2 }] }];
      if (expression.includes("const expected={}")) return { "skeleton:0": 2 };
      if (expression.includes("camera_world:flymsg.camera"))
        return { camera_world: Array(16).fill(1), projection: [1] };
      return {};
    },
  };
  try {
    const report = await observerOracle(browser, join(root, "evidence"));
    assert.equal(report.status, "pass");
    assert.equal(captures, 12);
    assert.equal(report.cases.length, 6);
    assert.equal(
      JSON.parse(readFileSync(join(root, "evidence/progress.json"))).cases
        .length,
      6,
    );
    assert.equal(
      JSON.parse(readFileSync(join(root, "evidence/cleanup.json"))).ok,
      true,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
