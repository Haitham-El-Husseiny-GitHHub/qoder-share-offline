"""Independent persistent sessions sharing one two-slot inference runtime."""
import json,os,time,uuid,threading,subprocess,sys,signal
from pathlib import Path
from runtime_config import ROOT
from coding_runner import redact

class SessionStore:
    def __init__(self, runtime_lock, root=ROOT):
        self.root=Path(root);self.folder=self.root/'sessions';self.folder.mkdir(mode=0o700,exist_ok=True)
        self.guard=threading.RLock();self.runtime_lock=runtime_lock;self.active={};self.sessions={}
        for p in self.folder.glob('*.json'):
            try:
                s=json.loads(p.read_text());self.validate_id(s['id'])
                if s.get('current',{}).get('status')=='running':
                    try:
                        recovered=json.loads((self.root/'jobs'/(s['current']['id']+'.json')).read_text())
                        if recovered.get('id')==s['current']['id']:s['current'].update(recovered)
                    except (OSError,ValueError):pass
                    if s['current'].get('status')=='running':s['current'].update(status='interrupted',error='Service restarted. Run the same task to resume its saved workspace and verified steps.')
                    s.setdefault('jobs',[]).append(s.pop('current'));self.write(s)
                self.sessions[s['id']]=s
            except (OSError,ValueError,KeyError):continue
        marker=self.folder/'legacy-migrated'
        if not marker.exists():
            try:
                old=json.loads((self.root/'jobs/latest.json').read_text());self.validate_id(old['id'])
                if old.get('status')=='running':old.update(status='interrupted',error='Previous service task was interrupted.')
                sid=uuid.uuid4().hex;s={'id':sid,'name':'Previous coding session','saved':True,'workspace':old.get('workspace',''),'profile':old.get('profile','BUILD'),'jobs':[old]}
                old.pop('state_file',None);old.pop('history',None);self.write(s);self.sessions[sid]=s
            except (OSError,ValueError,KeyError):pass
            marker.touch(mode=0o600)
    @staticmethod
    def validate_id(value):
        if not isinstance(value,str) or len(value)!=32 or any(c not in '0123456789abcdef' for c in value):raise ValueError('Unknown session.')
        return value
    def get(self,sid):
        self.validate_id(sid)
        if sid not in self.sessions:raise ValueError('Session not found.')
        return self.sessions[sid]
    def write(self,s):
        s['updated_at']=time.time();p=self.folder/(s['id']+'.json');tmp=p.with_suffix('.tmp')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:json.dump(s,f)
        tmp.replace(p)
    def metadata(self,s):
        return {k:s.get(k) for k in ('id','name','saved','workspace','profile','updated_at')} | {'running':s['id'] in self.active,'job_count':len(s.get('jobs',[]))}
    def listing(self):
        with self.guard:return {'data':[self.metadata(s) for s in sorted(self.sessions.values(),key=lambda x:x['updated_at'],reverse=True)],'running_count':len(self.active)}
    def snapshot(self,sid):
        with self.guard:
            s=json.loads(json.dumps(self.get(sid)));current=s.get('current')
            if current and current.get('status')=='running':
                try:
                    state=json.loads((self.root/'jobs'/(current['id']+'.json')).read_text())
                    if state.get('id')==current['id']:current.update({k:v for k,v in state.items() if k not in ('messages','history','session_id')})
                except (OSError,ValueError):pass
                current['observed_at']=time.time()
            s['running_count']=len(self.active);return s
    def manage(self,data):
        with self.guard:
            action=data.get('action');sid=data.get('session')
            if action=='new':
                sid=uuid.uuid4().hex;s={'id':sid,'name':'New session','saved':False,'workspace':data.get('workspace',''),'profile':'BUILD','jobs':[]};self.write(s);self.sessions[sid]=s;return self.metadata(s)
            s=self.get(sid)
            if action=='save':
                name=data.get('name','').strip()
                if not name or len(name)>100:raise ValueError('Enter a session name up to 100 characters.')
                s.update(name=name,saved=True);self.write(s);return self.metadata(s)
            if sid in self.active:raise ValueError('Stop this session before clearing or deleting it.')
            if action=='clear' and s.get('saved'):return self.manage({'action':'new','workspace':s.get('workspace','')})
            if action not in ('clear','delete'):raise ValueError('Unknown session action.')
            jobs=s.get('jobs',[])
            for job in jobs:
                jid=self.validate_id(job['id'])
                for suffix in ('.json','.request.json','.cancel'):(self.root/'jobs'/(jid+suffix)).unlink(missing_ok=True)
            if action=='delete':
                (self.folder/(sid+'.json')).unlink(missing_ok=True);del self.sessions[sid];return {'deleted':sid}
            s['jobs']=[];s.pop('current',None);self.write(s);return self.metadata(s)
    def reserve(self,sid,request):
        with self.guard:
            s=self.get(sid)
            if sid in self.active:raise ValueError('This session already has an active task.')
            if len(self.active)>=2:raise ValueError('Two coding tasks are already running.')
            path=Path(request['workspace'])
            for other in self.active.values():
                existing=Path(other['workspace'])
                if path==existing or path.is_relative_to(existing) or existing.is_relative_to(path):raise ValueError('Parallel jobs need separate project folders or Git worktrees.')
            if not self.active and not self.runtime_lock.acquire(blocking=False):raise ValueError('Another task or model switch is active.')
            try:
                if not request.get('resume_from') and s.get('jobs'):
                    previous=s['jobs'][-1]
                    if previous.get('status') in {'interrupted','stopped','needs_verification'} and previous.get('objective')==request['objective'] and previous.get('target',previous.get('workspace'))==request['workspace']:
                        journal=self.root/'jobs'/(previous['id']+'.journal.json')
                        if journal.is_file():request['resume_from']=previous['id']
                history=[]
                for previous in s.get('jobs',[])[-2:]:
                    history.extend([{'role':'user','content':previous['objective'][:1000]},{'role':'assistant','content':str(previous.get('result') or previous.get('error') or previous['status'])[:1000]}])
                request.update(id=uuid.uuid4().hex,session_id=sid,history=history)
                self.active[sid]=request
                s.update(workspace=request['workspace'],profile=request['profile'],current={k:v for k,v in request.items() if k!='history'} | {'status':'running','qoder_credits':0})
                self.write(s)
            except Exception:
                self.active.pop(sid,None)
                if not self.active:self.runtime_lock.release()
                raise
    def worker(self,sid,request,request_file):
        state={'id':request['id'],'objective':request['objective'],'profile':request['profile'],'status':'failed','error':'Local worker could not finish.'}
        try:
            subprocess.run([sys.executable,str(self.root/'coding_runner.py'),str(request_file)],capture_output=True,text=True,timeout=2400,env={**os.environ,'TMPDIR':'/data/data/com.termux/files/usr/tmp'})
            path=self.root/'jobs'/(request['id']+'.json')
            if path.exists():state=json.loads(path.read_text())
            if state.get('status')=='running':state.update(status='failed',error='Worker interrupted before completion.')
        except Exception as exc:state['error']=redact(exc)
        finally:
            request_file.unlink(missing_ok=True)
            state.pop('history',None);state.pop('messages',None)
            with self.guard:
                s=self.get(sid);s.pop('current',None);s.setdefault('jobs',[]).append(state)
                if state.get('status')=='completed' and state.get('workspace'):s['workspace']=state['workspace']
                self.write(s)
                self.active.pop(sid,None)
                if not self.active:self.runtime_lock.release()
    def launch(self,sid):
        with self.guard:
            request=self.active[sid];jobs=self.root/'jobs';jobs.mkdir(mode=0o700,exist_ok=True);p=jobs/(request['id']+'.request.json')
            try:
                fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'w') as f:json.dump(request,f)
                threading.Thread(target=self.worker,args=(sid,request,p),daemon=True).start()
            except Exception:
                self.active.pop(sid,None);self.get(sid).pop('current',None)
                if not self.active:self.runtime_lock.release()
                raise
            return {'id':request['id'],'status':'running','session':sid}
    def stop(self,sid,jid):
        with self.guard:
            s=self.get(sid);job=self.active.get(sid)
            if not job or job['id']!=jid:raise ValueError('The active task changed. Refresh before stopping.')
            self.validate_id(jid);p=self.root/'jobs'/(jid+'.cancel');fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,'w') as f:f.write('stop')
            s['current']['cancel_requested']=True
            try:
                state=json.loads((self.root/'jobs'/(jid+'.json')).read_text());pid=state.get('agent_pid',0)
                args=Path('/proc',str(pid),'cmdline').read_bytes().split(b'\0')
                if state.get('id')==jid and str(self.root/'coding_runner.py').encode() in args and str(self.root/'jobs'/(jid+'.request.json')).encode() in args:os.kill(pid,signal.SIGTERM)
            except (OSError,ValueError):pass
            return {'status':'stopping','id':jid}
