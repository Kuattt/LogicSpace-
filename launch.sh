#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ -d "$project_dir/.deps/PySide6" ]]; then
  export PYTHONPATH="$project_dir/.deps${PYTHONPATH:+:$PYTHONPATH}"
fi
if ! python3 -c 'from PySide6.QtWidgets import QApplication'; then
  echo "LogicSpace needs PySide6 and Qt runtime libraries. Run $project_dir/install.sh; on minimal Ubuntu installs, install the libegl1 package." >&2
  exit 1
fi
cd "$project_dir"
exec python3 main.py "$@"
