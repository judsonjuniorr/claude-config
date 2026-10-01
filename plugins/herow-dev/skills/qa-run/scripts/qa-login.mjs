#!/usr/bin/env node
// qa-login.mjs save|check|login|clear "<QA>" — logs in outside the MCP browser so the credential never
// crosses a tool call. The result line is "ok …" / "warn …" / "error <code>[ <key>]"; stderr is silenced.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { Writable } from "node:stream";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

export class QaLoginError extends Error {
  constructor(code, key) {
    super(code);
    this.code = code;
    this.key = key;
  }
}

const fail = (code, key) => {
  throw new QaLoginError(code, key);
};

const INVALID = Symbol("invalid");

function stripComment(line) {
  let quote = null;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quote) {
      if (c === "\\" && quote === '"') i++;
      else if (c === quote) quote = null;
    } else if (c === '"' || c === "'") {
      quote = c;
    } else if (c === "#" && (i === 0 || /\s/.test(line[i - 1]))) {
      return line.slice(0, i);
    }
  }
  return line;
}

function splitTop(s) {
  const parts = [];
  let quote = null;
  let depth = 0;
  let cur = "";
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (quote) {
      if (c === "\\" && quote === '"') {
        cur += c + (s[++i] ?? "");
        continue;
      }
      if (c === quote) quote = null;
    } else if (c === '"' || c === "'") {
      quote = c;
    } else if (c === "[" || c === "{") {
      depth++;
    } else if (c === "]" || c === "}") {
      depth--;
    } else if (c === "," && depth === 0) {
      parts.push(cur);
      cur = "";
      continue;
    }
    cur += c;
  }
  if (cur.trim() !== "") parts.push(cur);
  return parts;
}

function scalar(raw) {
  const s = raw.trim();
  if (s.startsWith('"') && s.endsWith('"') && s.length >= 2) return JSON.parse(s);
  if (s.startsWith("'") && s.endsWith("'") && s.length >= 2) return s.slice(1, -1).replace(/''/g, "'");
  if (s.startsWith("[") && s.endsWith("]")) return splitTop(s.slice(1, -1)).map(scalar);
  if (s.startsWith("{") && s.endsWith("}")) {
    const out = {};
    for (const part of splitTop(s.slice(1, -1))) {
      const m = part.match(/^\s*([\w.-]+)\s*:\s*(.*)$/s);
      if (!m) throw new Error("bad flow map");
      out[m[1]] = scalar(m[2]);
    }
    return out;
  }
  if (s === "true") return true;
  if (s === "false") return false;
  if (s === "null" || s === "~" || s === "") return null;
  if (/^-?\d+$/.test(s)) return Number(s);
  return s;
}

// A malformed value becomes INVALID rather than vanishing, so validation names the key.
const safeScalar = (raw) => {
  try {
    return scalar(raw);
  } catch {
    return INVALID;
  }
};

// YAML subset: only the top-level session/browser blocks, one level of nested map or "- item" list.
export function parseConfig(text) {
  const out = { session: {}, browser: {} };
  let block = null;
  let childIndent = null;
  let nestedKey = null;
  let nestedIndent = null;
  for (const rawLine of text.split(/\r?\n/)) {
    const line = stripComment(rawLine).replace(/\s+$/, "");
    if (line.trim() === "") continue;
    const indent = line.length - line.trimStart().length;
    if (indent === 0) {
      const m = line.match(/^([\w-]+):\s*(.*)$/);
      block = m && (m[1] === "session" || m[1] === "browser") && m[2] === "" ? out[m[1]] : null;
      childIndent = nestedKey = nestedIndent = null;
      continue;
    }
    if (!block) continue;
    if (childIndent === null) childIndent = indent;
    if (nestedKey && indent > childIndent) {
      if (nestedIndent === null) nestedIndent = indent;
      if (indent !== nestedIndent) continue;
      const item = line.trim().match(/^-\s+(.*)$/);
      const m = line.trim().match(/^([\w-]+):\s*(.*)$/);
      if (item) {
        if (!Array.isArray(block[nestedKey])) block[nestedKey] = Object.keys(block[nestedKey]).length ? INVALID : [];
        if (block[nestedKey] !== INVALID) block[nestedKey].push(safeScalar(item[1]));
      } else if (m && !Array.isArray(block[nestedKey]) && block[nestedKey] !== INVALID) {
        block[nestedKey][m[1]] = safeScalar(m[2]);
      } else {
        block[nestedKey] = INVALID;
      }
      continue;
    }
    const m = line.trim().match(/^([\w-]+):\s*(.*)$/);
    if (indent !== childIndent || !m) continue;
    nestedKey = nestedIndent = null;
    if (m[2] === "") {
      block[m[1]] = {};
      nestedKey = m[1];
    } else {
      block[m[1]] = safeScalar(m[2]);
    }
  }
  return out;
}

