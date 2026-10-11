"""Android shell operations through the already-authorized Rish bridge."""
import re, os, shlex, shutil, signal, subprocess, tempfile, time, uuid
from bridge import status
def execute(argv, progress=None, cancel=None, redact=str, timeout=120):
    if not isinstance(timeout,int) or isinstance(timeout,bool) or not 1<=timeout<=600:raise ValueError('Device timeout must be 1..600 seconds.')
    if not isinstance(argv,list) or not argv or len(argv)>128 or not all(isinstance(a,str) and '\0' not in a for a in argv):
        raise ValueError('Supply a command and arguments as a string argv array.')
    if sum(len(a) for a in argv)>16000:raise ValueError('Command exceeds length limit.')
    rish=shutil.which('rish')
    if not rish or not status()['rish_connected']:raise ValueError('Rish is offline. Start Shizuku and authorize Termux.')
    marker='/data/local/tmp/qoder-job-'+uuid.uuid4().hex+'.pid'
    command=shlex.join(argv)
    completion='QODER_DEVICE_EXIT_'+uuid.uuid4().hex
    script='echo $$ > '+marker+'; trap '+shlex.quote('rm -f '+marker)+' EXIT; group=$$; (sleep '+str(max(1,timeout-5))+' & sleeper=$!; trap \'kill "$sleeper"; exit\' TERM; wait "$sleeper"; /system/bin/kill -KILL -- "-$group") </dev/null >/dev/null 2>&1 & watchdog=$!; '+command+'; rc=$?; kill "$watchdog" 2>/dev/null; wait "$watchdog" 2>/dev/null; printf '+shlex.quote('\n'+completion+':%s\n')+' "$rc"; exit "$rc"'
    remote='/system/bin/setsid /system/bin/sh -c '+shlex.quote(script)
    def cleanup():
        # The recorded PID is also the isolated remote process group.
        code='if [ -f '+marker+' ]; then read p < '+marker+'; case "$p" in ""|*[!0-9]*) ;; *) /system/bin/kill -KILL -- "-$p" ;; esac; fi; rm -f '+marker
        try:subprocess.run([rish,'-c',code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=4)
        except (OSError,subprocess.TimeoutExpired):pass
    with tempfile.TemporaryFile() as out:
        proc=subprocess.Popen([rish,'-c',remote],stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+timeout;last_update=0;timed_out=False
        def tail():
            size=os.fstat(out.fileno()).st_size
            return redact(os.pread(out.fileno(),min(size,65536),max(0,size-65536)).decode(errors='replace'))[-6000:]
        try:
            while proc.poll() is None:
                if cancel:cancel()
                now=time.monotonic()
                if now>=deadline:timed_out=True;cleanup();os.killpg(proc.pid,signal.SIGKILL);proc.wait();break
                if progress and now-last_update>=.5:progress(tail());last_update=now
                time.sleep(.1)
            output=tail()
            matched=re.search(r'\n'+completion+r':(\d+)\n',output)
            exit_code=124 if timed_out else int(matched.group(1)) if matched else 255
            if matched:output=output[:matched.start()]+output[matched.end():]
            else:output+='\nRemote completion not confirmed.'
            if progress:progress(output)
            return {'argv':argv,'exit_code':exit_code,'output':output,'timeout':timed_out,'executor':'rish'}
        finally:
            if proc.poll() is None:
                cleanup();os.killpg(proc.pid,signal.SIGKILL);proc.wait()
