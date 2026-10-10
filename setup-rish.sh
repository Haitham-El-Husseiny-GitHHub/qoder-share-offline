#!/data/data/com.termux/files/usr/bin/sh
set -eu
[ "$#" = 1 ] || { echo 'Usage: sh setup-rish.sh /path/to/exported/rish_shizuku.dex'; exit 1; }
[ -f "$1" ] || { echo 'Export Rish files from the Shizuku app first.'; exit 1; }
base=/data/data/com.termux/files/usr/bin
# Preserve any existing local integration instead of silently replacing it.
[ ! -e "$base/rish" ] && [ ! -e "$base/rish_shizuku.dex" ] || { echo 'Rish already exists. Check it with rish -c id; existing files preserved.'; exit 0; }
cp "$1" "$base/rish_shizuku.dex"
chmod 400 "$base/rish_shizuku.dex"
mkdir -p /data/data/com.termux/files/home/.config/qoder-share
python3 -c 'import os,json,pathlib; p=pathlib.Path.home()/".config/qoder-share/android-env.json"; p.write_text(json.dumps({k:os.environ[k] for k in ["BOOTCLASSPATH","DEX2OATBOOTCLASSPATH","SYSTEMSERVERCLASSPATH"] if os.environ.get(k)})); p.chmod(0o600)'
cat > "$base/rish" <<'WRAPPER'
#!/data/data/com.termux/files/usr/bin/python3
import os,json
from pathlib import Path
import sys
p=Path.home()/'.config/qoder-share/android-env.json'
env=dict(os.environ)
if p.exists():
 for k,v in json.loads(p.read_text()).items():
  if not env.get(k):env[k]=v
for k in ('LD_PRELOAD','LD_LIBRARY_PATH'):env.pop(k,None)
env['RISH_APPLICATION_ID']='com.termux'
os.execve('/system/bin/app_process',['app_process','-Djava.class.path=/data/data/com.termux/files/usr/bin/rish_shizuku.dex','/system/bin','--nice-name=rish','rikka.shizuku.shell.ShizukuShellLoader',*sys.argv[1:]],env)
WRAPPER
chmod 700 "$base/rish"
echo 'Rish installed. Start Shizuku, then run: rish -c id and approve Termux access.'
