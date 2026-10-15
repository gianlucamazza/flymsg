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
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    pending.get(message.id)?.(message);
  });
  const evaluate = (expression) =>
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
        else resolve(message.result.result.value);
      });
      ws.send(
        JSON.stringify({
          id: request,
          method: "Runtime.evaluate",
          params: { expression, awaitPromise: true, returnByValue: true },
        }),
      );
    });
  return { url: target.url, evaluate, close: () => ws.close() };
}
