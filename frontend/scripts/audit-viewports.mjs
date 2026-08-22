#!/usr/bin/env node
/**
 * audit-viewports.mjs — NetGrid viewport regression audit.
 *
 * Drives a real headless Chrome (via raw CDP, zero npm dependencies) against
 * the running frontend and asserts that every page fits its viewport: no
 * element may poke past the right (or left) edge unless it lives inside an
 * `overflow-x` container (tables, charts) where scrolling is intentional.
 *
 * It checks every route at two viewports — 375px (mobile) and 1440px
 * (desktop) — logging in through the real login form first so the pages
 * render with the authenticated nav and real data. Id-bearing detail/edit
 * pages (e.g. /subscribers/1, /subscribers/1/edit) are discovered live from
 * the list pages, so the whole route tree is exercised without hardcoding
 * ids. Two extra guarantees per page: no element may poke past the viewport
 * unless it lives inside an overflow-x container, and horizontally
 * scrollable tables/charts must scroll inside their own cards — panning one
 * to its end must not move the page itself (scroll-position stability).
 * Screenshots of failing pages are written to the screenshot dir for the
 * nightly failure issue.
 *
 * With AUDIT_DIFF=1 the dashboard is additionally diffed against a pixel
 * baseline (AUDIT_BASELINE_DIR, default frontend/audit-baselines): created
 * when missing, refreshed on drift-only change, failing when more than
 * AUDIT_MAX_CHANGED_PIXELS (default 0.12) of pixels change. Baselines are
 * environment-specific (font rasterization differs across OSes), so CI
 * persists it as an artifact between nightly runs rather than committing it.
 *
 * Requires:
 *   - Node >= 22 (native fetch + WebSocket)
 *   - a Chrome/Chromium/Edge binary (auto-detected, or CHROME_PATH)
 *   - the frontend running at AUDIT_BASE_URL (default http://localhost:3000)
 *   - a seeded database with the dev admin (default superadmin/netgrid-admin)
 *
 * Usage:
 *   node frontend/scripts/audit-viewports.mjs
 *
 * Env:
 *   AUDIT_BASE_URL       frontend to audit          (default http://localhost:3000)
 *   AUDIT_USERNAME       login username             (default superadmin)
 *   AUDIT_PASSWORD       login password             (default netgrid-admin)
 *   AUDIT_VIEWPORTS      comma-separated widths     (default "375,1440")
 *   AUDIT_ROUTES         comma-separated paths      (default all known routes)
 *   AUDIT_SCREENSHOT_DIR dir for failure PNGs       (default os.tmpdir()/netgrid-viewport-audit)
 *   CHROME_PATH          explicit browser binary    (default: auto-detect)
 *
 * Exit code 0 = every page fits at every viewport; 1 = overflow found, a page
 * failed to render, login failed, or the detector self-test failed.
 */

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";

// 127.0.0.1 (not "localhost") so the browser never resolves to ::1 while
// the dev server listens on IPv4 only.
const BASE_URL = process.env.AUDIT_BASE_URL || "http://127.0.0.1:3000";
const USERNAME = process.env.AUDIT_USERNAME || "superadmin";
const PASSWORD = process.env.AUDIT_PASSWORD || "netgrid-admin";
const VIEWPORTS = (process.env.AUDIT_VIEWPORTS || "375,1440")
  .split(",")
  .map((s) => Number(s.trim()))
  .filter(Number.isFinite);
const SCREENSHOT_DIR =
  process.env.AUDIT_SCREENSHOT_DIR || path.join(os.tmpdir(), "netgrid-viewport-audit");

