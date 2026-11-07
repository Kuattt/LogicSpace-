#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
mkdir -p "$project_dir/.deps" "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/256x256/apps"
if [[ ! -d "$project_dir/.deps/PySide6" ]] && ! python3 -c 'import PySide6' >/dev/null 2>&1; then
  python3 -m pip install --target "$project_dir/.deps" -r "$project_dir/requirements.txt" --break-system-packages
fi
cat > "$HOME/.local/share/applications/logicspace.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=LogicSpace
Comment=Digital electronics sandbox
Exec="$project_dir/launch.sh"
Icon=$project_dir/resources/logicspace.png
Terminal=false
Categories=Education;Electronics;
StartupNotify=true
StartupWMClass=LogicSpace
EOF
chmod +x "$project_dir/launch.sh"
cp "$project_dir/resources/logicspace.png" "$HOME/.local/share/icons/hicolor/256x256/apps/logicspace.png"
echo "LogicSpace installed. Launch from the applications menu or run $project_dir/launch.sh"
