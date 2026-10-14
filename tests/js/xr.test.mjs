import assert from "node:assert/strict";
import { test } from "node:test";
import {
  xrRequested,
  xrScaleForExtent,
  installXrObserver,
} from "../../src/flymsg/viz_static/xr.js";

class Vector {
  constructor(x = 0, y = 0, z = 0) {
    Object.assign(this, { x, y, z });
  }
  clone() { return new Vector(this.x, this.y, this.z); }
  copy(v) { return this.set(v.x, v.y, v.z); }
  set(x, y, z) { Object.assign(this, { x, y, z }); return this; }
  setScalar(n) { return this.set(n, n, n); }
}
class Emitter {
  constructor() { this.listeners = new Map(); }
  addEventListener(name, fn) { this.listeners.set(name, fn); }
  dispatch(name) { this.listeners.get(name)?.(); }
}
class Element extends Emitter {
  constructor() {
    super();
    this.children = [];
    this.hidden = false;
    this.disabled = false;
  }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); }
  setAttribute(k, v) { this[k] = v; }
  async click() { await this.listeners.get("click")?.(); }
}
function fixture({ supported = true, deny = false, xrAvailable = true } = {}) {
  const requestCalls = [];
  const system = xrAvailable
    ? {
        async isSessionSupported(mode) { assert.equal(mode, "immersive-vr"); return supported; },
        async requestSession(mode) {
          requestCalls.push(mode);
          if (deny) throw new Error("permission denied");
          const session = {
            async end() { renderer.xr.session = null; renderer.xr.dispatch("sessionend"); },
          };
          return session;
        },
      }
    : undefined;
  const documentRef = {
    body: new Element(),
    createElement: () => new Element(),
  };
  const renderer = {
    xr: Object.assign(new Emitter(), {
      enabled: false,
      isPresenting: false,
      session: null,
      setReferenceSpaceType(type) { assert.equal(type, "local"); },
      getSession() { return this.session; },
      async setSession(session) {
        this.session = session;
        this.isPresenting = true;
        this.dispatch("sessionstart");
      },
    }),
  };
  const root = { position: new Vector(4, 5, 6), scale: new Vector(1, 1, 1) };
  const camera = {
    near: 2, far: 500, updates: 0,
    updateProjectionMatrix() { this.updates++; },
  };
  const controls = { enabled: true };
  return {
    system, documentRef, renderer, root, camera, controls, requestCalls,
    options: {
      search: "?xr=1", renderer, root, camera, controls, extentUm: 1200,
      documentRef, xrSystem: system,
    },
  };
}

test("XR opt-in defaults off, and display scale checks its units", () => {
  for (const url of ["", "?xr=0", "?chrome=0", "?xr=true"])
    assert.equal(xrRequested(url), false);
  assert.equal(xrRequested("?t=120&xr=1"), true);
  assert.equal(xrScaleForExtent(1200), 0.001);
  assert.throws(() => xrScaleForExtent(0), RangeError);
  assert.throws(() => xrScaleForExtent(Infinity), RangeError);
  assert.throws(() => xrScaleForExtent(4, NaN), RangeError);
});

test("ordinary viewer has no added UI, XR side effects or API calls", async () => {
  const f = fixture();
  const result = await installXrObserver({ ...f.options, search: "?t=120" });
  assert.equal(result.available, false);
  assert.equal(f.documentRef.body.children.length, 0);
  assert.equal(f.renderer.xr.enabled, false);
  assert.deepEqual(f.requestCalls, []);
});

test("unsupported or missing XR leaves the desktop renderer alone", async () => {
  for (const options of [{ supported: false }, { xrAvailable: false }]) {
    const f = fixture(options);
    const result = await installXrObserver(f.options);
    assert.equal(result.available, false);
    assert.equal(f.renderer.xr.enabled, false);
    assert.equal(f.documentRef.body.children[0].children[0].hidden, true);
    assert.deepEqual(f.requestCalls, []);
  }
});

test("an explicit click enters; session end restores all model-view state", async () => {
  const f = fixture();
  let transitions = 0;
  const result = await installXrObserver({
    ...f.options, onTransition: () => { transitions++; },
  });
  assert.equal(result.available, true);
  assert.deepEqual(f.requestCalls, []);
  assert.equal(result.button.hidden, false);
  assert.equal(f.renderer.xr.enabled, true);
  await result.button.click();
  assert.deepEqual(f.requestCalls, ["immersive-vr"]);
  assert.equal(result.button.textContent, "Exit VR");
  assert.deepEqual(f.root.position, new Vector(0, 0, -2));
  assert.deepEqual(f.root.scale, new Vector(0.001, 0.001, 0.001));
  assert.equal(f.controls.enabled, false);
  assert.deepEqual([f.camera.near, f.camera.far], [0.05, 20]);
  assert.equal(transitions, 1);
  await result.button.click();
  assert.equal(result.button.textContent, "Enter VR");
  assert.deepEqual(f.root.position, new Vector(4, 5, 6));
  assert.deepEqual(f.root.scale, new Vector(1, 1, 1));
  assert.deepEqual([f.camera.near, f.camera.far], [2, 500]);
  assert.equal(f.controls.enabled, true);
  assert.equal(transitions, 2);
});

test("permission denial is explicit and does not modify the scene", async () => {
  const f = fixture({ deny: true });
  const result = await installXrObserver(f.options);
  await result.button.click();
  assert.match(result.status.textContent, /session failed/);
  assert.equal(result.button.disabled, false);
  assert.deepEqual(f.root.position, new Vector(4, 5, 6));
  assert.equal(f.controls.enabled, true);
});
