import { frozenCameraProfile } from "../../scripts/observer-camera.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { observerOracle, oracleFlags } from "../../scripts/observer_oracle.mjs";

test("oracle completes all stereo timestamps and retains repeated progress updates", async () => {
  const root = mkdtempSync(join(tmpdir(), "observer-oracle-"));
  const url = "http://localhost:8892/live/looming/?check";
  const identity = Array.from({ length: 16 }, (_, i) => (i % 5 === 0 ? 1 : 0));
  const frozen = {
    camera_world: [...identity],
    projection: [...identity],
    viewport: { width: 128, height: 128, pixel_ratio: 1, samples: 4 },
  };
  frozen.camera_world[12] = 10;
  frozen.camera_world[13] = 2;
  frozen.camera_world[14] = 3;
  const observed = {
    camera_world: [...frozen.camera_world],
    projection: [...frozen.projection],
  };
  observed.camera_world[12] += 1e-13;
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
          after: {
            document_id: "a",
            identity: { width: 128, height: 128, pixel_ratio: 1, samples: 4 },
          },
          frame_callbacks: 20,
          submitted_frames: 20,
          stats: "x · 0 loading · y",
          fidelity: { status: "ready", gpu_ready: true },
          resources: { gpu_resources: { complete: true } },
        };
      if (expression.startsWith("flymsg.reference(")) {
        const options = JSON.parse(
          expression.slice("flymsg.reference(".length, -1),
        );
        const expected = [...frozen.camera_world];
        const eye = Math.floor(captures / 2) % 2 === 0 ? -1 : 1;
        expected[12] +=
          eye * 0.015 * Math.hypot(expected[12], expected[13], expected[14]);
        assert.deepEqual(options.cameraWorld, expected);
        assert.deepEqual(options.projection, frozen.projection);
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
      if (expression.includes("camera_world:flymsg.camera")) return observed;
      return {};
    },
  };
  try {
    const report = await observerOracle(browser, join(root, "evidence"), {
      cameraProfile: frozen,
    });
    assert.equal(report.camera_source, "frozen-profile");
    assert.deepEqual(
      JSON.parse(readFileSync(join(root, "evidence/camera.json"))),
      frozen,
    );
    assert.notDeepEqual(
      JSON.parse(readFileSync(join(root, "evidence/camera-observed.json")))
        .camera_world,
      frozen.camera_world,
    );
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

test("oracle freezes declared matrices before capture and refuses viewport drift", () => {
  const observed = {
    camera_world: Array(16).fill(1),
    projection: Array(16).fill(2),
  };
  const viewport = { width: 1280, height: 670, pixel_ratio: 1, samples: 4 };
  const first = frozenCameraProfile(observed, null, viewport);
  const different = structuredClone(observed);
  different.camera_world[0] += 1e-13;
  assert.notDeepEqual(different.camera_world, first.camera_world);
  assert.deepEqual(frozenCameraProfile(different, first, viewport), first);
  for (const [key, value] of Object.entries({
    width: 640,
    height: 335,
    pixel_ratio: 2,
    samples: 0,
  }))
    assert.throws(
      () =>
        frozenCameraProfile(different, first, { ...viewport, [key]: value }),
      /viewport|quality/,
    );
  const bad = structuredClone(first);
  bad.projection[0] = NaN;
  assert.throws(() => frozenCameraProfile(observed, bad, viewport), /matrix/);
  observed.camera_world[0] = 100;
  assert.equal(first.camera_world[0], 1);
});
test("oracle CLI accepts explicit frozen camera and rejects ambiguous flags", () => {
  assert.deepEqual(
    oracleFlags(["--readback-only", "--camera-file", "camera.json"]),
    { readbackOnly: true, cameraFile: "camera.json" },
  );
  assert.deepEqual(oracleFlags([]), { readbackOnly: false, cameraFile: null });
  for (const flags of [
    ["--camera-file"],
    ["--camera-file", "--readback-only"],
    ["--unknown"],
    ["--readback-only", "--readback-only"],
  ])
    assert.throws(() => oracleFlags(flags), /flag/);
});