const isStr = (v) => typeof v === "string" && v !== "";
const isMap = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

// Only keys this script reads are checked; present-but-wrong-typed fails instead of silently defaulting.
export function validateConfig(cfg) {
  const s = cfg.session;
  const b = cfg.browser;
  const bad = (key) => fail("config-unreadable", key);
  if (s.start_url !== undefined && !isStr(s.start_url)) bad("session.start_url");
  if (s.password_file !== undefined && !isStr(s.password_file)) bad("session.password_file");
  if (s.login_fields !== undefined) {
    if (!isMap(s.login_fields)) bad("session.login_fields");
    for (const k of ["user", "password", "submit"]) {
      if (s.login_fields[k] !== undefined && !isStr(s.login_fields[k])) bad(`session.login_fields.${k}`);
    }
  }
  if (s.login_origins !== undefined && !(Array.isArray(s.login_origins) && s.login_origins.every(isStr))) bad("session.login_origins");
  if (s.credentials_env !== undefined && !(isMap(s.credentials_env) && Object.values(s.credentials_env).every(isStr))) bad("session.credentials_env");
  const vp = b.viewport;
  if (vp !== undefined && !(Array.isArray(vp) && vp.length === 2 && vp.every((n) => Number.isInteger(n) && n > 0))) bad("browser.viewport");
  if (b.executable_path !== undefined && b.executable_path !== null && !isStr(b.executable_path)) bad("browser.executable_path");
  return cfg;
}

function loadConfig(qa) {
  let text;
  try {
    text = fs.readFileSync(path.join(qa, "config.yml"), "utf8");
  } catch {
    fail("config-unreadable", "config.yml");
  }
  return validateConfig(parseConfig(text));
}

export function readLoginFile(file) {
  let st;
  try {
    st = fs.lstatSync(file);
  } catch (e) {
    if (e.code === "ENOENT") return null;
    fail("file-invalid");
  }
  if (st.isSymbolicLink()) fail("unsafe-path");
  if (!st.isFile()) fail("file-invalid");
  if (st.mode & 0o077) fail("file-mode");
  let data;
  try {
    data = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    fail("file-invalid");
  }
  if (!data || !isStr(data.user) || !isStr(data.password)) fail("file-invalid");
  return { source: "file", user: data.user, password: data.password };
}

export function loginFromEnv(names, env = process.env) {
  if (!names || !names.user || !names.password) return null;
  const user = env[names.user];
  const password = env[names.password];
  return user && password ? { source: "env", user, password } : null;
}

export function loginFilePath(qa, session) {
  const name = session.password_file || "login.json";
  // A bare *.json name directly in <QA>: knowledge/, reports/ and config.yml are read into the model's context.
  if (name !== path.basename(name) || !/\.json$/i.test(name)) fail("unsafe-path");
  return path.join(qa, name);
}

export function resolveLogin(qa, session, env = process.env) {
  return readLoginFile(loginFilePath(qa, session)) || loginFromEnv(session.credentials_env, env) || fail("login-missing");
}

const LOCAL_HOST = /^(localhost|127(\.\d+){3}|\[::1\]|.+\.(localhost|test|local))$/i;

