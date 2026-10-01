#!/usr/bin/env bash
# Tests for qa-run/scripts/qa-login.mjs; sandbox under $HOME (never bare /tmp, same as the other qa suites).
# Browser cases need an engine + browser; QA_LOGIN_REQUIRE_BROWSER=1 (CI) turns their skip into a failure.
set -u

SCRIPT="$(cd "$(dirname "$0")/../../skills/qa-run/scripts" && pwd)/qa-login.mjs"
[ -f "$SCRIPT" ] || { echo "script not found: $SCRIPT" >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo "node not found" >&2; exit 1; }

SANDBOX="$(cd "$HOME" && pwd)/.qa-login-test.$$"
QA="$SANDBOX/herow/projects/proj-abc123/qa"
mkdir -p "$QA/knowledge" "$QA/reports"
SERVER_PID=""
cleanup() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; rm -rf "$SANDBOX"; }
trap cleanup EXIT

# Optional overrides: a browser binary, and a dir with node_modules/playwright-core (CI installs one).
EXE="${QA_LOGIN_TEST_EXE:-}"
if [ -n "${QA_LOGIN_TEST_ENGINE:-}" ]; then
  mkdir -p "$SANDBOX/herow/tools" && ln -s "$QA_LOGIN_TEST_ENGINE" "$SANDBOX/herow/tools/playwright"
fi

PW="fixture-Pw-7731"
GOOD_LOGIN="{\"user\":\"qa@example.com\",\"password\":\"$PW\"}"
PASS=0
FAIL=0
ok()   { PASS=$((PASS + 1)); echo "ok   - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL - $1"; }

LEAKED=0
run() { # $@ = args; sets OUT/RC; flags any output containing the fixture password
  OUT="$(node "$SCRIPT" "$@" 2>&1)"; RC=$?
  case "$OUT" in *"$PW"*) LEAKED=1 ;; esac
}
expect() { # $1 = label, $2 = expected rc, $3 = expected first line (exact)
  if [ "$RC" -eq "$2" ] && [ "$(printf '%s\n' "$OUT" | head -1)" = "$3" ]; then ok "$1"; else fail "$1: expected rc=$2 '$3', got rc=$RC out=$OUT"; fi
}
mode_of() { stat -c %a "$1" 2>/dev/null || stat -f %Lp "$1"; }

write_config() { # $1 = start_url, $2 = extra session lines, $3 = extra browser lines
  cat > "$QA/config.yml" <<EOF
schema_version: 1
browser:
  headed_required: false     # comment
  viewport: [1280, 800]
${EXE:+  executable_path: "$EXE"}
${3:-}
session:
  env: local
  start_url: $1          # trailing comment
  login: form
  login_detect: "a form with a password field"
  credentials_env: { user: QA_TEST_USER, password: QA_TEST_PASS }   # names only
  auto_fill: true
$2
  entry_target: "Home (heading 'Home')"
setup:
  smoke: pending
EOF
}
write_login() { # $1 = json, $2 = mode
  printf '%s' "$1" > "$QA/login.json"; chmod "$2" "$QA/login.json"
}

# --- usage -------------------------------------------------------------------------------------
run; expect "no args: usage" 2 "error usage"
run check relative/path; expect "relative QA path: usage" 2 "error usage"

# --- parser --------------------------------------------------------------------------------------
PARSED="$(node --input-type=module -e "
import { parseConfig } from '$SCRIPT';
const c = parseConfig(['session:', '  start_url: http://x/   # c', '  login_fields:', '    user: \"#email\"',
  \"    submit: 'it''s'\", '  login_origins:', '    - https://idp.example.com', '    - \"https://b.example.com\"',
  '  auto_fill: true', 'browser:', '  viewport: [1, 2]'].join('\r\n'));
console.log(JSON.stringify(c));" 2>&1)"
WANT='{"session":{"start_url":"http://x/","login_fields":{"user":"#email","submit":"it'"'"'s"},"login_origins":["https://idp.example.com","https://b.example.com"],"auto_fill":true},"browser":{"viewport":[1,2]}}'
if [ "$PARSED" = "$WANT" ]; then ok "parser: quoted #, '' escape, block list, nested map + sibling, CRLF"; else fail "parser: got $PARSED"; fi

# --- check -------------------------------------------------------------------------------------
run check "$QA"; expect "missing config: config-unreadable" 1 "error config-unreadable config.yml"

write_config "http://127.0.0.1:1/" ""
run check "$QA"; expect "no file, no env: login-missing" 1 "error login-missing"

write_login "$GOOD_LOGIN" 644
run check "$QA"; expect "group-readable file: file-mode" 1 "error file-mode"

write_login '{"user":"qa@example.com"' 600
run check "$QA"; expect "malformed JSON: file-invalid" 1 "error file-invalid"

write_login '{"user":"qa@example.com","password":""}' 600
run check "$QA"; expect "empty password: file-invalid" 1 "error file-invalid"

write_login "$GOOD_LOGIN" 600
run check "$QA"; expect "valid file: ok file" 0 "ok file"

