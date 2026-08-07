#!/usr/bin/env bash
# The whole skeleton, from an empty database to a divergence report.
#
#   ./run_all.sh          # live: makes real model calls on the subscription
#   RK_LIVE=0 ./run_all.sh   # everything except the model-in-the-loop stage
#
# Requires a Postgres container named by CT (default rk2-t31-pg), e.g.
#   docker run -d --name rk2-t31-pg -e POSTGRES_PASSWORD=x pgvector/pgvector:pg18
#
# NOTHING here sets a billing vector. `subscription_guard` asserts on every run
# that ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL,
# CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR, CLAUDE_CODE_USE_BEDROCK,
# CLAUDE_CODE_USE_VERTEX, CLAUDE_CODE_USE_FOUNDRY and `apiKeyHelper` are all
# absent, and the child process is given an allowlisted environment rather than
# an inherited one. P10 proves the assertion fires for each of them.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CT="${CT:-rk2-t31-pg}"
export DB="${DB:-rk2}"

"$HERE/reset.sh"
exec python3 "$HERE/skeleton.py" "$@"
