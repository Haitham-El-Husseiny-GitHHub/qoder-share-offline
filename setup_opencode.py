"""Install pinned OpenCode for an ARM64 Termux phone with an existing glibc runner."""
import os,subprocess,shutil
from pathlib import Path
HOME=Path('/data/data/com.termux/files/home');PREFIX=Path('/data/data/com.termux/files/usr')
def setup():
 if not shutil.which('grun'):raise SystemExit('Install/configure the Termux glibc runner first; OpenCode ARM64 is a Linux binary.')
 if not shutil.which('npm'):raise SystemExit('Node.js/npm is required.')
 runtime=HOME/'opencode-runtime';runtime.mkdir(exist_ok=True)
 env={**os.environ,'PREFIX':str(PREFIX),'TMPDIR':str(PREFIX/'tmp')}
 packed=subprocess.check_output(['npm','pack','opencode-linux-arm64@1.19.0','--silent'],cwd=runtime,env=env,text=True).strip().splitlines()[-1]
 subprocess.run(['tar','-xzf',packed],cwd=runtime,env=env,check=True)
 subprocess.run(['grun',str(runtime/'package/bin/opencode'),'--version'],env=env,check=True)
 shutil.copy2(Path(__file__).parent/'backend/opencode_start.py',runtime/'start-server.py')
 service=PREFIX/'var/service/opencode';service.mkdir(parents=True,exist_ok=True)
 run=service/'run';run.write_text('#!'+str(PREFIX/'bin/sh')+'\nexec '+str(PREFIX/'bin/python')+' '+str(runtime/'start-server.py')+'\n');run.chmod(0o700)
 print('Installed OpenCode 1.19.0. Enable the opencode Termux service with sv-enable opencode.')
if __name__=='__main__':setup()
