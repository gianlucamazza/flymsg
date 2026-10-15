import assert from "node:assert/strict";
import { test } from "node:test";
import { localObserver } from "../../scripts/observer_cdp.mjs";

test("diagnostics restrict the target and read loaded sources, disabling debugger on failure", async (t) => {
  const commands = [];
  const url = "http://localhost:8901/live/looming/?check";
  t.mock.method(globalThis, "fetch", async () => ({
    json: async () => [
      {
        id: "58",
        url,
        webSocketDebuggerUrl: "ws://localhost:40623/devtools/page/58",
      },
      { id: "other", url: "https://example.org" },
    ],
  }));
  class Socket extends EventTarget {
    constructor() {
      super();
      queueMicrotask(() => this.dispatchEvent(new Event("open")));
    }
    send(text) {
      const { id, method } = JSON.parse(text);
      commands.push(method);
      const emit = (message) => {
        const event = new Event("message");
        event.data = JSON.stringify(message);
        this.dispatchEvent(event);
      };
      queueMicrotask(() => {
        if (method === "Debugger.enable")
          emit({
            method: "Debugger.scriptParsed",
            params: {
              url: new URL("main.js", url).href,
              scriptId: "real-loaded-script",
            },
          });
        emit({
          id,
          result:
            method === "Debugger.getScriptSource"
              ? { scriptSource: "export const original = true;" }
              : {},
        });
      });
    }
    close() {
      this.dispatchEvent(new Event("close"));
    }
  }
  const originalSocket = globalThis.WebSocket;
  globalThis.WebSocket = Socket;
  t.after(() => {
    globalThis.WebSocket = originalSocket;
  });
  await assert.rejects(localObserver("https://example.org", "58"), /Local CDP/);
  await assert.rejects(
    localObserver("http://localhost:40623", "other"),
    /Explicit local/,
  );
  const browser = await localObserver("http://localhost:40623", "58");
  try {
    assert.deepEqual(await browser.loadedSources(["main.js"]), {
      "main.js": "export const original = true;",
    });
    assert.equal(commands.at(-1), "Debugger.disable");
    await assert.rejects(
      browser.loadedSources(["missing.js"]),
      /Loaded module unavailable/,
    );
    assert.equal(commands.at(-1), "Debugger.disable");
  } finally {
    browser.close();
  }
});
