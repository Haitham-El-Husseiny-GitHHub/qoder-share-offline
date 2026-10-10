#!/usr/bin/env python3
import urllib.parse
import json, urllib.request, urllib.error, threading, subprocess, time, sys, uuid, hashlib, os, signal
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent
ORIGIN="http://127.0.0.1:8767"
from runtime_config import UPSTREAM, KEY_FILE, ensure, MODELS, CODING_ROUTES, model_catalog
ensure()

CONTROL_SCRIPT=str(ROOT/'runtime_controller.py')
ROUTES={
    'chat': {'route':'phone-chat','id':'Llama3-8B-Abliterated-Q4_K_M','name':'Chat · Llama 3 8B Abliterated'},
    'coding': {'route':'phone-code','id':'Qwen2.5-Coder-3B-Abliterated','name':'Coding · Qwen2.5-Coder 3B Abliterated'},
}
for mode,route in CODING_ROUTES.items():
    ROUTES[mode]={'route':route,'id':MODELS[route][0],'name':mode}
RUNTIME_LOCK=threading.Lock()
SWITCH={'loading':False,'error':None,'target':None}
PHONE_HOME=Path('/data/data/com.termux/files/home')
DEFAULT_WORKSPACE=PHONE_HOME/'coding-workspace'
JOB={'status':'idle'}
JOB_GUARD=threading.Lock()
try:
    JOB.update(json.loads((ROOT/"jobs"/"latest.json").read_text()))
    if JOB.get("status")=="running":JOB.update(status="interrupted",error="Service restarted; inspect project files before starting another task.")
