#!/usr/bin/env bash
# install.sh - install the fluent-cfd DSH agent preset (Linux / macOS).
#
# Usage (from the repo checkout):
#   ./install.sh [-t <target>] [-p <python>] [-a <ansys-root>] [-f]
#
# Auto-detection (override with env vars or the flags):
#   PYTHON                    -> python interpreter (else python3 / python)
#   PYTHON_ANSYS_FLUENT_MCP   -> path to the ansys-fluent-mcp entrypoint (else on PATH)
#   ANSYS_AWP_ROOT            -> Ansys install dir, e.g. /opt/ansys_inc/v252
#
# Idempotent: backs up an existing install unless -f.
set -euo pipefail

TARGET="${TARGET:-$HOME/.dsh/.agent-presets/fluent-cfd}"
PY="$PYTHON"
ANYSYS="$ANSYS_AWP_ROOT"
FORCE=0
while getopts "t:p:a:f" o; do
  case "$o" in
    t) TARGET="$OPTARG";;
    p) PY="$OPTARG";;
    a) ANYSYS="$OPTARG";;
    f) FORCE=1;;
    *) echo "usage: $0 [-t target] [-p python] [-a ansys-root] [-f]"; exit 2;;
  esac
done

BUNDLE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$BUNDLE/fluent-cfd"
[ -f "$SRC/agent.cordis.yml" ] || { echo "ERROR: bundle not found: $SRC"; exit 1; }

echo "== fluent-cfd DSH agent preset installer =="

# --- python ---
if [ -z "$PY" ]; then
  PY="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PY" ]; then echo "ERROR: python3/python not found. Set PYTHON or pass -p."; exit 1; fi
echo "python : $PY"

# --- ansys-fluent-mcp ---
MCP="${PYTHON_ANSYS_FLUENT_MCP:-}"
if [ -z "$MCP" ]; then
  MCP="$(command -v ansys-fluent-mcp || true)"
fi
if [ -z "$MCP" ]; then
  echo "WARN: ansys-fluent-mcp not found on PATH. Install it and set PYTHON_ANSYS_FLUENT_MCP, or edit command in agent.cordis.yml."
  MCP="__PYTHON_ANSYS_FLUENT_MCP__"
else
  echo "mcp    : $MCP"
fi

# --- ANSYS AWP root ---
if [ -z "$ANYSYS" ]; then
  for c in /opt/ansys_inc /usr/local/ansys_inc /opt/AnsysInc /usr/ansys_inc; do
    if [ -d "$c" ]; then
      v="$(ls -1 "$c" 2>/dev/null | grep -E '^v[0-9]+$' | sort -V | tail -n1 || true)"
      if [ -n "$v" ] && [ -d "$c/$v" ]; then ANYSYS="$c/$v"; break; fi
    fi
  done
fi
if [ -z "$ANYSYS" ]; then
  echo "WARN: ANSYS install not detected. Set ANSYS_AWP_ROOT or pass -a."
  ANYSYS="__ANSYS_AWP_ROOT__"
else
  echo "ansys  : $ANYSYS"
fi

# --- install ---
if [ -d "$TARGET" ]; then
  if [ "$FORCE" -eq 1 ]; then rm -rf "$TARGET"; else
    BAK="${TARGET}.bak-$(date +%Y%m%d-%H%M%S)"; echo "existing install -> backup $BAK"; mv "$TARGET" "$BAK"
  fi
fi
mkdir -p "$(dirname "$TARGET")"
cp -R "$SRC" "$TARGET"
echo "copied preset -> $TARGET"

YML="$TARGET/agent.cordis.yml"
# derive AWP_ROOT<version> var name from the ansys dir (v252 -> AWP_ROOT252)
AWPVAR="__AWP_ROOT_VARNAME__"
if [[ "$ANYSYS" =~ v([0-9]+)[^/]*$ ]]; then AWPVAR="AWP_ROOT${BASH_REMATCH[1]}"; fi
echo "awp var: $AWPVAR"
python3 - "$YML" "$MCP" "$ANYSYS" "$AWPVAR" <<'PY' || true
import io,sys
path,mcp,ansys,awpvar=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
s=io.open(path,encoding="utf-8").read()
s=s.replace("__PYTHON_ANSYS_FLUENT_MCP__",mcp).replace("__AWP_ROOT_VARNAME__",awpvar).replace("__ANSYS_AWP_ROOT__",ansys)
io.open(path,"w",encoding="utf-8").write(s)
PY
echo "filled machine paths in agent.cordis.yml"

if grep -q '__PYTHON_ANSYS_FLUENT_MCP__\|__ANSYS_AWP_ROOT__\|__AWP_ROOT_VARNAME__' "$YML"; then
  echo "WARN: unresolved tokens remain. Edit agent.cordis.yml manually."
else
  echo "RESOLVED: no unresolved tokens."
fi

echo "Done. Start a DSH agent from the 'fluent-cfd' preset. Prereqs: ANSYS Fluent 24R2+ (detected: $ANYSYS) + license, pyfluent-core, ansys-fluent-mcp."
