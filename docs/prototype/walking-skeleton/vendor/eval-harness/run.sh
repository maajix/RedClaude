#!/usr/bin/env bash
# PROTOTYPE eval harness. One command, no dependencies beyond python3.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf out
exec python3 harness.py
