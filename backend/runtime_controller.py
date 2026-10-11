#!/usr/bin/env python3
import argparse,fcntl,json,os,signal,subprocess,time,sys
from pathlib import Path
from runtime_config import RUNTIME,KEY_FILE,PORT,MODELS,ensure,request,model_catalog,EXPECTED,context_plan
STATE=RUNTIME/'server.json'
def alive(pid):
    try:return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[0] not in ('Z','X')
    except (OSError,IndexError):return False
def owned(pid):
    try:
        args=Path('/proc',str(pid),'cmdline').read_bytes().split(b'\0')
        return str(KEY_FILE).encode() in args and str(PORT).encode() in args and any(b'llama-server' in a for a in args)
    except OSError:return False
def start(route):
    ensure()
    with (RUNTIME/'server.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('A coding task or model switch is running.')
        model,path=MODELS[route]
        limits=context_plan(route)
        if not limits['fits']:raise ValueError('Not enough free phone RAM for this model and two context slots. Close other apps and retry.')
        context=limits['context_window']
        if route in EXPECTED:
            entry=next(m for m in model_catalog() if m['route']==route)
            if not entry['selectable']:raise ValueError(entry['reason'])
        with path.open('rb') as f:
            if f.read(4)!=b'GGUF' or path.stat().st_size<1_000_000:raise ValueError('Selected GGUF model is incomplete.')
        state=json.loads(STATE.read_text()) if STATE.exists() else {}
        pid=state.get('pid',0)
        if pid and alive(pid):
            if not owned(pid):raise ValueError('Runtime ownership check failed; no process stopped.')
            if state.get('route')!=route or state.get('model_path')!=str(path) or state.get('parallel')!=2 or state.get('context_policy_version')!=limits['policy_version']:
                try:
                    if any(s.get('is_processing') for s in request('/slots')):raise ValueError('Model is processing a request. Wait before switching.')
                except ValueError:raise
                except Exception:raise ValueError('Cannot verify model idle state.')
                os.killpg(pid,signal.SIGTERM)
                deadline=time.monotonic()+8
                while alive(pid) and time.monotonic()<deadline:time.sleep(.2)
                if alive(pid):os.killpg(pid,signal.SIGKILL)
                pid=0
        else:pid=0
        if not pid:
            # Only Qoder's own loopback runtime and private key are used.
            log=(RUNTIME/'server.log').open('ab',buffering=0)
            args=['/data/data/com.termux/files/usr/bin/llama-server','--model',str(path),'--alias',model,'--host','127.0.0.1','--port',str(PORT),'--api-key-file',str(KEY_FILE),'--ctx-size',str(context*2),'--parallel','2','--threads','6','--threads-batch','8','--batch-size','512','--ubatch-size','128','--flash-attn','on','--cache-type-k','q8_0','--cache-type-v','q8_0','--cache-ram','0','--ctx-checkpoints','0','--jinja','--reasoning-budget','0','--chat-template-kwargs','{"enable_thinking":false}','--no-webui']
            proc=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
            pid=proc.pid
            state={'pid':pid,'route':route,'model':model,'model_path':str(path),'port':PORT,'parallel':2,'context_window':context,'trained_context_window':limits['trained_context_window'],'context_policy_version':limits['policy_version']}
            temp=STATE.with_suffix('.tmp');temp.write_text(json.dumps(state));temp.chmod(0o600);temp.replace(STATE)
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            if not alive(pid):raise ValueError('Qoder model process stopped. Check runtime/server.log.')
            try:
                request('/health')
                ids=[m['id'] for m in request('/v1/models').get('data',[])]
                if model in ids:return state
            except Exception:pass
            time.sleep(1)
        if owned(pid) and alive(pid):os.killpg(pid,signal.SIGTERM)
        STATE.unlink(missing_ok=True)
        raise ValueError('Model loading timed out; partial runtime stopped.')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start']);parser.add_argument('--route',choices=list(MODELS),default='phone-code');args=parser.parse_args()
    try:print(json.dumps(start(args.route)))
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
