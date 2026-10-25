#!/usr/bin/env bash
# Friendly entry point for the single first-run installer (macOS and Linux).
# Use 'bash install.sh' or './install.sh'; no password is passed on the command line.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
    exec "$ROOT/.venv/bin/python" "$ROOT/install.py" "$@"
fi
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$ROOT/install.py" "$@"
fi
echo "Python 3 is required for CA-Panel setup." >&2
exit 1