const ROUTES = [
  { path: "/", settle: 2500 }, // dashboard: charts + polling need a beat
  { path: "/subscribers", settle: 900 },
  { path: "/plans", settle: 900 },
  { path: "/invoices", settle: 900 },
  { path: "/nas-devices", settle: 900 },
  { path: "/sessions", settle: 900 },
  { path: "/admins", settle: 900 },
  { path: "/roles", settle: 900 },
  { path: "/audit-logs", settle: 900 },
  { path: "/subscribers/new", settle: 900 },
  { path: "/plans/new", settle: 900 },
  { path: "/nas-devices/new", settle: 900 },
  { path: "/admins/new", settle: 900 },
  { path: "/roles/new", settle: 900 },
];
const ROUTES_FILTERED = process.env.AUDIT_ROUTES
  ? ROUTES.filter((r) => process.env.AUDIT_ROUTES.split(",").map((s) => s.trim()).includes(r.path))
  : ROUTES;

/**
 * Dynamic (id-bearing) routes are discovered live: right after a list page
 * is audited, the first link matching `selector` is read and `transform`
 * derives the target path, so the audit exercises real detail/edit pages
 * without hardcoding ids. Skipped silently when a page has no rows.
 */
// Selectors are scoped to the list <table> so header action buttons (e.g.
// the "New subscriber" link at /subscribers/new) don't get mistaken for
// row links. `marker` is a page expression that must be truthy after render,
// so a discovered link that 404s (or renders an empty shell) fails instead
// of passing silently.
const DISCOVERY = [
  {
    after: "/subscribers",
    selector: `table a[href^="/subscribers/"]`,
    transform: (h) => h,
    settle: 1200,
    marker: `!!document.querySelector('table')`,
  },
  {
    after: "/subscribers",
    selector: `table a[href^="/subscribers/"]`,
    transform: (h) => `${h}/edit`,
    settle: 1200,
    marker: `document.body.innerText.includes('Edit subscriber')`,
  },
  {
    after: "/plans",
    selector: `table a[href^="/plans/"]`,
    transform: (h) => h,
    settle: 1200,
    marker: `document.body.innerText.includes('Edit ')`,
  },
  {
    after: "/invoices",
    selector: `table a[href^="/invoices/"]`,
    transform: (h) => h,
    settle: 1200,
    marker: `document.body.innerText.includes('Invoice #')`,
  },
  {
    after: "/nas-devices",
    selector: `table a[href^="/nas-devices/"]`,
    transform: (h) => h,
    settle: 1200,
    marker: `document.body.innerText.includes('Edit ')`,
  },
  {
    after: "/admins",
    selector: `table a[href^="/admins/"]`,
    transform: (h) => h,
    settle: 1200,
    marker: `document.body.innerText.includes('Edit ')`,
  },
  {
    after: "/roles",
    selector: `table a[href^="/roles/"]`,
    transform: (h) => h,
    settle: 1200,
    marker: `document.body.innerText.includes('Edit ')`,
  },
];

const HEIGHT = 900;

/** In-page detector: returns { pageOverflow, offenders } for the current viewport. */
const AUDIT_FN = `(() => {
  const vw = document.documentElement.clientWidth;
  const docW = document.documentElement.scrollWidth;
  const all = document.querySelectorAll('*');
  const offenders = [];
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.right <= vw + 1 && r.left >= -1) continue;
    // Inside an overflow-x container (tables, charts) scrolling is intentional.
    let p = el.parentElement, contained = false;
    while (p) {
      const s = getComputedStyle(p);
      if (/(auto|scroll|hidden)/.test(s.overflowX)) { contained = true; break; }
      p = p.parentElement;
    }
    if (contained) continue;
    offenders.push({ el, right: r.right, left: r.left, w: r.width });
  }
  // Report only the outermost culprits so a broken container is listed once,
  // not once per descendant.
  const roots = offenders.filter(
    (o) => !offenders.some((x) => x !== o && x.el.contains(o.el))
  );
  return {
    pageOverflow: docW > vw + 1,
    offenders: roots.map((o) => ({
      tag: o.el.tagName,
      cls: String(o.el.className).slice(0, 60),
      id: o.el.id || null,
      right: Math.round(o.right),
      left: Math.round(o.left),
      w: Math.round(o.w),
    })),
  };
})()`;

