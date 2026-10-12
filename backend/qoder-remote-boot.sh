#!/data/data/com.termux/files/usr/bin/bash
export PATH=/data/data/com.termux/files/usr/bin:/system/bin
export PREFIX=/data/data/com.termux/files/usr
export TMPDIR=/data/data/com.termux/files/usr/tmp
termux-wake-lock
python - <<'PYCODE'
import sys
sys.path.insert(0,'/data/data/com.termux/files/home/qoder-selfhost')
from restart_localhost import daemons,restart
if not daemons():restart()
PYCODE