// The credential is only ever typed into an allowed origin; plain http only for local dev hosts.
export function assertOrigin(url, allowed) {
  let u;
  try {
    u = new URL(url);
  } catch {
    fail("origin-mismatch");
  }
  if (!allowed.includes(u.origin)) fail("origin-mismatch");
  if (u.protocol !== "https:" && !(u.protocol === "http:" && LOCAL_HOST.test(u.hostname))) fail("insecure-origin");
}

export function allowedOrigins(startUrl, extra) {
  try {
    return [startUrl, ...(extra || [])].map((u) => new URL(u).origin);
  } catch {
    fail("config-unreadable", "session.login_origins");
  }
}

const USER_INPUTS = "input[type=email], input[type=text], input[type=tel], input:not([type])";
const USER_FALLBACK = "input[type=email], input[autocomplete=username], input[name*=user i], input[name*=email i]";

const visible = (page, sel) => page.locator(`${sel} >> visible=true`).first();
const reaches = (loc, state, timeout) => loc.waitFor({ state, timeout }).then(() => true, () => false);

async function userField(page, fields, pw) {
  if (fields.user) return visible(page, fields.user);
  if (pw) {
    const form = pw.locator("xpath=ancestor::form[1]");
    if (await form.count()) return form.locator(`${USER_INPUTS} >> visible=true`).first();
  }
  return visible(page, USER_FALLBACK);
}

export async function performLogin(page, creds, fields, origins) {
  if (!Array.isArray(origins) || !origins.length) fail("internal");
  fields = fields || {};
  const missing = (f) => (fields[f] ? fail("field-missing", `session.login_fields.${f}`) : fail("no-form"));
  const pw = visible(page, fields.password || "input[type=password]");
  if (await reaches(pw, "visible", 5000)) {
    const user = await userField(page, fields, pw);
    if (!(await reaches(user, "visible", 2000))) missing("user");
    assertOrigin(page.url(), origins);
    await user.fill(creds.user);
  } else {
    // Two-step forms ask for the user first and reveal the password field after Enter.
    const user = await userField(page, fields, null);
    if (!(await reaches(user, "visible", 1000))) missing("user");
    assertOrigin(page.url(), origins);
    await user.fill(creds.user);
    await user.press("Enter");
    if (!(await reaches(pw, "visible", 10000))) missing("password");
  }
  assertOrigin(page.url(), origins);
  await pw.fill(creds.password);
  if (fields.submit) {
    const submit = visible(page, fields.submit);
    if (!(await reaches(submit, "visible", 2000))) missing("submit");
    await submit.click();
  } else {
    await pw.press("Enter");
  }
  if (!(await reaches(pw, "hidden", 15000))) fail("rejected");
  await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
  // A redirect back to the login form after a failed attempt briefly hides the field too.
  await page.waitForTimeout(1000);
  if (await pw.isVisible().catch(() => false)) fail("rejected");
}

function storeLayout(qa) {
  const projectDir = path.dirname(qa);
  const projects = path.dirname(projectDir);
  const home = path.basename(projects) === "projects" ? path.dirname(projects) : process.env.HEROW_HOME || path.join(os.homedir(), ".herow");
  return { home, id: path.basename(projectDir) };
}

function mtime(p) {
  try {
    return fs.statSync(p).mtimeMs;
  } catch {
    return 0;
  }
}

function resolveEngine(home) {
  const npx = path.join(process.env.npm_config_cache || path.join(os.homedir(), ".npm"), "_npx");
  let cached = [];
  try {
    // Fallback: the playwright-core the Playwright MCP server itself runs from the npx cache.
    cached = fs
      .readdirSync(npx)
      .map((d) => path.join(npx, d, "node_modules"))
      .filter((nm) => fs.existsSync(path.join(nm, "@playwright", "mcp", "package.json")))
      .sort((a, b) => mtime(path.join(b, "@playwright", "mcp")) - mtime(path.join(a, "@playwright", "mcp")));
  } catch {}
  for (const nm of [path.join(home, "tools", "playwright", "node_modules"), ...cached]) {
    try {
      return createRequire(path.join(nm, "_"))("playwright-core");
    } catch {}
  }
  fail("engine-missing");
}