/**
 * In-page scroll-stability probe: every horizontally scrollable element must
 * scroll inside its own card — panning it to the far edge must not move the
 * page itself — and the page must never arrive horizontally scrolled. Runs
 * after AUDIT_FN and restores every scrollLeft it touches.
 */
const SCROLL_PROBE = `(() => {
  const scrollX0 = window.scrollX;
  const targets = [];
  for (const el of document.querySelectorAll('*')) {
    const s = getComputedStyle(el);
    if (s.overflowX !== 'auto' && s.overflowX !== 'scroll') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (el.scrollWidth <= el.clientWidth + 1) continue; // not actually scrollable
    if (r.right > document.documentElement.clientWidth + 1) continue; // offender territory
    targets.push(el);
  }
  const results = targets.map((el) => {
    // Assign the max scroll offset; the browser clamps it to
    // scrollWidth - clientWidth. "took" means the pan actually moved the
    // container (it is genuinely scrollable and accepts a scroll).
    el.scrollLeft = el.scrollWidth;
    const took = el.scrollLeft > 0;
    const pageMoved = window.scrollX !== scrollX0;
    el.scrollLeft = 0;
    return {
      id: el.id || null,
      cls: String(el.className).slice(0, 40),
      took,
      pageMoved,
    };
  });
  return {
    scrollX0,
    finalScrollX: window.scrollX,
    containerCount: targets.length,
    results,
  };
})()`;

// --- pixel-diff baseline (zero-dependency PNG decode/encode) -------------------
// A strict pixel baseline would false-fail across operating systems (font
// rasterization differs between Windows and Linux Chrome), so the baseline is
// captured and compared in the same environment: CI persists it as a GitHub
// artifact between nightly runs. The dashboard is live data, so the diff is
// thresholded — small perpetual drift (ticking timestamps, durations) refreshes
// the baseline, and only a change above AUDIT_MAX_CHANGED_PIXELS fails.

const BASELINE_DIR =
  process.env.AUDIT_BASELINE_DIR ||
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "audit-baselines");
const DIFF_ENABLED = process.env.AUDIT_DIFF === "1";
const MAX_CHANGED = Number(process.env.AUDIT_MAX_CHANGED_PIXELS || 0.12);
// Below this fraction the change is treated as live-data drift and the
// baseline is refreshed; between it and the threshold it's reported only.
const STABLE_FACTOR = 0.5;
const PER_PIXEL_DIFF = 24; // summed channel difference that counts a pixel

const PNG_SIG = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

