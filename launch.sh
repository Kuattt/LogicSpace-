#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ -d "$project_dir/.deps/PySide6" ]]; then
  export PYTHONPATH="$project_dir/.deps${PYTHONPATH:+:$PYTHONPATH}"
fi
if ! python3 -c 'import PySide6' >/dev/null 2>&1; then
  echo "PySide6 is missing. Run: $project_dir/install.sh" >&2
  exit 1
fi
cd "$project_dir"
exec python3 main.py "$@"
