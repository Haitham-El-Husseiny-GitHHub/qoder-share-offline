import os,secrets,subprocess
from pathlib import Path
home=Path('/data/data/com.termux/files/home'); runtime=home/'opencode-runtime'
key=runtime/'server.password'
if not key.exists():
 fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(32))
env={**os.environ,'PREFIX':'/data/data/com.termux/files/usr','TMPDIR':'/data/data/com.termux/files/usr/tmp','PATH':'/data/data/com.termux/files/usr/bin:/system/bin','OPENCODE_SERVER_PASSWORD':key.read_text().strip(),'OPENCODE_SERVER_USERNAME':'opencode'}
os.chdir(home)
os.execvpe('grun',['grun',str(runtime/'package/bin/opencode'),'serve','--hostname','127.0.0.1','--port','4096'],env)