function crc32(buf) {
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    crc ^= buf[i];
    for (let j = 0; j < 8; j++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const out = Buffer.alloc(12 + data.length);
  out.writeUInt32BE(data.length, 0);
  out.write(type, 4, "ascii");
  data.copy(out, 8);
  out.writeUInt32BE(crc32(out.subarray(4, 8 + data.length)), 8 + data.length);
  return out;
}

function writePng(width, height, rgba) {
  const stride = width * 4;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0; // filter: None
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  return Buffer.concat([
    PNG_SIG,
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", zlib.deflateSync(raw)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function readPng(buffer) {
  if (!buffer.subarray(0, 8).equals(PNG_SIG)) throw new Error("not a PNG");
  let pos = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  const idat = [];
  while (pos < buffer.length) {
    const len = buffer.readUInt32BE(pos);
    const type = buffer.toString("ascii", pos + 4, pos + 8);
    const data = buffer.subarray(pos + 8, pos + 8 + len);
    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
    } else if (type === "IDAT") {
      idat.push(data);
    } else if (type === "IEND") {
      break;
    }
    pos += 12 + len;
  }
  if (!width || !height) throw new Error("PNG has no IHDR");
  if (bitDepth !== 8) throw new Error(`unsupported bit depth ${bitDepth}`);
  let channels;
  if (colorType === 6) channels = 4; // RGBA
  else if (colorType === 2) channels = 3; // RGB
  else if (colorType === 0) channels = 1; // grayscale
  else throw new Error(`unsupported color type ${colorType}`);
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = width * channels;
  const out = Buffer.alloc(height * stride);
  let prev = Buffer.alloc(stride);
  let p = 0;
  for (let y = 0; y < height; y++) {
    const filter = raw[p++];
    const line = out.subarray(y * stride, (y + 1) * stride);
    const src = raw.subarray(p, p + stride);
    p += stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= channels ? line[x - channels] : 0;
      const b = prev[x];
      const c = x >= channels ? prev[x - channels] : 0;
      let v = src[x];
      if (filter === 1) v = (v + a) & 0xff; // Sub
      else if (filter === 2) v = (v + b) & 0xff; // Up
      else if (filter === 3) v = (v + ((a + b) >> 1)) & 0xff; // Average
      else if (filter === 4) {
        // Paeth
        const pa = Math.abs(b - c);
        const pb = Math.abs(a - c);
        const pc = Math.abs(a + b - 2 * c);
        const pr = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
        v = (v + pr) & 0xff;
      }
      line[x] = v;
    }
    prev = line;
  }
  return { width, height, channels, data: out };
}

function pixelChanged(a, b, i, j) {
  return (
    Math.abs(a[i] - b[j]) +
      Math.abs(a[i + 1] - b[j + 1]) +
      Math.abs(a[i + 2] - b[j + 2]) >
    PER_PIXEL_DIFF
  );
}

function diffPixels(a, b) {
  const w = Math.min(a.width, b.width);
  const h = Math.min(a.height, b.height);
  const blocks = 24;
  const bw = Math.max(1, Math.ceil(w / blocks));
  const bh = Math.max(1, Math.ceil(h / blocks));
  const blockChanged = new Array(blocks * blocks).fill(0);
  let changed = 0;
  let sumDiff = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const ai = (y * a.width + x) * a.channels;
      const bi = (y * b.width + x) * b.channels;
      const d =
        Math.abs(a.data[ai] - b.data[bi]) +
        Math.abs(a.data[ai + 1] - b.data[bi + 1]) +
        Math.abs(a.data[ai + 2] - b.data[bi + 2]);
      sumDiff += d;
      if (d > PER_PIXEL_DIFF) {
        changed++;
        const bx = Math.min(blocks - 1, Math.floor(x / bw));
        const by = Math.min(blocks - 1, Math.floor(y / bh));
        blockChanged[by * blocks + bx] = 1;
      }
    }
  }
  return {
    width: w,
    height: h,
    changedPixels: changed,
    totalPixels: w * h,
    fraction: w * h ? changed / (w * h) : 1,
    meanAbsDiff: (w * h ? sumDiff / (w * h) : 0) / 3,
    blockRows: Array.from({ length: blocks }, (_, by) =>
      Array.from({ length: blocks }, (_, bx) => (blockChanged[by * blocks + bx] ? "#" : ".")).join("")
    ),
  };
}

function makeOverlay(a, b, w, h) {
  const out = Buffer.alloc(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const ai = (y * a.width + x) * a.channels;
      const bi = (y * b.width + x) * b.channels;
      const oi = (y * w + x) * 4;
      if (pixelChanged(a.data, b.data, ai, bi)) {
        out[oi] = 239;
        out[oi + 1] = 68;
        out[oi + 2] = 68;
        out[oi + 3] = 255; // red highlight
      } else {
        out[oi] = a.data[ai];
        out[oi + 1] = a.data[ai + 1];
        out[oi + 2] = a.data[ai + 2];
        out[oi + 3] = a.channels > 3 ? a.data[ai + 3] : 255;
      }
    }
  }
  return out;
}

