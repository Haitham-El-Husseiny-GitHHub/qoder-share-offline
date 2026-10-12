#!/data/data/com.termux/files/usr/bin/sh
# Shared idempotent startup for Offline, Qoder Cloud, OpenCode and Rish recovery.
export PATH=/data/data/com.termux/files/usr/bin:/system/bin
export PREFIX=/data/data/com.termux/files/usr
export TMPDIR=/data/data/com.termux/files/usr/tmp
base=/data/data/com.termux/files/home/qoder-selfhost
mkdir -p "$base/runtime"
date -u +%Y-%m-%dT%H:%M:%SZ > "$base/runtime/bridge-last-start.txt"
termux-wake-lock
exec 9>"$base/runtime/bridge-start.lock"
flock -n 9 || exit 0
for name in qoder-selfhost opencode qoder-bridge; do
    service="$PREFIX/var/service/$name"
    [ -x "$service/run" ] || continue
    if ! sv status "$service" >/dev/null 2>&1; then
        nohup runsv "$service" </dev/null >/dev/null 2>&1 9>&- &
    fi
    sv up "$service"
done
