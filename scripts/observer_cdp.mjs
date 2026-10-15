// Explicit local diagnostic target; no browser discovery or unrelated tab access.
export async function localObserver(endpoint, targetId) {
  if (!["localhost", "127.0.0.1"].includes(new URL(endpoint).hostname))
    throw Error("Local CDP endpoint required");
  const target = (
    await (await fetch(new URL("/json/list", endpoint))).json()
  ).find((t) => t.id === targetId);
  if (
    !target?.url.startsWith("http://localhost:") ||
    !new URL(target.url).searchParams.has("check")
  )
    throw Error("Explicit local ?check target required");
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  let id = 0;
  const pending = new Map();
  const listeners = new Map();
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    pending.get(message.id)?.(message);
    for (const listener of listeners.get(message.method) ?? [])
      listener(message.params);
  });
  ws.addEventListener("close", () => {
    for (const callback of pending.values())
      callback({ error: { message: "Diagnostic connection closed" } });
    pending.clear();
  });
  const command = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const request = ++id,
        timer = setTimeout(() => {
          pending.delete(request);
          reject(Error("Diagnostic timeout; no completed artifact"));
        }, 180000);
      pending.set(request, (message) => {
        clearTimeout(timer);
        pending.delete(request);
        if (message.error || message.result?.exceptionDetails)
          reject(Error(JSON.stringify(message)));
        else resolve(message.result);
      });
      try {
        ws.send(
          JSON.stringify({
            id: request,
            method,
            params,
          }),
        );
      } catch (error) {
        clearTimeout(timer);
        pending.delete(request);
        reject(error);
      }
    });
  const evaluate = async (expression) =>
    (
      await command("Runtime.evaluate", {
        expression,
        awaitPromise: true,
        returnByValue: true,
      })
    ).result.value;
  const loadedSources = async (names) => {
    const scripts = new Map();
    const listener = (params) => scripts.set(params.url, params.scriptId);
    listeners.set("Debugger.scriptParsed", new Set([listener]));
    try {
      await command("Debugger.enable");
      const result = {};
      for (const name of names) {
        const url = new URL(name, target.url).href,
          scriptId = scripts.get(url);
        if (!scriptId) throw Error(`Loaded module unavailable: ${name}`);
        result[name] = (
          await command("Debugger.getScriptSource", { scriptId })
        ).scriptSource;
      }
      return result;
    } finally {
      listeners.delete("Debugger.scriptParsed");
      await command("Debugger.disable");
    }
  };
  return {
    url: target.url,
    command,
    evaluate,
    loadedSources,
    close: () => ws.close(),
  };
}