// Capture the dashboard at this viewport and diff against the persisted
// baseline: create it when missing, refresh on drift-only change, fail when
// the change exceeds the threshold. Returns whether the baseline check passed.
async function baselineCheck(send, vw) {
  const file = path.join(BASELINE_DIR, `dashboard-${vw}.png`);
  fs.mkdirSync(BASELINE_DIR, { recursive: true });
  const where = await evalJs(send, `JSON.stringify({ path: location.pathname, hasNav: !!document.querySelector('nav'), text: document.body.innerText.slice(0, 60) })`);
  console.log(`baseline  capturing ${vw}px at ${where}`);
  const shot = await send("Page.captureScreenshot", { format: "png" });
  const current = Buffer.from(shot.data, "base64");
  if (!fs.existsSync(file)) {
    fs.writeFileSync(file, current);
    console.log(`baseline  created ${file}`);
    return true;
  }
  const a = readPng(current);
  const b = readPng(fs.readFileSync(file));
  const d = diffPixels(a, b);
  const pct = (d.fraction * 100).toFixed(2);
  console.log(`baseline  ${vw}px diff ${pct}% (mean ${d.meanAbsDiff.toFixed(2)}, ${d.changedPixels}/${d.totalPixels} px)`);
  console.log(`baseline  changed regions (24-col grid):`);
  for (const row of d.blockRows) console.log(`baseline    ${row}`);
  if (d.fraction < MAX_CHANGED * STABLE_FACTOR) {
    fs.writeFileSync(file, current);
    console.log(`baseline  refreshed (drift only)`);
    return true;
  }
  if (d.fraction >= MAX_CHANGED) {
    const overlay = makeOverlay(a, b, d.width, d.height);
    const diffFile = path.join(BASELINE_DIR, `dashboard-${vw}-diff.png`);
    fs.writeFileSync(diffFile, writePng(d.width, d.height, overlay));
    fs.writeFileSync(path.join(BASELINE_DIR, `dashboard-${vw}-current.png`), current);
    failures.push({
      vw,
      path: `dashboard pixel baseline (${vw}px)`,
      error: `${pct}% pixels changed (threshold ${(MAX_CHANGED * 100).toFixed(0)}%) — see ${diffFile}`,
    });
    console.log(`baseline  FAIL — ${pct}% changed`);
    return false;
  }
  console.log(`baseline  drift ${pct}% (below ${(MAX_CHANGED * 100).toFixed(0)}% threshold; not refreshing)`);
  return true;
}

// --- chrome discovery --------------------------------------------------------

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  process.env.PUPPETEER_EXECUTABLE_PATH,
  // Linux (GitHub Actions runners ship Google Chrome)
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
  // macOS
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  // Windows
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
].filter(Boolean);

function findChrome() {
  for (const candidate of CHROME_CANDIDATES) {
    try {
      fs.accessSync(candidate);
      return candidate;
    } catch {
      /* keep looking */
    }
  }
  return null;
}

// --- chrome lifecycle --------------------------------------------------------