except (OSError,ValueError):pass
from bridge import status as bridge_status
from session_store import SessionStore
SESSIONS=SessionStore(RUNTIME_LOCK)
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def valid(self, navigation=False):
        if self.headers.get("Host") != "127.0.0.1:8767":
            return False
        # Android app links may carry cross-site navigation metadata.
        # Only the landing page accepts top-level document navigation.
        if navigation and self.command == "GET" and self.headers.get("Sec-Fetch-Mode") == "navigate" and self.headers.get("Sec-Fetch-Dest") == "document":
            return True
        return self.headers.get("Origin", ORIGIN) == ORIGIN and self.headers.get("Sec-Fetch-Site", "same-origin") in ("none", "same-origin")
    def answer(self,code,data,mime="application/json"):
        raw=json.dumps(data).encode() if mime=="application/json" else data
        self.send_response(code)
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(raw)
    def upstream(self,path,data=None):
        try:
            key=KEY_FILE.read_text().strip()
            request=urllib.request.Request(UPSTREAM+path,data=data,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request,timeout=240 if data else 10) as r:
                return r.status,json.loads(r.read(8*1024*1024))
        except urllib.error.HTTPError as e:
            try: body=json.loads(e.read(65536))
            except Exception: body={"error":{"message":"Upstream HTTP "+str(e.code)}}
            return e.code,body
        except Exception:
            return 502,{"error":{"message":"Local model runtime unavailable or timed out. Tap Refresh when it is ready."}}
    def runtime_status(self):
        if SWITCH['loading']:
            return 200,{'status':'LOADING','phase':'Loading '+str(SWITCH['target'])+' · one model at a time','ready':None,'hourly_usd':0}
        code,health=self.upstream('/health')
        if code!=200:
            return 200,{'status':'OFFLINE','phase':SWITCH['error'] or 'Choose Chat or Coding to load a local model','ready':None,'hourly_usd':0}
        code,catalog=self.upstream('/v1/models')
        if code!=200:
            return code,catalog
        models=catalog.get('data',[])
        model=models[0]['id'] if models else None
        active=next((m for m in model_catalog() if m['id']==model),{})
        return 200,{'status':'READY' if model else 'No model loaded','phase':SWITCH['error'] or 'Independent Qoder runtime · zero provider credits','ready':model,'coding_ready':bool(active),'model_name':active.get('name',model),'hourly_usd':0,'context_window':models[0].get('meta',{}).get('n_ctx') if models else None}
    def switch_worker(self,mode):
        try:
            result=subprocess.run([sys.executable,CONTROL_SCRIPT,'start','--route',ROUTES[mode]['route']],capture_output=True,text=True,timeout=150)
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout).strip()[:500] or 'Local model switch failed')
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                code,health=self.upstream('/health')
                if code==200:
                    code,catalog=self.upstream('/v1/models')
                    if code==200 and any(m.get('id')==ROUTES[mode]['id'] for m in catalog.get('data',[])):
                        SWITCH['error']=None
                        return
                time.sleep(2)
            raise RuntimeError('Model loading timed out. Tap Refresh to check or try again.')
        except Exception as exc:
            SWITCH['error']=str(exc)
            if mode!='coding':
                try:
                    fallback=subprocess.run([sys.executable,CONTROL_SCRIPT,'start','--route','phone-code'],capture_output=True,text=True,timeout=150)
                    SWITCH['error']+='; Qwen 3B restored' if not fallback.returncode else '; reload Qwen 3B to recover'
                except Exception:pass
        finally:
            SWITCH['loading']=False
            RUNTIME_LOCK.release()
    def switch_model(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1024:raise ValueError()
            mode=json.loads(self.rfile.read(length)).get('mode')
            if mode not in ROUTES:raise ValueError()
            if mode in CODING_ROUTES:
                entry=next(m for m in model_catalog() if m['mode']==mode)
                if not entry['selectable']:return self.answer(409,{'error':entry['reason']})
        except (ValueError,TypeError,AttributeError):
            return self.answer(400,{'error':{'message':'Choose Chat or Coding'}})
        if not RUNTIME_LOCK.acquire(blocking=False):
            return self.answer(409,{'error':{'message':'A reply or model switch is in progress. Wait for it to finish.'}})
        handed_off=False
        try:
            code,slots=self.upstream('/slots')
            if code==200 and isinstance(slots,list):
                if any(slot.get('is_processing') for slot in slots):
                    return self.answer(409,{'error':{'message':'The local model is answering another request. Retry when it finishes.'}})
            elif code not in (502,503):
                return self.answer(409,{'error':{'message':'Cannot verify whether the local model is busy. Retry later.'}})
            SWITCH.update(loading=True,error=None,target=ROUTES[mode]['id'])
            threading.Thread(target=self.switch_worker,args=(mode,),daemon=True).start()
            handed_off=True
            self.answer(202,{'status':'LOADING','model':ROUTES[mode]['id']})
        finally:
            if not handed_off:
                SWITCH['loading']=False
                RUNTIME_LOCK.release()
    def coding_status(self):
        with SESSIONS.guard:
            if SESSIONS.active:
                sid=next(iter(SESSIONS.active));snapshot=SESSIONS.snapshot(sid)
                return snapshot['current']
        with JOB_GUARD:
            data=dict(JOB)
        data['default_workspace']=str(DEFAULT_WORKSPACE)
        if data.get('status')=='running' and data.get('state_file'):
            try:
                state=json.loads(Path(data['state_file']).read_text())
                if state.get('id')==data.get('id'):
                    for key in ('evidence','activity','current_operation','phase','turn','updated_at','started_at'):
                        if key in state:data[key]=state[key]
            except (OSError,ValueError):pass
        if data.get('status')=='running':data['observed_at']=time.time()
        data.pop('state_file',None)
        return data
    def coding_worker(self,request,request_file):
        try:
            result=subprocess.run([sys.executable,str(ROOT/'coding_runner.py'),str(request_file)],capture_output=True,text=True,timeout=2400,env={**os.environ,'TMPDIR':'/data/data/com.termux/files/usr/tmp'})
            slot=hashlib.sha256((request['workspace']+request['route']+request['profile']).encode()).hexdigest()[:16]
            state_file=ROOT/'jobs'/(slot+'.json')
            state=json.loads(state_file.read_text()) if state_file.exists() else {}
            state.pop('messages',None)
            with JOB_GUARD:
                JOB.update({k:v for k,v in state.items() if k!='id'})
                JOB['status']=state['status'] if result.returncode==0 and state.get('status') in {'completed','stopped'} else 'failed'
                JOB.pop('cancel_requested',None)
                if JOB['status']=='failed':JOB['error']=state.get('error') or 'Local coding worker failed. Check the installed tool engine.'
        except Exception:
            with JOB_GUARD:JOB.update(status='failed',error='Coding worker timed out or could not finish.')
        finally:
            request_file.unlink(missing_ok=True)
            try:
                with JOB_GUARD:snapshot=dict(JOB)
                tmp=ROOT/"jobs"/"latest.tmp"
                fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
                with os.fdopen(fd,"w") as f:json.dump(snapshot,f)
                tmp.replace(ROOT/"jobs"/"latest.json")
            finally:RUNTIME_LOCK.release()
    def stop_coding(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<1024:raise ValueError()
            data=json.loads(self.rfile.read(length))
            with JOB_GUARD:
                if data.get('id')!=JOB.get('id'):return self.answer(409,{'error':'The active task changed. Refresh before stopping.'})
                if JOB.get('status')!='running':return self.answer(200,{'status':JOB.get('status')})
                jobid=JOB['id']
                if len(jobid)!=32 or any(c not in '0123456789abcdef' for c in jobid):raise ValueError()
                cancel=ROOT/'jobs'/(jobid+'.cancel')
                fd=os.open(cancel,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
                with os.fdopen(fd,'w') as out:out.write('stop')
                JOB['cancel_requested']=True
                try:
                    state=json.loads(Path(JOB['state_file']).read_text())
                    pid=state.get('agent_pid',0)
                    args=Path('/proc',str(pid),'cmdline').read_bytes().split(b'\0')
                    if state.get('id')==jobid and str(ROOT/'coding_runner.py').encode() in args and str(ROOT/'jobs'/(jobid+'.request.json')).encode() in args:
                        os.kill(pid,signal.SIGTERM)
                except (OSError,ValueError,KeyError):pass
            return self.answer(202,{'status':'stopping','id':jobid})
        except (ValueError,TypeError,AttributeError):return self.answer(400,{'error':'Choose the active coding task to stop.'})
    def start_coding(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=20000:raise ValueError()
            data=json.loads(self.rfile.read(length))
            objective=data.get('objective','').strip()
            profile=data.get('profile','BUILD')
            if not objective or len(objective)>8000 or profile not in {'BUILD','FIX','VERIFY','REVIEW','AUDIT'}:raise ValueError()
            DEFAULT_WORKSPACE.mkdir(exist_ok=True)
            workspace=Path(data.get('workspace',str(DEFAULT_WORKSPACE))).resolve(strict=True)
            if not workspace.is_dir() or not any(workspace.is_relative_to(base) for base in (DEFAULT_WORKSPACE,PHONE_HOME/'projects')):raise ValueError()
            if workspace==PHONE_HOME/'projects':raise ValueError()
        except (ValueError,TypeError,AttributeError,OSError):
            return self.answer(400,{'error':'Choose an existing project inside ~/projects or ~/coding-workspace and enter a coding objective.'})
        if not RUNTIME_LOCK.acquire(blocking=False):return self.answer(409,{'error':'A local reply, coding task or model switch is already running.'})
        handed_off=False
        try:
            code,catalog=self.upstream('/v1/models')
            active=next((m for m in model_catalog() if any(v.get('id')==m['id'] for v in catalog.get('data',[]))),None)
            if code!=200 or not active:
                return self.answer(409,{'error':'Load the coding model first.'})
            code,slots=self.upstream('/slots')
            if code!=200 or not isinstance(slots,list) or any(s.get('is_processing') for s in slots):
                return self.answer(409,{'error':'Local model is busy or readiness cannot be verified.'})
            request={'workspace':str(workspace),'objective':objective,'profile':profile,'route':active['route']}
            jobid=uuid.uuid4().hex
            request['id']=jobid
            jobs=ROOT/'jobs';jobs.mkdir(mode=0o700,exist_ok=True)
            request_file=jobs/(jobid+'.request.json')
            fd=os.open(request_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:json.dump(request,f)
            slot=hashlib.sha256((str(workspace)+active['route']+profile).encode()).hexdigest()[:16]
            state_file=jobs/(slot+'.json');state_file.unlink(missing_ok=True)
            with JOB_GUARD:
                JOB.clear();JOB.update(status='running',**request,state_file=str(state_file),model=active['id'],qoder_credits=0)
            threading.Thread(target=self.coding_worker,args=(request,request_file),daemon=True).start()
            handed_off=True
            return self.answer(202,{'id':jobid,'status':'running'})
        finally:
            if not handed_off:RUNTIME_LOCK.release()
    def session_post(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=20000:raise ValueError('Invalid session request.')
            data=json.loads(self.rfile.read(length));sid=data.get('session')
            if self.path=='/api/sessions':return self.answer(200,SESSIONS.manage(data))
            if self.path=='/api/session/stop':return self.answer(202,SESSIONS.stop(sid,data.get('id')))
            objective=data.get('objective','').strip();profile=data.get('profile','BUILD')
            if not objective or len(objective)>8000 or profile not in {'BUILD','FIX','VERIFY','REVIEW','AUDIT'}:raise ValueError('Enter a coding objective.')
            workspace=Path(data.get('workspace',str(DEFAULT_WORKSPACE))).resolve(strict=True)
            if not workspace.is_dir() or not any(workspace.is_relative_to(base) for base in (DEFAULT_WORKSPACE,PHONE_HOME/'projects')) or workspace==PHONE_HOME/'projects':raise ValueError('Choose an existing project folder.')
            code,catalog=self.upstream('/v1/models')
            active=next((m for m in model_catalog() if any(v.get('id')==m['id'] for v in catalog.get('data',[]))),None)
            if code!=200 or not active:raise ValueError('Load a coding model first.')
            code,slots=self.upstream('/slots')
            if code!=200 or not isinstance(slots,list) or len(slots)<2:raise ValueError('Reload the model to enable two coding slots.')
            SESSIONS.reserve(sid,{'workspace':str(workspace),'objective':objective,'profile':profile,'route':active['route'],'model':active['id']})
            return self.answer(202,SESSIONS.launch(sid))
        except (ValueError,TypeError,AttributeError,OSError) as exc:return self.answer(409,{'error':str(exc)})
    def do_GET(self):
        if not self.valid(navigation=self.path in ("/","/coding","/chat")): return self.answer(403,{"error":"Local origin required"})
        parsed=urllib.parse.urlsplit(self.path)
        if parsed.path in ('/api/sessions','/api/session','/api/session/export'):
            try:
                data=SESSIONS.listing() if parsed.path=='/api/sessions' else SESSIONS.snapshot(urllib.parse.parse_qs(parsed.query).get('session',[''])[0])
                return self.answer(200,data)
            except ValueError as exc:return self.answer(404,{'error':str(exc)})
        files={"/":("coding.html","text/html; charset=utf-8"),"/chat":("index.html","text/html; charset=utf-8"),"/app.js":("app.js","text/javascript; charset=utf-8"),"/coding":("coding.html","text/html; charset=utf-8"),"/coding.js":("coding.js","text/javascript; charset=utf-8")}
        if self.path in files:
            name,mime=files[self.path]
            return self.answer(200,(ROOT/name).read_bytes(),mime)
        if self.path == '/api/bridge':return self.answer(200,bridge_status())
        if self.path == '/api/status':
            code,body=self.runtime_status()
            return self.answer(code,body)
        if self.path == '/api/coding':
            return self.answer(200,self.coding_status())
        if self.path == '/api/models':
            return self.answer(200,{'object':'list','data':model_catalog()})
        paths={}
        if self.path not in paths:return self.answer(404,{"error":"Unknown route"})
        code,body=self.upstream(paths[self.path]);self.answer(code,body)
    def do_POST(self):
        if not self.valid():return self.answer(403,{"error":"Local origin required"})
        if self.path in ('/api/sessions','/api/session/run','/api/session/stop'):return self.session_post()
        if self.path == '/api/coding/stop':
            return self.stop_coding()
        if self.path == '/api/coding':
            return self.start_coding()
        if self.path == '/api/switch':
            return self.switch_model()
        if self.path!="/api/chat":return self.answer(404,{"error":"Unknown route"})
        if not RUNTIME_LOCK.acquire(blocking=False):
            return self.answer(409,{'error':{'message':'Model switch or reply in progress. Wait for READY.'}})
        try:
            return self.complete_chat()
        finally:
            RUNTIME_LOCK.release()
    def complete_chat(self):
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=2*1024*1024:raise ValueError()
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict) or not isinstance(data.get("messages"),list) or not data["messages"]:raise ValueError()
            if any(not isinstance(m,dict) or m.get("role") not in ("system","user","assistant") or not isinstance(m.get("content"),str) for m in data["messages"]):raise ValueError()
            model=data.get("model")
            code,catalog=self.upstream("/v1/models")
            if code!=200:return self.answer(code,catalog)
            if model not in [m["id"] for m in catalog.get("data",[])]:raise ValueError()
            code,status=self.runtime_status()
            if code!=200:return self.answer(code,status)
            if status.get("ready")!=model:return self.answer(409,{"error":{"message":"Selected local model is not READY. Tap Refresh when it is loaded."}})
            payload={"model":model,"messages":data["messages"],"stream":False,"max_tokens":max(1,min(1024,int(data.get("max_tokens",1024))))}
        except (ValueError,TypeError,KeyError):
            return self.answer(400,{"error":{"message":"Invalid chat request"}})
        code,body=self.upstream("/v1/chat/completions",json.dumps(payload).encode())
        try:self.answer(code,body)
        except (BrokenPipeError,ConnectionResetError):pass
def boot_runtime():
    if not RUNTIME_LOCK.acquire(blocking=False):return
    SWITCH.update(loading=True,error=None,target=ROUTES['coding']['id'])
    try:
        result=subprocess.run([sys.executable,CONTROL_SCRIPT,'start','--route','phone-code'],capture_output=True,text=True,timeout=150)
        if result.returncode:SWITCH['error']=(result.stderr or 'Qoder model could not start.').strip()[:500]
    except Exception:SWITCH['error']='Qoder model startup timed out. Tap Load coding model to retry.'
    finally:SWITCH['loading']=False;RUNTIME_LOCK.release()
if __name__=="__main__":
    threading.Thread(target=boot_runtime,daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1",8767),Handler).serve_forever()

