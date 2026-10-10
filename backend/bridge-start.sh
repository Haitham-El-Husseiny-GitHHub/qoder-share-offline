#!/data/data/com.termux/files/usr/bin/sh
# Idempotent recovery; never restarts a healthy backend or a loaded model.
export PATH=/data/data/com.termux/files/usr/bin:/system/bin
export TMPDIR=/data/data/com.termux/files/usr/tmp
termux-wake-lock
exec 9>/data/data/com.termux/files/home/qoder-selfhost/runtime/bridge-start.lock
flock -n 9 || exit 0
service=/data/data/com.termux/files/usr/var/service/qoder-selfhost
if ! sv status "$service" >/dev/null 2>&1; then
    nohup runsv "$service" </dev/null >/dev/null 2>&1 9>&- &
fi
sv up "$service"