function launchChrome(binary) {
  const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "netgrid-audit-"));
  const args = [
    "--headless=new",
    "--remote-debugging-port=0", // random port; discovered via DevToolsActivePort
    `--user-data-dir=${profileDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-gpu",
    "--disable-background-networking",
    "about:blank",
  ];
  const child = spawn(binary, args, {
    stdio: "ignore",
    detached: process.platform !== "win32",
  });
  return { child, profileDir };
}

function killChrome(child) {
  try {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"]);
    } else {
      process.kill(-child.pid, "SIGKILL");
    }
  } catch {
    /* already gone */
  }
}

async function waitForDebugPort(profileDir) {
  const portFile = path.join(profileDir, "DevToolsActivePort");
  for (let i = 0; i < 60; i++) {
    try {
      const [port] = fs.readFileSync(portFile, "utf8").trim().split("\n");
      if (port) return Number(port);
    } catch {
      /* not written yet */
    }
    await sleep(250);
  }
  throw new Error("Chrome never opened its debugging port");
}

// --- CDP plumbing ------------------------------------------------------------

function connect(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => resolve(ws);
    ws.onerror = () => reject(new Error("could not connect to " + wsUrl));
  });
}

function cdpClient(ws) {
  let nextId = 1;
  const pending = new Map();
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
    }
  };
  return (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- page driving ------------------------------------------------------------

async function evalJs(send, expression) {
  const { result, exceptionDetails } = await send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (exceptionDetails) {
    throw new Error("page eval failed: " + JSON.stringify(exceptionDetails).slice(0, 300));
  }
  return result.value;
}

async function waitFor(send, expression, timeoutMs, label) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      if (await evalJs(send, expression)) return true;
    } catch {
      /* page mid-navigation; retry */
    }
    await sleep(250);
  }
  throw new Error(`timed out waiting for ${label}`);
}

async function login(send) {
  await send("Page.navigate", { url: `${BASE_URL}/login` });
  await waitFor(send, `document.readyState === 'complete'`, 20000, "login page load");
  await sleep(500);
  const filled = await evalJs(
    send,
    `(() => {
      const setVal = (el, v) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, v);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      };
      const user = document.querySelector('input[type="text"]') || document.querySelector('input:not([type="password"])');
      const pass = document.querySelector('input[type="password"]');
      if (!user || !pass) return { ok: false, why: 'login inputs not found' };
      setVal(user, ${JSON.stringify(USERNAME)});
      setVal(pass, ${JSON.stringify(PASSWORD)});
      const btn = Array.from(document.querySelectorAll('button')).find((b) => /sign in/i.test(b.textContent || ''));
      if (!btn) return { ok: false, why: 'sign-in button not found' };
      btn.click();
      return { ok: true };
    })()`
  );
  if (!filled.ok) throw new Error("login failed: " + filled.why);
  // After the (client-side) sign-in the dashboard renders its nav inside <main>.
  await waitFor(send, `!!document.querySelector('nav')`, 15000, "post-login navigation");
}

async function auditRoute(send, route) {
  await send("Page.navigate", { url: `${BASE_URL}${route.path}` });
  await waitFor(
    send,
    `document.readyState === 'complete' && !!document.querySelector('main')`,
    20000,
    `render of ${route.path}`
  );
  await sleep(route.settle);
  return evalJs(send, AUDIT_FN);
}

// Audit one route at one viewport: record the outcome, write a screenshot on
// failure, and return whether the page is clean. Failed renders are recorded
// but don't abort the walk (the next page may be fine and still worth seeing).
let checked = 0;
async function checkRoute(send, vw, route) {
  let result;
  try {
    result = await auditRoute(send, route);
    result.scroll = await evalJs(send, SCROLL_PROBE);
    if (route.marker && !(await evalJs(send, route.marker))) {
      throw new Error("page rendered without expected content");
    }
  } catch (err) {
    const entry = { vw, path: route.path, error: err.message };
    failures.push(entry);
    const file = path.join(SCREENSHOT_DIR, `${vw}-${route.path.replaceAll("/", "_")}.png`);
    try {
      await saveScreenshot(send, file);
      entry.screenshot = file;
    } catch {
      /* best effort */
    }
    console.log(`view ${vw}px  ${route.path}  FAIL (${err.message})`);
    checked += 1;
    return false;
  }
  const scroll = result.scroll;
  const scrollOk =
    scroll.scrollX0 === 0 &&
    scroll.finalScrollX === 0 &&
    scroll.results.every((r) => r.took && !r.pageMoved);
  const ok = !result.pageOverflow && result.offenders.length === 0 && scrollOk;
  if (!ok) {
    const entry = { vw, path: route.path, result };
    if (!scrollOk) entry.scroll = scroll;
    failures.push(entry);
    const file = path.join(SCREENSHOT_DIR, `${vw}-${route.path.replaceAll("/", "_")}.png`);
    try {
      await saveScreenshot(send, file);
      entry.screenshot = file;
    } catch {
      /* best effort */
    }
  }
  results.push({ vw, path: route.path, ok });
  const reason = !ok
    ? result.pageOverflow || result.offenders.length > 0
      ? `${result.offenders.length} offender(s)`
      : "scroll instability"
    : "";
  console.log(`view ${vw}px  ${route.path}  ${ok ? "OK" : `FAIL (${reason})`}`);
  checked += 1;
  return ok;
}

async function saveScreenshot(send, file) {
  const shot = await send("Page.captureScreenshot", { format: "png" });
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, Buffer.from(shot.data, "base64"));
}

// --- detector self-test ------------------------------------------------------
// A detector that never fires would make nightly pass forever even if the
// audit silently broke. Inject a genuinely overflowing element on the last
// page and require the detector to catch it.
async function selfTest(send) {
  // Overflow detector: inject a genuinely overflowing element and require the
  // detector to flag it.
  const injected = await evalJs(
    send,
    `(() => {
      const probe = document.createElement('div');
      probe.id = 'audit-probe';
      probe.className = 'audit-probe';
      probe.style.cssText = 'position:fixed;left:0;top:0;width:99999px;height:10px;';
      document.body.appendChild(probe);
      return document.getElementById('audit-probe') !== null;
    })()`
  );
  if (!injected) throw new Error("self-test: could not inject probe");
  const result = await evalJs(send, AUDIT_FN);
  const caught = result.offenders.some(
    (o) => o.cls.includes("audit-probe") || o.id === "audit-probe"
  );
  if (!caught) {
    throw new Error(
      "self-test: overflow detector did not flag the injected overflow — audit is broken"
    );
  }
  // Scroll-stability probe: inject a genuinely scrollable container and require
  // the probe to find it, pan it, and classify it as stable (page unmoved). A
  // probe that silently found zero containers would make the scroll check pass
  // forever.
  const scrollOk = await evalJs(
    send,
    `(() => {
      const wrap = document.createElement('div');
      wrap.id = 'audit-scroll-probe';
      wrap.style.cssText =
        'position:fixed;left:8px;top:8px;width:200px;height:20px;overflow-x:auto;background:#000;';
      const inner = document.createElement('div');
      inner.style.cssText = 'width:2000px;height:1px;';
      wrap.appendChild(inner);
      document.body.appendChild(wrap);
      const res = ${SCROLL_PROBE};
      wrap.remove();
      const hit = res.results.find((r) => r.id === 'audit-scroll-probe');
      return !!hit && hit.took && !hit.pageMoved;
    })()`
  );
  if (!scrollOk) {
    throw new Error(
      "self-test: scroll probe did not find/classify the injected scrollable — audit is broken"
    );
  }
  await evalJs(
    send,
    `document.getElementById('audit-probe')?.remove(); true`
  );
}

// --- main --------------------------------------------------------------------

const chromeBinary = findChrome();
if (!chromeBinary) {
  console.error("FAIL  no Chrome/Chromium/Edge binary found (set CHROME_PATH)");
  process.exit(1);
}

const { child, profileDir } = launchChrome(chromeBinary);
let pageWs = null;
const failures = [];
const results = [];

try {
  const port = await waitForDebugPort(profileDir);
  const target = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {
    method: "PUT",
  }).then((r) => r.json());
  pageWs = await connect(target.webSocketDebuggerUrl);
  const send = cdpClient(pageWs);
  await send("Page.enable");
  await send("Runtime.enable");

  console.log(`== NetGrid viewport audit ==`);
  console.log(`base:   ${BASE_URL}`);
  console.log(`chrome: ${chromeBinary}`);
  console.log(`views:  ${VIEWPORTS.join("x900, ")}x900  routes: ${ROUTES_FILTERED.length}`);

  for (let vi = 0; vi < VIEWPORTS.length; vi++) {
    const vw = VIEWPORTS[vi];
    await send("Emulation.setDeviceMetricsOverride", {
      width: vw,
      height: HEIGHT,
      deviceScaleFactor: 1,
      mobile: false,
    });
    if (vi === 0) {
      // Audit the login page itself, then authenticate once for every route
      // and viewport (the session cookie persists across navigations).
      await send("Page.navigate", { url: `${BASE_URL}/login` });
      await waitFor(send, `document.readyState === 'complete'`, 20000, "login page load");
      await sleep(500);
      const loginResult = await evalJs(send, AUDIT_FN);
      const routeOk = !loginResult.pageOverflow && loginResult.offenders.length === 0;
      if (!routeOk) failures.push({ vw, path: "/login", result: loginResult });
      console.log(
        `view ${vw}px  /login  ${routeOk ? "OK" : `FAIL (${loginResult.offenders.length} offender(s))`}`
      );
      await login(send);
    }

    // Queue-based walk: static routes first, then any detail/edit routes
    // discovered from the list pages, so id-bearing pages get audited too.
    const visited = new Set();
    const queue = ROUTES_FILTERED.map((r) => ({ ...r }));
    while (queue.length > 0) {
      const route = queue.shift();
      if (visited.has(route.path)) continue;
      visited.add(route.path);
      const ok = await checkRoute(send, vw, route);
      // Pixel-diff baseline for the dashboard, captured at desktop width
      // (opt-in via AUDIT_DIFF; CI persists the baseline between runs). Runs
      // even if the page check failed — a broken dashboard should fail the
      // pixel diff too, not hide behind the layout pass.
      if (DIFF_ENABLED && vw === 1440 && route.path === "/") {
        await baselineCheck(send, vw);
      }
      if (!ok) continue; // don't discover children from a page that failed
      for (const d of DISCOVERY) {
        if (d.after !== route.path) continue;
        const href = await evalJs(
          send,
          `(() => { const a = document.querySelector(${JSON.stringify(d.selector)}); return a ? a.getAttribute('href') : null; })()`
        );
        if (!href) continue;
        const target = d.transform(href);
        if (!visited.has(target) && !queue.some((q) => q.path === target)) {
          queue.push({ path: target, settle: d.settle, marker: d.marker });
        }
      }
    }
  }

  // Detector sanity check on the last rendered page.
  await selfTest(send);
  console.log(`self-test detector  OK`);
} catch (err) {
  failures.push({ fatal: err.message });
  console.error(`FATAL  ${err.message}`);
} finally {
  try {
    pageWs?.close();
  } catch {
    /* ignore */
  }
  killChrome(child);
  try {
    fs.rmSync(profileDir, { recursive: true, force: true });
  } catch {
    /* ignore */
  }
}

console.log("");
if (failures.length > 0) {
  console.log(`FAIL — ${failures.length} issue(s)`);
  for (const f of failures) {
    if (f.fatal) {
      console.log(`  fatal: ${f.fatal}`);
      continue;
    }
    const offenders = f.result?.offenders ?? [];
    console.log(`  view ${f.vw}px  ${f.path}  ${f.error ? f.error : `${offenders.length} offender(s)`}`);
    for (const o of offenders.slice(0, 6)) {
      const id = o.id ? ` id="${o.id}"` : "";
      console.log(`    <${o.tag}${id} class="${o.cls}"> right=${o.right} w=${o.w}${o.left < 0 ? ` left=${o.left}` : ""}`);
    }
    if (f.scroll) {
      const unstable = f.scroll.results.filter((r) => !r.took || r.pageMoved);
      console.log(
        `    scroll: scrollX0=${f.scroll.scrollX0} final=${f.scroll.finalScrollX} ` +
          `containers=${f.scroll.containerCount} unstable=${unstable.length}`
      );
      for (const u of unstable.slice(0, 4)) {
        const id = u.id ? ` id="${u.id}"` : "";
        console.log(`      <${u.cls}${id}> took=${u.took} pageMoved=${u.pageMoved}`);
      }
    }
    if (f.screenshot) console.log(`    screenshot: ${f.screenshot}`);
  }
  process.exit(1);
}
console.log(
  `PASS — ${VIEWPORTS.length} viewport(s) × ${checked} page check(s) clean (overflow + scroll stability), detector verified`
);
