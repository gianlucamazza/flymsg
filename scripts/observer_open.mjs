import { observerTarget, localObserver } from "./observer_cdp.mjs";
const [endpoint, url, closeId] = process.argv.slice(2);
try {
  const result = await observerTarget(endpoint, url, closeId);
  if (!closeId) {
    const page = await localObserver(endpoint, result.targetId);
    try {
      await page.command("Page.bringToFront");
    } finally {
      page.close();
    }
  }
  console.log(JSON.stringify(result));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