function mcpExecutablePath() {
  try {
    const args = JSON.parse(fs.readFileSync(path.join(os.homedir(), ".claude.json"), "utf8")).mcpServers["playwright-headless"].args;
    const i = args.indexOf("--executable-path");
    if (i >= 0 && isStr(args[i + 1])) return args[i + 1];
    const eq = args.find((a) => typeof a === "string" && a.startsWith("--executable-path="));
    return eq ? eq.slice("--executable-path=".length) : undefined;
  } catch {
    return undefined;
  }
}

// The engine's bundled Chromium is often not installed, so mirror what the MCP server launches first.
async function launchBrowser(chromium, configured) {
  const mcp = configured ? undefined : mcpExecutablePath();
  const tries = configured ? [{ executablePath: configured }] : [...(mcp ? [{ executablePath: mcp }] : []), { channel: "chrome" }, {}];
  for (const opts of tries) {
    try {
      return await chromium.launch({ headless: true, ...opts });
    } catch {}
  }
  fail("browser-missing");
}

function writePrivate(file, data) {
  const dir = path.dirname(file);
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  fs.chmodSync(dir, 0o700);
  const tmp = `${file}.tmp-${process.pid}`;
  try {
    fs.writeFileSync(tmp, data, { mode: 0o600, flag: "wx" });
    fs.renameSync(tmp, file);
  } catch (e) {
    fs.rmSync(tmp, { force: true });
    throw e;
  }
}

function stateFile(qa) {
  const { home, id } = storeLayout(qa);
  return path.join(home, "browser", "state", `${id}.json`);
}

// The state file is a bearer credential; drop it once the MCP browser has loaded it.
function clear(qa) {
  fs.rmSync(stateFile(qa), { force: true });
  return "ok cleared";
}

async function login(qa) {
  const cfg = loadConfig(qa);
  const s = cfg.session;
  if (!isStr(s.start_url)) fail("config-unreadable", "session.start_url");
  const origins = allowedOrigins(s.start_url, s.login_origins);
  const creds = resolveLogin(qa, s);
  const file = stateFile(qa);
  fs.rmSync(file, { force: true });
  const { chromium } = resolveEngine(storeLayout(qa).home);
  const [width, height] = cfg.browser.viewport || [1440, 900];
  const browser = await launchBrowser(chromium, cfg.browser.executable_path);
  try {
    const context = await browser.newContext({ viewport: { width, height } });
    const page = await context.newPage();
    try {
      await page.goto(s.start_url, { waitUntil: "domcontentloaded", timeout: 30000 });
    } catch {
      fail("unreachable");
    }
    await performLogin(page, creds, s.login_fields, origins);
    const state = await context.storageState({ indexedDB: true });
    try {
      writePrivate(file, JSON.stringify(state));
    } catch {
      fail("state-write");
    }
    return `ok ${file}`;
  } finally {
    await browser.close().catch(() => {});
  }
}

const DENY_NAME = /secret|credentials|^\.env(\..*)?$/i;

