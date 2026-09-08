#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/mac_rescue_test.py
python3 scripts/rescue_gui_test.py
python3 scripts/rescue_native_test.py
python3 scripts/rescue_settings_test.py
python3 scripts/install_rescue_test.py
python3 - <<'PY'
import ast
from pathlib import Path
for path in Path('scripts').glob('*.py'):
    ast.parse(path.read_text(), filename=str(path))
print('Python syntax: OK')
PY
python3 scripts/harness-check.py
git diff --check
