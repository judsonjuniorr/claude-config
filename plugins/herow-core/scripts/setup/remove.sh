#!/usr/bin/env bash
# Apply approved removals. Each arg is a target token:
#   omega            full OMEGA removal (uv tool, bin, settings hooks, mcp server, CLAUDE.md section)
#   loose            loose dup commands + track script + settings blueprint-track hooks
#   stray:<key>      remove mcpServer <key> from ~/.claude.json
# Every mutated file gets a timestamped .bak first. No arg = no-op.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
. "${HERE}/_common.sh"

# Drop inner hooks whose command contains <substr>; prune emptied matcher-groups.
strip_settings_hooks() {  # strip_settings_hooks <file> <substr>
  local f="$1" sub="$2"
  [ -f "$f" ] || return 0
  python3 - "$f" "$sub" <<'PY'
import json,sys
f,sub=sys.argv[1],sys.argv[2]
try: d=json.load(open(f))
except Exception as e:
    sys.stderr.write("info|settings-parse-skip|%s\n"%e); sys.exit(0)
h=d.get("hooks",{})
for ev,groups in list(h.items()):
    ng=[]
    for g in groups:
        # Match the command field specifically (precise) rather than the whole
        # serialized hook — avoids ever stripping an unrelated hook whose JSON
        # happens to contain the substring.
        g["hooks"]=[x for x in g.get("hooks",[])
                    if sub not in (x.get("command","") if isinstance(x,dict) else json.dumps(x))]
        if g["hooks"]: ng.append(g)
    if ng: h[ev]=ng
    else: h.pop(ev,None)
json.dump(d,open(f,"w"),indent=2); open(f,"a").write("\n")
PY
}

remove_mcp_server() {  # remove_mcp_server <key-substr>
  local sub="$1"
  [ -f "$CLAUDE_JSON" ] || return 0
  python3 - "$CLAUDE_JSON" "$sub" <<'PY'
import json,sys
f,sub=sys.argv[1],sys.argv[2]
try: d=json.load(open(f))
except Exception: sys.exit(0)
srv=d.get("mcpServers",{})
for k in [k for k in srv if sub.lower() in k.lower()]:
    srv.pop(k,None); sys.stderr.write("info|mcp-removed|%s\n"%k)
json.dump(d,open(f,"w"),indent=2); open(f,"a").write("\n")
PY
}

strip_md_section() {  # strip_md_section <file> <needle>
  # Prefer the marker-delimited block (<!-- NEEDLE:BEGIN --> … <!-- NEEDLE:END -->)
  # that OMEGA writes; fall back to the heading section (## … OMEGA … up to next ##).
  local f="$1" needle="$2"
  [ -f "$f" ] || return 0
  python3 - "$f" "$needle" <<'PY'
import re,sys
f,needle=sys.argv[1],sys.argv[2]
lines=open(f).read().splitlines(keepends=True)
nl=needle.lower()

def find_markers():
    b=e=None
    for i,l in enumerate(lines):
        if "%s:begin"%nl in l.lower(): b=i
        if "%s:end"%nl in l.lower(): e=i
    if b is not None and e is not None and e>=b:
        # swallow a trailing blank line left by the block
        end=e+1
        if end<len(lines) and lines[end].strip()=="": end+=1
        return b,end
    return None

def find_heading():
    start=None
    for i,l in enumerate(lines):
        if re.match(r'^#{1,6}\s', l) and nl in l.lower(): start=i; break
    if start is None: return None
    end=len(lines)
    for j in range(start+1,len(lines)):
        if re.match(r'^#{1,2}\s', lines[j]): end=j; break
    return start,end

span=find_markers() or find_heading()
if span is None: sys.exit(0)
del lines[span[0]:span[1]]
open(f,"w").write("".join(lines))
sys.stderr.write("info|md-section-removed|%s (%d lines)\n"%(needle,span[1]-span[0]))
PY
}

for target in "$@"; do
  case "$target" in
    omega)
      info omega "removing OMEGA across all surfaces"
      have uv && uv tool uninstall omega-memory >/dev/null 2>&1 && emit ok omega-uv "uv tool uninstalled"
      [ -e "${HOME}/.local/bin/omega" ] && rm -f "${HOME}/.local/bin/omega" && emit ok omega-bin "removed"
      backup_file "$SETTINGS" >/dev/null; strip_settings_hooks "$SETTINGS" "omega" && emit ok omega-hooks "stripped from settings.json"
      backup_file "$CLAUDE_JSON" >/dev/null; remove_mcp_server "omega" && emit ok omega-mcp "stripped from ~/.claude.json"
      backup_file "$CLAUDE_MD" >/dev/null; strip_md_section "$CLAUDE_MD" "OMEGA" && emit ok omega-md "section removed from CLAUDE.md"
      ;;
    loose)
      info loose "removing loose duplicate commands + track hook"
      for n in blueprint quick execute; do
        [ -f "${LOOSE_CMD_DIR}/${n}.md" ] && rm -f "${LOOSE_CMD_DIR}/${n}.md" && emit ok "loose-${n}" "removed"
      done
      [ -f "$LOOSE_HOOK" ] && rm -f "$LOOSE_HOOK" && emit ok loose-track-script "removed"
      backup_file "$SETTINGS" >/dev/null; strip_settings_hooks "$SETTINGS" "blueprint-track.sh" && emit ok loose-settings-hook "stripped from settings.json"
      ;;
    stray:*)
      key="${target#stray:}"
      backup_file "$CLAUDE_JSON" >/dev/null; remove_mcp_server "$key" && emit ok "stray-${key}" "removed from ~/.claude.json"
      ;;
    *)
      emit err unknown-target "$target" ;;
  esac
done
exit 0