function insideGit(dir) {
  try {
    execFileSync("git", ["-C", dir, "rev-parse", "--is-inside-work-tree"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

async function askTty(prompt, hidden) {
  let muted = false;
  const output = new Writable({
    write(chunk, _enc, cb) {
      if (!muted) process.stdout.write(chunk);
      cb();
    },
  });
  const rl = readline.createInterface({ input: process.stdin, output, terminal: true });
  process.stdout.write(prompt);
  muted = hidden;
  const answer = await new Promise((resolve) => {
    rl.on("close", () => resolve(null));
    rl.question("", resolve);
  });
  rl.close();
  if (hidden) process.stdout.write("\n");
  return answer ?? fail("cancelled");
}

function askDialog(prompt, hidden) {
  // `!` in Claude Code has no TTY; a native dialog keeps the value off stdout entirely.
  const script = `text returned of (display dialog ${JSON.stringify(prompt)} default answer ""${hidden ? " with hidden answer" : ""})`;
  try {
    return execFileSync("osascript", ["-e", script], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).replace(/\n$/, "");
  } catch {
    fail("cancelled");
  }
}

async function save(qa) {
  process.umask(0o077);
  const session = fs.existsSync(path.join(qa, "config.yml")) ? loadConfig(qa).session : {};
  const file = loginFilePath(qa, session);
  const dir = path.dirname(file);
  if (DENY_NAME.test(path.basename(file))) fail("unsafe-path");
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  if (insideGit(dir)) fail("unsafe-path");
  let isLink = false;
  try {
    isLink = fs.lstatSync(file).isSymbolicLink();
  } catch {}
  if (isLink) fail("unsafe-path");
  let ask;
  if (process.stdin.isTTY) ask = askTty;
  else if (process.platform === "darwin") ask = askDialog;
  else fail("no-tty");
  const project = path.basename(path.dirname(qa));
  const user = (await ask(`QA login for ${project} — user: `, false)).trim();
  const password = await ask(`QA login for ${project} — password: `, true);
  if (!user || !password) fail("cancelled");
  try {
    writePrivate(file, JSON.stringify({ user, password }));
  } catch {
    fail("state-write");
  }
  return "ok saved";
}

function literalHits(qa, needle) {
  const hits = [];
  const scan = (p) => {
    try {
      if (fs.readFileSync(p, "utf8").includes(needle)) hits.push(path.relative(qa, p));
    } catch {}
  };
  const walk = (dir, depth) => {
    if (depth > 6) return;
    let entries = [];
    try {
      entries = fs.readdirSync(dir);
    } catch {
      return;
    }
    for (const name of entries) {
      const p = path.join(dir, name);
      let st;
      try {
        st = fs.statSync(p);
      } catch {
        continue;
      }
      if (st.isDirectory()) walk(p, depth + 1);
      else if (/\.(md|txt|json|ya?ml)$/i.test(name) && st.size < 5_000_000) scan(p);
    }
  };
  scan(path.join(qa, "config.yml"));
  walk(path.join(qa, "knowledge"), 0);
  walk(path.join(qa, "reports"), 0);
  return hits;
}

function check(qa) {
  const creds = resolveLogin(qa, loadConfig(qa).session);
  const lines = [`ok ${creds.source}`];
  // Very short values match unrelated prose; skip the scan rather than cry wolf.
  if (creds.password.length >= 6) {
    const hits = literalHits(qa, creds.password);
    if (hits.length) lines.push(`warn literal-in ${hits.join(" ")}`);
  }
  return lines.join("\n");
}

const COMMANDS = { save, check, login, clear };

function finish(line, code) {
  process.exitCode = code;
  process.stdout.write(`${line}\n`, () => process.exit(code));
}

async function main(argv) {
  process.exitCode = 1;
  delete process.env.DEBUG;
  delete process.env.PWDEBUG;
  for (const k of ["log", "info", "debug", "warn", "error", "trace", "dir"]) console[k] = () => {};
  process.stderr.write = () => true;
  process.on("warning", () => {});
  process.on("uncaughtException", () => finish("error internal", 1));
  process.on("unhandledRejection", () => finish("error internal", 1));
  const [cmd, qaArg] = argv;
  if (!Object.hasOwn(COMMANDS, cmd) || !qaArg || !path.isAbsolute(qaArg)) return finish("error usage", 2);
  try {
    finish(await COMMANDS[cmd](path.resolve(qaArg)), 0);
  } catch (e) {
    if (e instanceof QaLoginError) finish(`error ${e.code}${e.key ? ` ${e.key}` : ""}`, 1);
    else finish("error internal", 1);
  }
}

const invoked = process.argv[1] && (() => {
  try {
    return pathToFileURL(fs.realpathSync(process.argv[1])).href === import.meta.url;
  } catch {
    return false;
  }
})();
if (invoked) main(process.argv.slice(2));
