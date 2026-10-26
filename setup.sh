#! /bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install -e .
printf '\nActivate with: source .venv/bin/activate\n'
printf 'Optional debugger: pip install -e ".[debug]"\n'
printf 'Optional Amaranth tools: pip install -e ".[hdl]"\n'
