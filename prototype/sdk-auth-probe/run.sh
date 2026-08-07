#!/usr/bin/env bash
# Reproduce the ticket-21 probe. PROTOTYPE - throwaway.
#
#   ./run.sh            matrix + guard verification, all offline (default)
#   ./run.sh live       the two real-endpoint control runs (see WARNING below)
#
# The default path never reaches Anthropic: mitmdump answers every request
# locally, so no token is spent and no credential leaves the machine.
#
# WARNING for `live`: one Haiku turn is billed to the logged-in subscription,
# and a second run sends a deliberately invalid key to api.anthropic.com to see
# it rejected. Never put a working API key in this environment.
set -euo pipefail
cd "$(dirname "$0")"

command -v mitmdump >/dev/null || { echo "need mitmdump (mitmproxy 12.2.3 used)"; exit 1; }

if [ ! -x .venv/bin/python ]; then
  export UV_CACHE_DIR="${TMPDIR:-/tmp}/uv-cache"   # the default cache dir may be read-only
  uv venv --python 3.14 .venv
  uv pip install --python .venv/bin/python "claude-agent-sdk==0.2.132" anyio
fi

# Fail closed on the runtime the finding is bound to, rather than silently
# measuring a different CLI.
.venv/bin/python - <<'PY'
import importlib.metadata, pathlib, subprocess
sdk = importlib.metadata.version("claude-agent-sdk")
cli = pathlib.Path(".venv/lib/python3.14/site-packages/claude_agent_sdk/_bundled/claude")
out = subprocess.run([str(cli), "--version"], capture_output=True, text=True).stdout.strip()
print(f"SDK {sdk} / bundled CLI {out}")
if (sdk, out.split()[0]) != ("0.2.132", "2.1.224"):
    print("  ^ NOT the runtime this probe's findings are bound to; re-read README.md")
PY

if [ "${1:-}" = "live" ]; then
  exec .venv/bin/python live_control.py
fi

.venv/bin/python -u probe.py            # every vector, behind the fake upstream
.venv/bin/python fd_direct.py           # fd vector, bypassing the SDK's spawn
.venv/bin/python verify_guard.py        # the assertion, against what the wire showed
