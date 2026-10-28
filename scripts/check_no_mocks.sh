#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
if command -v py >/dev/null 2>&1 && py -3 --version >/dev/null 2>&1; then
    PY="py -3"
elif command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
    PY="python"
elif [ -x "/c/Users/abhin/AppData/Local/Programs/Python/Python313/python.exe" ]; then
    PY="/c/Users/abhin/AppData/Local/Programs/Python/Python313/python.exe"
else
    PY="py -3"
fi
exec $PY scripts/check_no_mocks.py "$@"
