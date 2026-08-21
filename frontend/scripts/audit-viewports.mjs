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
 * render with the authenticated nav and real data. Screenshots of failing
 * pages are written to the screenshot dir for the nightly failure issue.
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
  { path: "/audit-logs", settle: 900 },
];
const ROUTES_FILTERED = process.env.AUDIT_ROUTES
  ? ROUTES.filter((r) => process.env.AUDIT_ROUTES.split(",").map((s) => s.trim()).includes(r.path))
  : ROUTES;

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
    throw new Error("self-test: detector did not flag the injected overflow — audit is broken");
  }
  await evalJs(send, `document.getElementById('audit-probe')?.remove(); true`);
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

    for (const route of ROUTES_FILTERED) {
      let result;
      try {
        result = await auditRoute(send, route);
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
        continue;
      }
      const ok = !result.pageOverflow && result.offenders.length === 0;
      if (!ok) {
        const entry = { vw, path: route.path, result };
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
      console.log(
        `view ${vw}px  ${route.path}  ${ok ? "OK" : `FAIL (${result.offenders.length} offender(s))`}`
      );
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
    if (f.screenshot) console.log(`    screenshot: ${f.screenshot}`);
  }
  process.exit(1);
}
console.log(
  `PASS — ${VIEWPORTS.length} viewport(s) × ${ROUTES_FILTERED.length + 1} page(s) clean, detector verified`
);