QA_TEST_USER=qa@example.com QA_TEST_PASS=other-value run check "$QA"
expect "file wins over env" 0 "ok file"

rm -f "$QA/login.json"
QA_TEST_USER=qa@example.com QA_TEST_PASS="$PW" run check "$QA"
expect "env fallback: ok env" 0 "ok env"

write_login "$GOOD_LOGIN" 600
printf 'Log in with qa@example.com / %s\n' "$PW" > "$QA/knowledge/navigation.md"
run check "$QA"
if [ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -qx "warn literal-in knowledge/navigation.md"; then
  ok "literal in knowledge: warns with the file name only"
else
  fail "literal in knowledge: got rc=$RC out=$OUT"
fi
rm -f "$QA/knowledge/navigation.md"

write_config "http://127.0.0.1:1/" "  password_file: elsewhere.json"
run check "$QA"; expect "password_file points elsewhere, env unset: login-missing" 1 "error login-missing"

for bad in ../outside.json knowledge/login.json Knowledge/login.json reports/x.json config.yml login.txt; do
  write_config "http://127.0.0.1:1/" "  password_file: $bad"
  run check "$QA"; expect "password_file '$bad': unsafe-path" 1 "error unsafe-path"
done

write_config "http://127.0.0.1:1/" ""
mv "$QA/login.json" "$SANDBOX/real-login.json" && ln -s "$SANDBOX/real-login.json" "$QA/login.json"
run check "$QA"; expect "symlinked password file: unsafe-path" 1 "error unsafe-path"
rm -f "$QA/login.json" && mv "$SANDBOX/real-login.json" "$QA/login.json"

write_config "http://127.0.0.1:1/" "  login_fields:
    user: [name=email]"
run check "$QA"; expect "unquoted [ selector: config-unreadable" 1 "error config-unreadable session.login_fields.user"
write_config "http://127.0.0.1:1/" "  login_fields:
    user: \"a\\q\""
run check "$QA"; expect "malformed quoted value: config-unreadable" 1 "error config-unreadable session.login_fields.user"
write_config "http://127.0.0.1:1/" "" "  executable_path: true"
run check "$QA"; expect "non-string executable_path: config-unreadable" 1 "error config-unreadable browser.executable_path"

ORIGIN_OUT="$(node --input-type=module -e "
import { assertOrigin } from '$SCRIPT';
const t = (u, a) => { try { assertOrigin(u, a); return 'ok'; } catch (e) { return e.code; } };
console.log([t('https://app.example.com/x', ['https://app.example.com']), t('http://example.com/', ['http://example.com']),
  t('http://localhost:3000/', ['http://localhost:3000']), t('https://evil.example/', ['https://app.example.com'])].join(' '));" 2>&1)"
if [ "$ORIGIN_OUT" = "ok insecure-origin ok origin-mismatch" ]; then ok "assertOrigin: https ok, remote http refused, loopback http ok, foreign origin refused"; else fail "assertOrigin: got $ORIGIN_OUT"; fi

# --- save refuses unsafe targets before prompting ------------------------------------------------
write_config "http://127.0.0.1:1/" "  password_file: qa-secret.json"
run save "$QA" </dev/null; expect "deny-glob file name: unsafe-path" 1 "error unsafe-path"

write_config "http://127.0.0.1:1/" ""
mv "$QA/login.json" "$SANDBOX/real-login.json" && ln -s "$SANDBOX/real-login.json" "$QA/login.json"
run save "$QA" </dev/null; expect "save over a symlink: unsafe-path" 1 "error unsafe-path"
rm -f "$QA/login.json" && mv "$SANDBOX/real-login.json" "$QA/login.json"

GITQA="$SANDBOX/repo/qa"
mkdir -p "$GITQA" && git -C "$SANDBOX/repo" init -q .
run save "$GITQA" </dev/null; expect "target inside a git work tree: unsafe-path" 1 "error unsafe-path"

if [ "$(uname)" != "Darwin" ]; then
  write_config "http://127.0.0.1:1/" ""
  run save "$QA" </dev/null; expect "no TTY off macOS: no-tty" 1 "error no-tty"
fi

# --- browser login against a local fixture form -----------------------------------------------------
write_config "http://127.0.0.1:1/" ""
run login "$QA"
if [ "$OUT" = "error engine-missing" ] || [ "$OUT" = "error browser-missing" ]; then
  if [ "${QA_LOGIN_REQUIRE_BROWSER:-}" = "1" ]; then
    fail "browser cases required but unavailable ($OUT)"
  else
    echo "skip - browser cases ($OUT; set QA_LOGIN_TEST_EXE to a Chromium binary to run them)"
  fi
else
  cat > "$SANDBOX/server.mjs" <<'EOF'
import fs from "node:fs";
import http from "node:http";
const PW = process.env.FIXTURE_PW;
const BODIES = process.env.FIXTURE_BODIES;
const page = (body) => `<!doctype html><html><body>${body}</body></html>`;
const form = (action, step) => page(`<form method="post" action="${action}">
  ${step !== 2 ? '<label>Email <input type="email" name="email"></label>' : '<input type="hidden" name="email" value="x">'}
  ${step !== 1 ? '<label>Password <input type="password" name="password"></label>' : ""}
  <button type="submit">Sign in</button></form>`);
http.createServer((req, res) => {
  let data = "";
  req.on("data", (c) => (data += c));
  req.on("end", () => {
    fs.appendFileSync(BODIES, `${req.headers.host} ${req.url} ${data}\n`);
    const p = new URLSearchParams(data);
    const authed = (req.headers.cookie || "").includes("sid=ok");
    const send = (html) => { res.writeHead(200, { "content-type": "text/html" }); res.end(html); };
    const port = req.socket.localPort;
    if (req.url === "/" || req.url === "/two") {
      if (authed) return send(page("<h1>Home</h1>"));
      return send(req.url === "/" ? form("/login") : form("/two-step", 1));
    }
    if (req.url === "/two-foreign") return send(form("/to-foreign", 1));
    if (req.url === "/to-foreign") { res.writeHead(302, { location: `http://localhost:${port}/two-step` }); return res.end(); }
    if (req.url === "/two-step") return send(form("/login", 2));
    if (req.url === "/login") {
      if (p.get("password") === PW) { res.writeHead(302, { location: "/", "set-cookie": "sid=ok; Path=/; HttpOnly" }); return res.end(); }
      return send(form("/login"));
    }
    if (req.url === "/cross") { res.writeHead(302, { location: `http://localhost:${port}/` }); return res.end(); }
    if (req.url === "/plain") return send(page("<h1>No login here</h1>"));
    res.writeHead(404); res.end();
  });
}).listen(0, "127.0.0.1", function () { console.log(this.address().port); });
EOF
  FIXTURE_PW="$PW" FIXTURE_BODIES="$SANDBOX/bodies" node "$SANDBOX/server.mjs" > "$SANDBOX/port" &
  SERVER_PID=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$SANDBOX/port" ] && break; sleep 0.3; done
  PORT="$(cat "$SANDBOX/port")"
  BASE="http://127.0.0.1:$PORT"
  STATE="$SANDBOX/herow/browser/state/proj-abc123.json"

  write_config "$BASE/" ""
  run login "$QA"; expect "one-step form: ok <state path>" 0 "ok $STATE"
  if [ -f "$STATE" ] && [ "$(mode_of "$STATE")" = "600" ] && [ "$(mode_of "$(dirname "$STATE")")" = "700" ] && grep -q '"sid"' "$STATE"; then
    ok "state file is 600 in a 700 dir and holds the session cookie"
  else
    fail "state file missing, wrong mode, or no cookie"
  fi
  if ! grep -qF "$PW" "$STATE"; then ok "state file does not contain the password"; else fail "state file contains the password"; fi

  write_config "$BASE/two" ""
  run login "$QA"; expect "two-step form: ok" 0 "ok $STATE"

  write_config "$BASE/" '  login_fields:
    user: "input[name=email]"
    submit: "role=button[name=\"Sign in\"]"'
  run login "$QA"; expect "configured selectors: ok" 0 "ok $STATE"

  write_config "$BASE/" '  login_fields:
    user: "#nope"'
  run login "$QA"; expect "configured selector matches nothing: field-missing" 1 "error field-missing session.login_fields.user"
  if [ ! -e "$STATE" ]; then ok "a failed login leaves no stale state file"; else fail "stale state file survived a failed login"; fi

  write_login '{"user":"qa@example.com","password":"wrong-password"}' 600
  write_config "$BASE/" ""
  run login "$QA"; expect "wrong password: rejected" 1 "error rejected"
  write_login "$GOOD_LOGIN" 600

  write_config "$BASE/plain" ""
  run login "$QA"; expect "page without a form: no-form" 1 "error no-form"

  write_config "$BASE/cross" ""
  run login "$QA"; expect "redirect to a foreign origin: origin-mismatch" 1 "error origin-mismatch"
  write_config "$BASE/cross" "  login_origins:
    - \"http://localhost:$PORT\""
  run login "$QA"; expect "redirect to an allowlisted origin (block list): ok" 0 "ok $STATE"

  : > "$SANDBOX/bodies"
  write_config "$BASE/two-foreign" ""
  run login "$QA"; expect "user step redirects to a foreign origin: origin-mismatch" 1 "error origin-mismatch"
  if ! grep -qF "$PW" "$SANDBOX/bodies"; then ok "password never sent to the foreign origin"; else fail "password reached the server after a foreign redirect"; fi

  run clear "$QA"; expect "clear: ok cleared" 0 "ok cleared"
  if [ ! -e "$STATE" ]; then ok "clear removed the state file"; else fail "clear left the state file"; fi

  write_config "http://127.0.0.1:1/" ""
  run login "$QA"; expect "unreachable start_url: unreachable" 1 "error unreachable"
fi

if [ "$LEAKED" -eq 0 ]; then ok "no output ever contained the password"; else fail "an output contained the password"; fi

echo
echo "passed: $PASS  failed: $FAIL"
[ "$FAIL" -eq 0 ]
