#!/bin/zsh

set -euo pipefail

project_root="${0:A:h:h}"
user_root="${project_root%%/.codex/*}"
bundled_python="$user_root/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"

if python3 -c 'import PIL, reportlab' >/dev/null 2>&1; then
  python_executable="$(command -v python3)"
elif [[ -x "$bundled_python" ]] && \
  "$bundled_python" -c 'import PIL, reportlab' >/dev/null 2>&1; then
  python_executable="$bundled_python"
else
  print -u2 'PillowとReportLabを利用できるPythonが見つかりません。'
  print -u2 'Codexのワークスペース依存環境を読み込んでから再実行してください。'
  exit 1
fi

exec "$python_executable" "$project_root/scripts/build.py" "$@"
