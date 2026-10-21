// 把历书 HTML 截成 PNG。用 Node 版 Playwright，避免重复下载浏览器。
// 用法：node shot.mjs <html> <png> [width] [height]
// 需要能解析到 playwright 包：设 NODE_PATH，或用 PLAYWRIGHT_PKG 指定绝对路径。
// 若 playwright 版本对应的浏览器未下载，会自动回退到本地缓存里的任一 Chromium。
import { createRequire } from "node:module";
import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  const fallback = process.env.PLAYWRIGHT_PKG;
  if (!fallback) {
    console.error("找不到 playwright 包，请设置 NODE_PATH 或 PLAYWRIGHT_PKG");
    process.exit(2);
  }
  ({ chromium } = require(fallback));
}

function findLocalChromium() {
  const cache = join(homedir(), "Library", "Caches", "ms-playwright");
  if (!existsSync(cache)) return null;
  const dirs = readdirSync(cache)
    .filter((d) => d.startsWith("chromium-") && !d.includes("headless"))
    .sort()
    .reverse();
  for (const d of dirs) {
    const base = join(cache, d, "chrome-mac-x64");
    if (!existsSync(base)) continue;
    for (const app of readdirSync(base)) {
      if (!app.endsWith(".app")) continue;
      const bin = join(base, app, "Contents", "MacOS", app.replace(".app", ""));
      if (existsSync(bin)) return bin;
    }
  }
  return null;
}

const [, , htmlPath, pngPath, w = "1080", h = "1440"] = process.argv;
if (!htmlPath || !pngPath) {
  console.error("usage: node shot.mjs <html> <png> [w] [h]");
  process.exit(2);
}

async function launch() {
  try {
    return await chromium.launch();
  } catch {
    const exe = process.env.CHROMIUM_PATH || findLocalChromium();
    if (!exe) throw new Error("没有可用的 Chromium，请运行 playwright install chromium");
    return await chromium.launch({ executablePath: exe });
  }
}

const browser = await launch();
const page = await browser.newPage({
  viewport: { width: Number(w), height: Number(h) },
  deviceScaleFactor: 2,
});
await page.goto("file://" + htmlPath);
await page.waitForTimeout(450);
await page.screenshot({ path: pngPath, fullPage: false });
await browser.close();
console.log("ok " + pngPath);
