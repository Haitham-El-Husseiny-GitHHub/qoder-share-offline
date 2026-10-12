#!/data/data/com.termux/files/usr/bin/python3
"""Restart and verify only the localhost Qoder remote-control daemon."""
import fcntl, json, os, signal, subprocess, time
from pathlib import Path
HOME=Path('/data/data/com.termux/files/home')
PREFIX=Path('/data/data/com.termux/files/usr')
STATE=HOME/'.local/state/qoder'

def is_localhost_daemon(args):
    executable=any(str(a).startswith(str(PREFIX)) and Path(a).name in {'qodercli','qodercli.js'} for a in args)
    if not executable or 'remote-control' not in args or '--name' not in args:return False
    i=args.index('--name')
    return i+1<len(args) and args[i+1]=='localhost'

def daemons():
    result=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            args=[a.decode(errors='replace') for a in (p/'cmdline').read_bytes().split(b'\0') if a]
            if is_localhost_daemon(args) and (p/'stat').read_text().rsplit(')',1)[1].split()[0] not in {'Z','X'}:result.append(int(p.name))
        except (OSError,ProcessLookupError):pass
    return result

def status():
    try:data=json.loads((STATE/'restart-status.json').read_text())
    except (OSError,ValueError):data={'phase':'idle'}
    pids=daemons()
    return {**data,'daemon_count':len(pids),'connected':data.get('phase')=='ready' and data.get('pid') in pids and len(pids)==1}

def restart():
    STATE.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'PREFIX':str(PREFIX),'PATH':str(PREFIX/'bin')+':/system/bin','TMPDIR':str(PREFIX/'tmp'),'TERMUX_VERSION':os.environ.get('TERMUX_VERSION','remote-session')}
    started=time.time()
    def save(phase,**extra):
        p=STATE/'restart-status.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps({'phase':phase,'requested_at':started,'checked_at':time.time(),**extra}));tmp.chmod(0o600);tmp.replace(p)
    with (STATE/'restart.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        save('restarting')
        try:
            subprocess.run([str(PREFIX/'bin/termux-wake-lock')],timeout=5,check=False,env=env)
            old=daemons()
            for pid in old:
                try:os.kill(pid,signal.SIGTERM)
                except ProcessLookupError:pass
            for _ in range(80):
                if not set(old).intersection(daemons()):break
                time.sleep(.1)
            if set(old).intersection(daemons()):raise ValueError('Previous localhost daemon did not stop.')
            logpath=STATE/'remote-control.log';offset=logpath.stat().st_size if logpath.exists() else 0
            with logpath.open('ab',buffering=0) as log:
                child=subprocess.Popen([str(PREFIX/'bin/node'),str(PREFIX/'lib/node_modules/@qoder-ai/qodercli/bundle/qodercli.js'),'remote-control','--name','localhost','--directory',str(HOME)],cwd=HOME,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
            (STATE/'remote-control.pid').write_text(str(child.pid)+'\n')
            for _ in range(40):
                if child.poll() is not None:raise ValueError('Localhost startup failed. Check Termux login.')
                with logpath.open('rb') as log:log.seek(offset);fresh=log.read(262144).decode(errors='replace')
                if 'Remote Control Connected' in fresh and daemons()==[child.pid]:
                    save('ready',pid=child.pid);print('Localhost reconnected');return
                time.sleep(1)
            raise ValueError('Localhost connection was not confirmed within 40 seconds.')
        except Exception as exc:
            save('failed',error=str(exc));raise

if __name__=='__main__':restart()
