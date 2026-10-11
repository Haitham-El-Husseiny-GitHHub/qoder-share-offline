#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
task_cache=$(cd -- "$(dirname -- "$0")" && pwd -P)
cd -- "$task_cache"
case "${PREFIX:-}" in /data/data/com.termux/*) ;; *) echo 'Run in official Termux on ARM64 Android.'; exit 1;; esac
[ "$(uname -m)" = aarch64 ] || { echo 'This cache targets ARM64.'; exit 1; }
echo 'Checking downloaded files...'
if ! sha256sum -c SHA256SUMS > "${TMPDIR:-$PREFIX/tmp}/qoder-cache-verification.log" 2>&1; then
  tail -n 15 "${TMPDIR:-$PREFIX/tmp}/qoder-cache-verification.log"
  exit 1
fi
if ! command -v python3 >/dev/null; then
  case "$task_cache" in *$'\n'*|*'#'*|*'%'*|*'['*) echo 'Move the extracted cache to a path without special characters.'; exit 1;; esac
  task_apt=$(mktemp -d "${TMPDIR:-$PREFIX/tmp}/qoder-offline-apt.XXXXXX")
  trap 'rm -rf -- "$task_apt"' EXIT
  mkdir -p "$task_apt/lists/partial"
  task_uri=${task_cache// /%20}
  printf 'deb [trusted=yes] file:%s/android/termux-debs ./\n' "$task_uri" > "$task_apt/sources.list"
  task_options=(-o "Dir::Etc::sourcelist=$task_apt/sources.list" -o Dir::Etc::sourceparts=- -o "Dir::State::lists=$task_apt/lists" -o APT::Get::List-Cleanup=0)
  apt-get "${task_options[@]}" update
  apt-get "${task_options[@]}" --no-remove install -y python
fi
exec python3 "$task_cache/install_offline_tools.py" --cache "$task_cache" "$@"
