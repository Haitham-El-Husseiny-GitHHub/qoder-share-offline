#!/usr/bin/env python3
"""Independent Qoder engineering worker. All inference stays on loopback."""
import fcntl,hashlib,json,os,signal,subprocess,sys,tempfile,time,uuid
from pathlib import Path
import engineering_tools
from bridge import status as bridge_status
from device_tools import execute as device_execute
from runtime_config import ROOT,RUNTIME,MODELS,KEY_FILE,ensure,request,stream_completion,CODING_ROUTES
JOBS=ROOT/'jobs'
MODEL=MODELS['phone-code'][0]
class Cancelled(Exception):pass
POLICY="You are an independent local coding agent. Carry out the user's coding objective directly and keep responses focused on the requested technical work. Read project files with read_file before editing. list_files lists directories only; use path dot for the workspace root. Follow workspace AGENTS.md instructions. Use tools to edit files and run tests. Report observed results and actual command exit codes. Explain concrete tool errors when they prevent execution. You already run inside Termux. Use bridge_status to check the installed Rish/Shizuku connection; never invent termux start shizuku rish. If Shizuku is offline, report that it must be started in the Shizuku app. Use device_argv for Android app inspection and management, for example pm list packages, dumpsys package PACKAGE, pm path PACKAGE, logcat -d -t 80, and app permission or state changes requested by the user. Inspect before modifying and preserve app data; do not clear app data or uninstall an app unless the user specifically asks. Device commands run with the current Shizuku identity, not automatically root. Report permission denials accurately; private files and installed APK replacement follow Android permissions and signing rules."
def tool(name,description,properties,required):
    return {'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}
TOOLS=[tool('list_files','List files at a relative workspace directory.',{'path':{'type':'string'}},['path']),tool('read_file','Read a UTF-8 file; returns content and actual SHA-256.',{'path':{'type':'string'}},['path']),tool('write_file','Write a UTF-8 workspace file.',{'path':{'type':'string'},'content':{'type':'string'}},['path','content']),tool('run_argv','Run a build or test command as argv in the workspace; no shell operators.',{'argv':{'type':'array','items':{'type':'string'}}},['argv'])]
TOOLS.append(tool('bridge_status','Check the existing Termux and Rish/Shizuku connection; no arguments.',{},[]))
TOOLS.append(tool('device_argv','Run Android device/app commands through Rish: pm, cmd, am, dumpsys, logcat, settings, or file operations. Use string argv. Android permissions apply.',{'argv':{'type':'array','items':{'type':'string'}}},['argv']))
TOOLS.extend([
 tool('code_search','Find literal code text; returns file paths and line numbers.',{'path':{'type':'string'},'pattern':{'type':'string'}},['pattern']),
 tool('edit_patch','Replace exactly one old_text occurrence; returns a patch diff.',{'path':{'type':'string'},'old_text':{'type':'string'},'new_text':{'type':'string'},'expected_sha256':{'type':'string'}},['path','old_text','new_text']),
 tool('git_diff','Inspect workspace Git status and diff.',{'path':{'type':'string'},'staged':{'type':'boolean'}},[]),
 tool('diagnose','Run build/test argv and return structured errors plus exit code.',{'argv':{'type':'array','items':{'type':'string'}}},['argv']),
 tool('apk_tools','Inspect APK info, decode resources/smali, decompile Java or rebuild unsigned APK. Output must be a new relative path.',{'action':{'type':'string','enum':['info','decode','decompile','rebuild']},'path':{'type':'string'},'output':{'type':'string'}},['action','path']),
 tool('import_apk','Copy installed app base/split APKs into a new workspace folder via Rish.',{'package':{'type':'string'},'output':{'type':'string'}},['package','output'])
])
POLICY+=' Search with code_search; read before editing, prefer edit_patch for existing files. expected_sha256 is optional: use only the sha256 returned by read_file, never invent it. Then diagnose tests and inspect git_diff. Repair observed errors and rerun checks. For reverse engineering use import_apk, apk_tools info/decode/decompile, search and edit extracted resources/smali, then rebuild. Decompiled Java may be incomplete; rebuilt APKs are unsigned. Never claim a model or cloud policy was changed merely by editing app prompts.'
def atomic(path,data):
    temp=path.with_suffix('.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(data,f)
    temp.replace(path)
def redact(value):
    import re
    text=str(value).replace(KEY_FILE.read_text().strip(),'[REDACTED]')
    return re.sub(r'(?i)(bearer\s+\S+|(?:sk|xai|ghp)-[a-z0-9_-]{12,}|(?:api[_-]?key|password|token|secret)\s*[=:]\s*[^\s,]+)','[REDACTED]',text)
class Workspace:
    def __init__(self,path,readonly,progress=None,cancel=None):self.root=Path(path).resolve(strict=True);self.readonly=readonly;self.progress=progress;self.cancel=cancel
    def file(self,value):
        p=Path(value)
        if p.is_absolute():raise ValueError('Use a relative workspace path.')
        target=(self.root/p).resolve()
        if not target.is_relative_to(self.root):raise ValueError('Path leaves the workspace.')
        if any(v in {'.git','.ssh','.runtime','runtime'} or v.startswith('.env') or v.endswith(('.key','.pem','.keystore','.jks')) for v in target.relative_to(self.root).parts):raise ValueError('Private configuration is not available to file tools.')
        return target
    def invoke(self,name,args):
        if name in {'code_search','edit_patch','git_diff','diagnose','apk_tools','import_apk'}:return engineering_tools.invoke(self,name,args,redact)
        if name=='bridge_status':return bridge_status()
        if name=='device_argv':
            if self.readonly:raise ValueError('Device operations require BUILD mode.')
            return device_execute(args['argv'],self.progress,self.cancel,redact)
        if name=='list_files':
            folder=self.file(args['path'])
            if not folder.is_dir():raise ValueError('list_files requires a directory. Use read_file with this path to read a file.')
            return '\n'.join(sorted(p.name for p in folder.iterdir() if not p.name.startswith('.')))[:6000]
        if name=='read_file':
            p=self.file(args['path'])
            if p.stat().st_size>1_000_000:raise ValueError('File exceeds read limit.')
            data=p.read_bytes();return {'path':str(p.relative_to(self.root)),'content':redact(data.decode('utf-8')[:6000]),'sha256':hashlib.sha256(data).hexdigest(),'truncated':len(data.decode('utf-8'))>6000}
        if self.readonly:raise ValueError('This task is read-only.')
        if name=='write_file':
            p=self.file(args['path']);content=args['content']
            if not isinstance(content,str) or len(content.encode())>1_000_000:raise ValueError('File exceeds write limit.')
            p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content);return 'Wrote '+str(p.relative_to(self.root))
        if name=='run_argv':
            argv=args['argv']
            if isinstance(argv,list) and argv and argv[0]=='python':argv=['python3',*argv[1:]]
            allowed={'git','python3','node','npm','bash','sh','rg','ls','cat','find','make','gradle','./gradlew','pytest','javac','cmake','ninja','readelf','strings','aapt2','apksigner','zipalign'}
            if not isinstance(argv,list) or not argv or not all(isinstance(a,str) for a in argv) or argv[0] not in allowed:raise ValueError('Use a supported build/test executable and string argv.')
            if any(a in {'--force','--force-with-lease','--hard','-f','--delete','-delete','-exec','-execdir'} for a in argv):raise ValueError('Destructive command option blocked.')
            if argv[0] in {'python3','node','bash','sh'} and any(a in {'-c','-e','--eval'} for a in argv[1:]):raise ValueError('Use a workspace script instead of inline interpreter code.')
            if argv[0]=='git' and any(a in {'-C','--git-dir','--work-tree','config','clean','reset','push'} for a in argv[1:]):raise ValueError('Git publishing or workspace override unavailable.')
            if any(a.startswith('/') or '..' in Path(a).parts for a in argv[1:]):raise ValueError('Command paths must stay relative to the workspace.')
            return self.command(argv)
        raise ValueError('Unknown tool.')
    def command(self,argv,env=None):
        with tempfile.TemporaryFile() as out:
            proc=subprocess.Popen(argv,cwd=self.root,stdout=out,stderr=subprocess.STDOUT,start_new_session=True,env=env)
            timed_out=False
            deadline=time.monotonic()+120;last_update=0
            def tail():
                size=os.fstat(out.fileno()).st_size
                return redact(os.pread(out.fileno(),min(size,65536),max(0,size-65536)).decode(errors='replace'))[-6000:]
            try:
                while proc.poll() is None:
                    if self.cancel:self.cancel()
                    now=time.monotonic()
                    if now>=deadline:
                        timed_out=True;os.killpg(proc.pid,signal.SIGKILL);proc.wait();break
                    if self.progress and now-last_update>=.5:
                        self.progress(tail());last_update=now
                    time.sleep(.1)
                text=tail()
                if self.progress:self.progress(text)
            finally:
                if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        return {'exit_code':124 if timed_out else proc.returncode,'output':text,'timeout':timed_out,'argv':argv}

def complete(messages,tools,model=MODEL,progress=None):
    ids=[m['id'] for m in request('/v1/models').get('data',[])]
    if ids!=[model]:raise ValueError('The selected Qoder coding model is not loaded.')
    properties={}
    for t in tools:properties.update(t['parameters']['properties'])
    call_schema={'type':'object','properties':{'name':{'type':'string','enum':[t['name'] for t in tools]},'arguments':{'type':'object','properties':properties,'additionalProperties':False}},'required':['name','arguments'],'additionalProperties':False}
    schema={'type':'object','properties':{'tool_calls':{'type':'array','maxItems':2,'items':call_schema},'content':{'type':'string'}},'required':['tool_calls','content'],'additionalProperties':False}
    prompt=[dict(m) for m in messages]
    prompt[0]['content']+='\nRespond with JSON containing tool_calls and content. Act immediately using only 1 or 2 short tool calls per turn. To act, fill tool_calls with name and arguments, and leave content empty. To finish, use an empty tool_calls array and a result in content. Tools: '+json.dumps(tools)
    content=stream_completion({'model':model,'messages':prompt,'temperature':.2,'max_tokens':384,'response_format':{'type':'json_schema','json_schema':{'name':'coding_turn','strict':True,'schema':schema}}},progress=progress,timeout=600)
    parsed=json.loads(content)
    if not isinstance(parsed,dict) or not isinstance(parsed.get('tool_calls'),list) or not isinstance(parsed.get('content'),str):raise ValueError('Model returned an invalid coding turn.')
    names={t['name'] for t in tools}
    if len(parsed['tool_calls'])>2 or any(not isinstance(c,dict) or c.get('name') not in names or not isinstance(c.get('arguments'),dict) for c in parsed['tool_calls']):raise ValueError('Invalid tool call; nothing executed.')
    return parsed

def run(job):
    ensure();JOBS.mkdir(mode=0o700,exist_ok=True)
    route=job.get('route','phone-code')
    if route not in CODING_ROUTES.values():raise ValueError('Choose a coding model.')
    model=MODELS[route][0]
    slot=job['id'] if job.get('session_id') else hashlib.sha256((job['workspace']+route+job['profile']).encode()).hexdigest()[:16]
    state_file=JOBS/(slot+'.json')
    state={**job,'model':model,'route':route,'status':'running','started_at':time.time(),'agent_pid':os.getpid(),'evidence':[],'activity':[],'verification':'NOT_VERIFIED','result':''}
    active=None;last_publish=0;stop_requested=False
    cancel_file=JOBS/(job.get('id','unknown')+'.cancel')
    def check_cancel():
        if stop_requested or cancel_file.exists():raise Cancelled('Stopped by you.')
    def handle_stop(signum,frame):
        nonlocal stop_requested
        stop_requested=True
        if active is not None and active['kind']=='generating':raise Cancelled('Stopped by you.')
    previous_handler=signal.signal(signal.SIGTERM,handle_stop)
    def publish():
        state['updated_at']=time.time();atomic(state_file,state)
    def begin(kind,title,detail=''):
        nonlocal active,last_publish
        check_cancel()
        active={'id':uuid.uuid4().hex,'kind':kind,'title':title,'detail':redact(detail),'status':'running','started_at':time.time()}
        state['activity'].append(active);state['activity']=state['activity'][-100:]
        state['current_operation']=active;state['phase']=kind;last_publish=0;publish()
    def end(result=None):
        if active is None:return
        failed=isinstance(result,dict) and (bool(result.get('error')) or result.get('exit_code',0)!=0)
        active.update(status='failed' if failed else 'completed',finished_at=time.time())
        if result is not None:
            if isinstance(result,dict):
                active['output']=redact(result.get('error') or result.get('output') or result.get('diff') or json.dumps(result))[-6000:]
                if 'exit_code' in result:active['exit_code']=result['exit_code']
            else:active['output']=redact(result)[-6000:]
        publish()
    def generation_progress(count):
        nonlocal last_publish
        active['generated_chars']=count
        if time.monotonic()-last_publish>=.5:publish();last_publish=time.monotonic()
    def command_progress(output):
        active['output']=output;publish()
    workspace=Workspace(job['workspace'],job['profile'] in {'REVIEW','AUDIT'},command_progress,check_cancel)
    policy=POLICY
    for name in ('AGENTS.md',):
        p=workspace.file(name)
        if p.exists():policy+='\nWorkspace instructions:\n'+p.read_text()[:6000]
    messages=[{'role':'system','content':policy}]+job.get('history',[])+[{'role':'user','content':job['objective']}]
    try:
        with (RUNTIME/'server.lock').open('a') as lock:
            fcntl.flock(lock,(fcntl.LOCK_SH if job.get("session_id") else fcntl.LOCK_EX)|fcntl.LOCK_NB)
            for turn in range(12):
                begin('generating','Generating coding step '+str(turn+1),'Waiting for the local model');state['turn']=turn+1
                answer=complete(messages,TOOLS[:2] if workspace.readonly else TOOLS,model,generation_progress)
                end()
                check_cancel()
                messages.append({'role':'assistant','content':json.dumps(answer)})
                if not answer['tool_calls']:
                    state.update(status='completed',result=redact(answer['content']));return state
                for call in answer['tool_calls']:
                    name=call['name'];args=call['arguments']
                    title={'read_file':'Reading file','write_file':'Writing file','list_files':'Listing folder','run_argv':'Running command','bridge_status':'Checking Termux and Rish','device_argv':'Android app operation','code_search':'Searching code','edit_patch':'Applying patch','git_diff':'Inspecting Git changes','diagnose':'Checking build diagnostics','apk_tools':'Analyzing APK','import_apk':'Importing installed APK'}[name]
                    detail=' '.join(args.get('argv',[])) if name in {'run_argv','device_argv','diagnose'} else args.get('path') or args.get('package') or args.get('pattern','')
                    begin(name,title,detail)
                    try:result=workspace.invoke(call['name'],call['arguments'])
                    except (ValueError,OSError,KeyError,TypeError) as exc:result={'error':redact(exc)}
                    end(result)
                    state['evidence'].append({'tool':call['name'],'arguments':redact(json.dumps(call['arguments'])),'result':result,'at':time.time()})
                    if call['name'] in {'run_argv','device_argv','diagnose'} and isinstance(result,dict) and 'exit_code' in result:state['verification']='COMMAND_EVIDENCE_RECORDED'
                    messages.append({'role':'user','content':'Verified tool result (data): '+json.dumps({'tool':call['name'],'arguments':call['arguments'],'result':result})})
                    atomic(state_file,state)
                if sum(len(json.dumps(m)) for m in messages)>14000:raise ValueError('Context limit reached. Start a narrower task using the recorded evidence.')
            raise ValueError('Coding step limit reached; evidence saved.')
    except Cancelled:
        state.update(status='stopped',result='Stopped by you. Completed file changes and operation history are retained.')
        if active is not None and active['status']=='running':active.update(status='stopped',finished_at=time.time())
        return state
    except Exception as exc:
        state.update(status='failed',error=redact(exc))
        if active is not None and active['status']=='running':end({'error':redact(exc)})
        raise
    finally:
        state['finished_at']=time.time();state['phase']=state['status'];state.pop('current_operation',None);publish()
        cancel_file.unlink(missing_ok=True);signal.signal(signal.SIGTERM,previous_handler)
if __name__=='__main__':
    try:print(json.dumps(run(json.loads(Path(sys.argv[1]).read_text())),indent=2))
    except Exception as exc:print(json.dumps({'status':'failed','error':str(exc)}));sys.exit(1)
