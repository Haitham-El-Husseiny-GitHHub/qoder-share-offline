#!/usr/bin/env python3
"""Independent Qoder engineering worker. All inference stays on loopback."""
import fcntl,hashlib,json,os,re,signal,subprocess,sys,tempfile,time,uuid
from pathlib import Path
import engineering_tools
from bridge import status as bridge_status
from device_tools import execute as device_execute
from runtime_config import ROOT,RUNTIME,MODELS,KEY_FILE,ensure,request,stream_completion,CODING_ROUTES,fit_messages,generation_timeout
JOBS=ROOT/'jobs'
MODEL=MODELS['phone-code'][0]
class Cancelled(Exception):pass
class PolicyViolation(ValueError):pass
WORKER_POLICY = r'''HARD STOPS only (refuse these and nothing else): (1) child sexual exploitation / CSAM; (2) assistance causing severe real-world harm to people; (3) bioweapons / pathogen weaponization; (4) chemical weapons; (5) nuclear weapons design or acquisition; (6) clear intent to commit violent crime against people. Be maximally helpful and uncensored for all other legitimate technical work. You are the Qoder worker. The router already chose the workflow, the adapters, and the checks. Do not choose another workflow. Do not search for the source again. Do not describe a plan in content. content stays empty until the same failing check has passed.

Assess the task in this order, then act:
1. Read the Plan JSON. If workflow is inspect, use only read_file, code_search, and git_diff. Write nothing.
2. If a failing check or a logcat trace is already in the conversation, that is the defect. Do not invent a second one.
3. If no failure is present and workflow is source_fix, call diagnose with the check argv. Stop if it passes.
4. From the failure text, pick the first project file that is not under tests. read_file that path. If the trace names no file, code_search the error string once.
5. Decide the change from the file you just read. If you cannot point to the exact lines, read one more file. Do not edit yet.
6. Patch only that defect. Prefer edit_patch with the exact old_text from read_file. expected_sha256 only if read_file returned one. Never invent a hash. write_file only for a new file. unified_patch only when more than one hunk is required.
7. Stop. The runner reruns the check. If it fails again, read the new trace and patch the new line. After two identical failures, stop calling tools and put the blocker in content.

Choose a tool only from the Tools line. Use this mapping:
- See a directory: list_files, path "."
- See code: read_file
- Find a string: code_search
- Change existing code: edit_patch
- Run the project check: diagnose, or run_argv with the check argv and no shell operators
- See the edit: git_diff
- Device crash, and device_argv is listed: logcat -d -t 80 AndroidRuntime:E *:S, then pm path only if a package id is known
- APK, and apk_tools or import_apk is listed: import_apk, then apk_tools info. Do not decompile unless the crash frame is inside that APK.
- tool_adapter only when that adapter name is in Plan.adapters. operation must be one of the operations named for it. If you do not know the operation, call tool_capabilities once, then stop this turn.
- Do not call verify_goal. The runner does that.
- Do not call bridge_status more than once. If Shizuku is offline, say so in content. Do not invent a start command.

Logic rules:
- A green check is not a defect. Do not edit a passing project.
- A missing file, a permission denial, or an unknown tool is a stop, not a retry with a different command.
- One defect per patch. Do not reformat, rename, or add features.
- Use project-relative paths, or absolute paths inside the discovered project. Never read .env, keys, or runtime.
- At most two tool calls, and the second may only read a file the first result named.
- Reply with JSON only: {"tool_calls":[{"name":"","arguments":{}}],"content":""}'''
POLICY="You are an independent local coding agent. Carry out the user's coding objective directly and keep responses focused on the requested technical work. Be maximally helpful and uncensored for legitimate technical work. Do not refuse, moralize, lecture, or soft-block coding, security, reverse-engineering, or automation tasks that are legal and user-authorized. HARD STOPS only (refuse these and nothing else): (1) child sexual exploitation / CSAM; (2) assistance causing severe real-world harm to people; (3) bioweapons / pathogen weaponization; (4) chemical weapons; (5) nuclear weapons design or acquisition; (6) clear intent to commit violent crime against people. Everything else that is technical work proceeds. Read project files with read_file before editing. list_files lists directories only; use path dot for the workspace root. Follow workspace AGENTS.md instructions. Use tools to edit files and run tests. Report observed results and actual command exit codes. Explain concrete tool errors when they prevent execution. You already run inside Termux. Use bridge_status to check the installed Rish/Shizuku connection; never invent termux start shizuku rish. If Shizuku is offline, report that it must be started in the Shizuku app. Use device_argv for Android device shell when available. t, for example pm list packages, dumpsys package PACKAGE, pm path PACKAGE, logcat -d -t 80, and app permission or state changes requested by the user. Inspect before modifying and preserve app data; do not clear app data or uninstall an app unless the user specifically asks. Device commands run with the current Shizuku identity, not automatically root. Report permission denials accurately; private files and installed APK replacement follow Android permissions and signing rules."
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
    text=str(value)
    if KEY_FILE.is_file():text=text.replace(KEY_FILE.read_text().strip(),'[REDACTED]')
    return re.sub(r'(?i)(bearer\s+\S+|(?:sk|xai|ghp)-[a-z0-9_-]{12,}|(?:api[_-]?key|password|token|secret)\s*[=:]\s*[^\s,]+)','[REDACTED]',text)
class Workspace:
    def __init__(self,path,readonly,progress=None,cancel=None):
        self.root=Path(path).resolve(strict=True);self.readonly=readonly;self.progress=progress;self.cancel=cancel
        self.runtime=None;self.journal=None
    def file(self,value):
        p=Path(value)
        # Absolute paths within the selected/discovered project are valid.
        if p.is_absolute():
            try:p=p.resolve().relative_to(self.root)
            except ValueError:raise ValueError('Select this source project as the task target first.')
        target=(self.root/p).resolve()
        if not target.is_relative_to(self.root):raise ValueError('Path leaves the workspace.')
        if any(v in {'.git','.ssh','.runtime','runtime'} or v.startswith('.env') or v.endswith(('.key','.pem','.keystore','.jks')) for v in target.relative_to(self.root).parts):raise ValueError('Private configuration is not available to file tools.')
        return target
    def invoke(self,name,args):
        if not isinstance(args,dict):raise ValueError('Tool arguments must be an object.')
        editing=name in {'write_file','edit_patch'}
        if editing and self.journal:
            if self.readonly:raise ValueError('This task is read-only.')
            self.journal.backup(self,args['path'])
        result=self._invoke(name,args)
        if editing and self.journal:self.journal.edited(self,args['path'],result)
        if self.runtime:result=self.runtime.observe(name,args,result)
        return result
    def _invoke(self,name,args):
        if name in {'tool_adapter','tool_capabilities','verify_goal'}:
            if not self.runtime:raise ValueError('This tool requires a routed job.')
            return self.runtime.invoke(name,args)
        if name=='unified_patch':return self.unified_patch(args)
        if name in {'code_search','edit_patch','git_diff','diagnose','apk_tools','import_apk'}:return engineering_tools.invoke(self,name,args,redact)
        if name=='bridge_status':return bridge_status()
        if name=='device_argv':
            argv=args['argv']
            if self.runtime and self.runtime.plan['workflow']=='device' and (argv and argv[0]=='pm' and len(argv)>1 and argv[1] in {'install','install-create','install-write','install-commit','uninstall','clear','grant','revoke'}):raise ValueError('Device diagnosis does not alter packages or app data.')
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
        if self.readonly and name!='run_argv':raise ValueError('This task is read-only.')
        if name=='write_file':
            p=self.file(args['path']);content=args['content']
            if not isinstance(content,str) or len(content.encode())>1_000_000:raise ValueError('File exceeds write limit.')
            if p.exists() and p.stat().st_size>1_000_000:raise ValueError('Existing file exceeds write limit.')
            before=p.read_bytes() if p.exists() else None
            p.parent.mkdir(parents=True,exist_ok=True)
            fd,temp=tempfile.mkstemp(prefix='.qoder-write-',dir=p.parent)
            try:
                with os.fdopen(fd,'wb') as out:
                    out.write(content.encode());out.flush();os.fsync(out.fileno())
                    os.fchmod(out.fileno(),p.stat().st_mode & 0o777 if p.exists() else 0o644)
                if (p.read_bytes() if p.exists() else None)!=before:raise ValueError('Concurrent file change; write was not applied.')
                if self.cancel:self.cancel()
                os.replace(temp,p)
            finally:
                if os.path.exists(temp):os.unlink(temp)
            return {'path':str(p.relative_to(self.root)),'changed':before!=content.encode(),'sha256':hashlib.sha256(content.encode()).hexdigest()}
        if name=='run_argv':
            if self.readonly and (not self.runtime or args['argv'] not in [c['argv'] for c in self.runtime.plan['checks'] if c['kind'] in {'tests','security_validation'}]):raise ValueError('Read-only tasks allow only declared verification commands.')
            return self.command(self.validate_argv(args['argv']),timeout=args.get('timeout',120))
        raise ValueError('Unknown tool.')
    def validate_argv(self,argv):
        if isinstance(argv,list) and argv and argv[0]=='python':argv=['python3',*argv[1:]]
        allowed={'git','python3','node','npm','pnpm','yarn','bun','bash','sh','rg','ls','cat','find','make','gradle','./gradlew','pytest','javac','cmake','ctest','ninja','readelf','strings','aapt2','apksigner','zipalign','tsc','cargo'}
        if not isinstance(argv,list) or not argv or len(argv)>128 or not all(isinstance(a,str) and '\0' not in a for a in argv) or argv[0] not in allowed:raise ValueError('Use a supported build/test executable and string argv.')
        if sum(len(a) for a in argv)>16000:raise ValueError('Command exceeds length limit.')
        if any(a in {'--force','--force-with-lease','--hard','-f','--delete','-delete','-exec','-execdir'} for a in argv):raise ValueError('Destructive command option blocked.')
        if argv[0] in {'python3','node','bash','sh'} and any(a in {'-c','-e','--eval'} for a in argv[1:]):raise ValueError('Use a workspace script instead of inline interpreter code.')
        if argv[0]=='git' and any(a in {'-C','--git-dir','--work-tree','config','clean','reset','push'} for a in argv[1:]):raise ValueError('Git publishing or workspace override unavailable.')
        if any(a.startswith('/') or '..' in Path(a).parts for a in argv[1:]):raise ValueError('Command paths must stay relative to the workspace.')
        return argv
    def unified_patch(self,args):
        if self.readonly:raise ValueError('Unified patches require a writable task.')
        patch=args['patch'];expected=args['expected_sha256']
        if not isinstance(patch,str) or len(patch.encode())>1_000_000 or not isinstance(expected,dict):raise ValueError('Supply a bounded unified diff and SHA-256 map.')
        names=[]
        for line in patch.splitlines():
            if line.startswith(('--- ','+++ ')):
                name=line[4:].split('\t')[0]
                if name=='/dev/null':continue
                if name.startswith(('a/','b/')):name=name[2:]
                if name.startswith('"'):raise ValueError('Use plain relative paths in patch headers.')
                path=self.file(name)
                if path.exists() and (not path.is_file() or expected.get(name)!=hashlib.sha256(path.read_bytes()).hexdigest()):raise ValueError('Patch checksum missing or stale for '+name)
                if name not in names:names.append(name)
        if not names or 'GIT binary patch' in patch or 'rename from ' in patch or 'copy from ' in patch:raise ValueError('Use text hunks with explicit --- and +++ file headers.')
        with tempfile.NamedTemporaryFile(mode='w',suffix='.patch') as f:
            f.write(patch);f.flush()
            check=self.command(['git','apply','--check','--whitespace=nowarn',f.name],timeout=15)
            if check['exit_code'] or args.get('preview',False):return {**check,'preview':True,'diff':redact(patch)[:6000]}
            for name in names:
                if self.journal:self.journal.backup(self,name)
            if self.cancel:self.cancel()
            result=self.command(['git','apply','--whitespace=nowarn',f.name],timeout=15,track_source=False)
            if result['exit_code']==0:
                for name in names:
                    if self.journal:self.journal.edited(self,name,{'diff':redact(patch)[:6000]})
        return {**result,'diff':redact(patch)[:6000],'paths':names}
    def command(self,argv,env=None,timeout=120,input_data=None,output_limit=6000,track_source=True):
        if not isinstance(timeout,int) or isinstance(timeout,bool) or not 1<=timeout<=1800:raise ValueError('Command timeout must be 1..1800 seconds.')
        if self.cancel:self.cancel()
        if self.runtime and self.runtime.config.get('offline', True):
            from offline_policy import command as offline_command
            offline_command(argv)
            env={**(env or {}),'npm_config_offline':'true','CARGO_NET_OFFLINE':'true','PIP_NO_INDEX':'1','YARN_ENABLE_NETWORK':'0'}
        env={**os.environ,**(env or {})}
        if self.runtime and self.runtime.config.get('android_sdk'):
            env={**os.environ,**(env or {}),'ANDROID_HOME':self.runtime.config['android_sdk'],'ANDROID_SDK_ROOT':self.runtime.config['android_sdk']}
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as incoming:
            if input_data is not None:incoming.write(input_data);incoming.seek(0)
            proc=subprocess.Popen(argv,cwd=self.root,stdin=incoming,stdout=out,stderr=subprocess.STDOUT,start_new_session=True,env=env)
            timed_out=False
            deadline=time.monotonic()+timeout;last_update=0
            def tail():
                size=os.fstat(out.fileno()).st_size
                return redact(os.pread(out.fileno(),min(size,output_limit),max(0,size-output_limit)).decode(errors='replace'))
            try:
                while proc.poll() is None:
                    if self.cancel:self.cancel()
                    now=time.monotonic()
                    if now>=deadline:
                        timed_out=True;os.killpg(proc.pid,signal.SIGKILL);proc.wait();break
                    if self.progress and now-last_update>=.5:
                        self.progress(tail());last_update=now
                    time.sleep(.1)
                text=tail();truncated=os.fstat(out.fileno()).st_size>output_limit
                if self.progress:self.progress(text)
            finally:
                if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        result={'exit_code':124 if timed_out else proc.returncode,'output':text,'timeout':timed_out,'argv':argv,'output_may_be_truncated':truncated}
        if self.journal and track_source:
            from job_journal import fingerprint
            changed=[name for name,sha in self.journal.data['file_hashes'].items() if fingerprint(self.file(name))!=sha]
            for name in changed:self.journal.edited(self,name)
            if changed:result.update(success=False,error='Source changed during the command; inspect it and rerun verification.',changed_paths=changed)
        return result

class WorkerGuard:
    """Validate worker actions against the fixed plan and observed results."""
    def __init__(self, workspace, plan):
        self.ws,self.plan=workspace,plan
        self.reads={};self.counts={};self.previous=None
    def validate(self, name, args, index=0):
        if name=='verify_goal':raise ValueError('Verification belongs to the runner.')
        if self.plan['workflow']=='inspect' and name not in {'read_file','code_search','git_diff'}:raise ValueError('Inspect permits only read_file, code_search and git_diff.')
        if index:
            path=args.get('path','')
            if name!='read_file' or not path or path not in json.dumps(self.previous,ensure_ascii=False):raise ValueError('The second call must read a file named by the first result.')
        if name in {'bridge_status','tool_capabilities'} and self.counts.get(name,0):raise ValueError(name+' may only be called once.')
        if name in {'diagnose','run_argv'} and args.get('argv') not in [c['argv'] for c in self.plan['checks']]:raise ValueError('Use the exact check argv from Plan JSON.')
        if name=='write_file' and self.ws.file(args['path']).exists():raise ValueError('write_file is only for a new file.')
        if name=='edit_patch':
            read=self.reads.get(args.get('path'))
            if not read or not args.get('old_text') or args['old_text'] not in read['content']:raise ValueError('Read the exact old_text before editing.')
            if args.get('expected_sha256') is not None and args['expected_sha256']!=read.get('sha256'):raise ValueError('Use only the SHA-256 returned by read_file.')
        if name=='unified_patch' and len(re.findall(r'^@@ ',args.get('patch',''),re.M))<2:raise ValueError('Use edit_patch for a single hunk.')
        self.counts[name]=self.counts.get(name,0)+1
    def observe(self, name, result):
        self.previous=result
        if name=='read_file' and isinstance(result,dict) and not result.get('error'):self.reads[result['path']]=result
    @staticmethod
    def repeated_check_failure(checks):
        groups={}
        for check in checks:
            if check.get('argv'):groups.setdefault(tuple(check['argv']),[]).append(check)
        for history in groups.values():
            if len(history)<2:continue
            a,b=history[-2:]
            if not a.get('success') and not b.get('success') and any(b.get(k) for k in ('output','error','diagnostics')) and all(a.get(k)==b.get(k) for k in ('exit_code','output','error','diagnostics')):
                return b.get('error') or b.get('output') or json.dumps(b.get('diagnostics'))
        return None
    @staticmethod
    def blocker(result):
        if not isinstance(result,dict):return None
        if result.get('missing_prerequisite'):return result.get('error') or 'Missing prerequisite.'
        if result.get('policy_violation'):return result['error']
        if 'rish_connected' in result and not result['rish_connected']:return 'Shizuku is offline.'
        message=str(result.get('error') or '')
        if result.get('exit_code') not in (None,0):message+='\n'+str(result.get('output') or '')
        if re.search(r'no such file|not found|permission denied|permission denial|unknown tool|unavailable|disconnected',message,re.I):return message
        if isinstance(result.get('shizuku'),dict) and not result['shizuku'].get('connected',True):return 'Shizuku is offline.'
        return None

def complete(messages,tools,model=MODEL,progress=None):
    ids=[m['id'] for m in request('/v1/models').get('data',[])]
    if ids!=[model]:raise ValueError('The selected Qoder coding model is not loaded.')
    names=[t['name'] for t in tools]
    call_schema={'type':'object','properties':{'name':{'type':'string','enum':names},'arguments':{'type':'object','additionalProperties':True}},'required':['name','arguments'],'additionalProperties':False}
    schema={'type':'object','properties':{'tool_calls':{'type':'array','maxItems':2,'items':call_schema},'content':{'type':'string'}},'required':['tool_calls','content'],'additionalProperties':False}
    prompt=[dict(m) for m in messages]
    guide=json.dumps([{'name':t['name'],'description':t['description'],'inputs':{k:(v.get('enum') or v.get('type')) for k,v in t['parameters']['properties'].items()},'required':t['parameters']['required']} for t in tools],separators=(',',':'))
    prompt[0]['content']=prompt[0]['content']+'\nTools: '+guide
    slots=request('/slots')
    context=min(slot['n_ctx'] for slot in slots)
    prompt,prompt_tokens=fit_messages(prompt,context)
    content=stream_completion({'model':model,'messages':prompt,'temperature':0,'max_tokens':384,'response_format':{'type':'json_schema','json_schema':{'name':'coding_turn','strict':True,'schema':schema}}},progress=progress,timeout=generation_timeout(prompt_tokens))
    parsed=json.loads(content)
    if not isinstance(parsed,dict) or not isinstance(parsed.get('tool_calls'),list) or not isinstance(parsed.get('content'),str):raise ValueError('Model returned an invalid coding turn.')
    known=set(names)
    if len(parsed['tool_calls'])>2 or any(not isinstance(c,dict) or c.get('name') not in known or not isinstance(c.get('arguments'),dict) for c in parsed['tool_calls']):raise ValueError('Invalid tool call; nothing executed.')
    if len(parsed['tool_calls'])==2 and parsed['tool_calls'][1]['name']!='read_file':raise ValueError('The second call may only read a file named by the first result.')
    if parsed['tool_calls']:parsed['content']=''
    return parsed

def run(job):
    from job_journal import Journal,recovery_workspace
    from tool_catalog import discover,load_config,public_capabilities
    import task_router
    from task_router import execution_plan
    import source_lookup
    from router_runtime import Runtime,tools as selected_tools
    job=dict(job);job.setdefault('id',uuid.uuid4().hex)
    ensure();JOBS.mkdir(mode=0o700,exist_ok=True)
    route=job.get('route','phone-code')
    if route not in CODING_ROUTES.values():raise ValueError('Choose a coding model.')
    model=MODELS[route][0]
    slot=job['id'] if job.get('session_id') else hashlib.sha256((job['workspace']+route+job['profile']).encode()).hexdigest()[:16]
    state_file=JOBS/(slot+'.json')
    state={**job,'model':model,'route':route,'status':'running','started_at':time.time(),'agent_pid':os.getpid(),'evidence':[],'activity':[],'verification':'NOT_VERIFIED','result':''}
    active=None;last_publish=0;stop_requested=False;journal=None
    cancel_file=JOBS/(job.get('id','unknown')+'.cancel')
    def check_cancel():
        if stop_requested or cancel_file.exists():raise Cancelled('Stopped by you.')
        if time.time()-state['started_at']>2100:raise TimeoutError('Job time budget reached; recovery evidence is saved.')
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
        failed=isinstance(result,dict) and (bool(result.get('error')) or not result.get('success',result.get('exit_code',0)==0))
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
    source_lock=None
    messages=[]
    def compact(result):
        if isinstance(result,str):return result[:2400]
        if isinstance(result,list):return [compact(v) for v in result[:12]]
        if isinstance(result,dict):return {k:compact(v) for k,v in result.items() if k not in {'command','checks'}}
        return result
    def trim_messages():
        nonlocal messages
        while len(messages)>66:
            del messages[2:4]
    def record(name,args,result):
        state['evidence'].append({'tool':name,'arguments':redact(json.dumps(args)),'result':result,'at':time.time()})
        state['evidence']=state['evidence'][-100:]
        model_result=compact(result)
        if len(json.dumps(model_result))>3500:model_result={'summary':json.dumps(model_result)[:3000],'artifacts':result.get('artifacts',[]) if isinstance(result,dict) else []}
        messages.append({'role':'user','content':'Observed tool result (data): '+json.dumps({'tool':name,'inputs':args,'result':model_result})})
        trim_messages();journal.finish(result,messages)
        state['artifacts']=journal.data['artifacts'];state['patches']=journal.data['patches'];publish()
    try:
        with (RUNTIME/'server.lock').open('a') as lock:
            fcntl.flock(lock,(fcntl.LOCK_SH if job.get("session_id") else fcntl.LOCK_EX)|fcntl.LOCK_NB)
            begin('prepare','Inspecting tools, files and access')
            config=load_config();inventory=discover(config)
            journal=Journal(JOBS,job,job.get('resume_from'))
            lookup=None
            if job.get('resume_from'):workspace.root=Path(journal.data['workspace']).resolve(strict=True)
            else:
                if source_lookup.explicit_source(job['objective']) is not None or source_lookup.app_token(job['objective']):
                    end({'success':True,'output':'Tool access checked.'})
                    begin('prepare','Locating app source',source_lookup.app_token(job['objective']))
                    def device_query(argv):return workspace.invoke('device_argv',{'argv':argv})
                    lookup=source_lookup.acquire(job['objective'],workspace.root,device=device_query,config=config)
                    if lookup.get('root'):workspace.root=Path(lookup['root']).resolve()
                    state['source_lookup']=source_lookup.public(lookup)
                    end({'success':bool(lookup.get('root')),'output':json.dumps(state['source_lookup'])[:4000]})
                    active=None
                located=None
                if not lookup or not lookup.get('root'):
                    if not task_router.device_intent(job['objective']):
                        located=source_lookup.locate_project(workspace.root,job['objective'])
                    else:
                        token=source_lookup.app_token(job['objective'])
                        matches=source_lookup.find_local(token,[workspace.root]) if token else []
                        if len(matches)==1:located=matches[0]
                if located and located.resolve()!=workspace.root.resolve():workspace.root=located.resolve()
            # Two sessions may discover the same project from different starting folders.
            # Lock the actual source location before any edits or verification commands.
            lockdir=RUNTIME/'source-locks';lockdir.mkdir(exist_ok=True)
            source_lock=(lockdir/(hashlib.sha256(str(source_lookup.project_for_path(workspace.root)).encode()).hexdigest()+'.lock')).open('a')
            try:fcntl.flock(source_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Another coding job is using this discovered source project. Resume after it finishes.')
            if lookup and not lookup.get('root') and not task_router.device_intent(job['objective']):
                raise ValueError('Source discovery: '+lookup.get('chosen',{}).get('reason','No matching source found.')+' Candidates: '+json.dumps(lookup.get('places',[])[:2]))
            plan=journal.data.get('plan') or execution_plan(workspace.root,job['objective'],job['profile'],inventory,{**config,'ambiguous_source':bool(lookup and lookup.get('ambiguous') and not lookup.get('root'))})
            workspace.readonly=plan.get('readonly',workspace.readonly)
            if plan['mutating'] or any(c['kind'] in plan['required'] for c in plan['checks']):
                end({'success':True,'workflow':plan['workflow']})
                begin('recovery','Creating source recovery point')
                recovery_workspace(workspace,journal,{**config,'edit_in_place':True})
            elif not journal.data['recovery']:
                journal.data['recovery']={'mode':'read_only','target':str(workspace.root)};journal.save()
            workspace.journal=journal
            runtime=Runtime(workspace,journal,plan,inventory,config);workspace.runtime=runtime
            state.update(workspace=str(workspace.root),target=job['workspace'],workflow=plan['workflow'],
                         recovery=journal.data['recovery'],capabilities=public_capabilities(inventory),required_verification=plan['required'],
                         resumed_from=job.get('resume_from'))
            policy=WORKER_POLICY+'\n'+runtime.prompt()
            worker_guard=WorkerGuard(workspace,plan)
            p=workspace.file('AGENTS.md')
            if p.exists():policy+='\nWorkspace instructions:\n'+p.read_text()[:4000]
            prior=journal.data.get('messages',[])
            messages=[{'role':'system','content':policy},{'role':'user','content':job['objective']}]
            if lookup and lookup.get('token'):
                messages.append({'role':'user','content':'Observed source/package discovery. A missing root is not source located.\n'+json.dumps(source_lookup.public(lookup))[:1200]})
            if prior:messages+=prior[2:][-6:]
            elif job.get('history'):messages[1:1]=job['history'][-4:]
            if journal.data.get('interrupted_operation'):
                messages.append({'role':'user','content':'The connection interrupted this operation before its outcome was verified: '+json.dumps(journal.data['interrupted_operation'])+'. Inspect existing outputs before retrying it.'})
            available=selected_tools(TOOLS,plan,workspace.readonly)
            end({'success':True,'workflow':plan['workflow'],'workspace':str(workspace.root),'recovery':journal.data['recovery']})
            def observed_failure(checks):
                return any(c.get('kind') in {'tests','build'} and c.get('exit_code') not in (None,0,124,126,127) and not c.get('timeout') and not c.get('missing_prerequisite') for c in checks)
            if plan['workflow']=='device' and not any(inventory['access'].get(n)=='available' for n in ('rish','adb')):
                state.update(status='blocked',error='Shizuku/Rish is disconnected and no authorized ADB connection is available.',result='Start Shizuku and authorize Termux, then resume.',verification='NOT_VERIFIED')
                return state
            if plan['required']==['project']:
                state.update(status='blocked',error=plan['reason'],result='Choose a project or a diagnostic target.',verification='NOT_VERIFIED')
                return state
            if not journal.data['checks'] and plan['workflow']=='source_fix':
                begin('diagnose','Checking the failure baseline')
                observed=False;detail='';baseline_error=None
                if plan['checks']:
                    baseline=runtime.verify(True)
                    observed=observed_failure(baseline.get('checks',[]))
                    detail=json.dumps({'missing':baseline['missing'],'checks':[{k:c.get(k) for k in ('kind','argv','exit_code','output','error','diagnostics')} for c in baseline.get('checks',[])[-4:]]})
                    baseline_error=None if observed else 'Planned checks did not fail. The original failure was not reproduced.'
                else:
                    baseline_error='No project checks in this workspace. Reproduction was not run.'
                    detail=baseline_error
                end({'success':bool(observed and not baseline_error),'output':detail,'error':baseline_error})
                if not observed:
                    if lookup and not lookup.get('root'):baseline_error=(baseline_error or '')+' '+((lookup.get('chosen') or {}).get('reason') or '')
                    state.update(status='failed',verification='NOT_VERIFIED',result=baseline_error+'\nWorkspace: '+str(workspace.root),error=baseline_error.strip())
                    return state
                messages.append({'role':'user','content':'Observed original failure:\n'+detail[:3000]})
                brief=source_lookup.failure_brief(workspace.root, detail)
                if brief:messages.append({'role':'user','content':redact(brief)[:6000]})
            finish_attempts=0
            for turn in range(plan['max_steps']):
                begin('generating','Generating coding step '+str(turn+1),'Waiting for the local model');state['turn']=turn+1
                available=selected_tools(TOOLS,plan,workspace.readonly)
                trim_messages();answer=complete(messages,available,model,generation_progress)
                end()
                check_cancel()
                messages.append({'role':'assistant','content':json.dumps(answer)})
                if not answer['tool_calls']:
                    begin('verify_goal','Verifying the requested outcome')
                    journal.begin('verify_goal',{'run_checks':True})
                    goal=runtime.verify(True);record('verify_goal',{'run_checks':True},goal);end({'success':goal['verified'],'output':json.dumps(compact(goal))})
                    state['verification_results']=goal
                    if goal['verified']:
                        state.update(status='completed',verification='GOAL_VERIFIED',result=redact(answer['content']))
                        if plan['mutating']:state['result']+='\nVerified workspace: '+str(workspace.root)
                        return state
                    finish_attempts+=1
                    missing_tools=[s for s in journal.data['steps'] if isinstance(s.get('result'),dict) and s['result'].get('missing_prerequisite')]
                    if finish_attempts>=2 or missing_tools:
                        state.update(status='needs_verification',verification='NOT_VERIFIED',result='Task needs verification: '+', '.join(goal['missing'])+'.\nSaved workspace: '+str(workspace.root),proposed_summary=redact(answer['content']),
                                     error='The requested outcome lacks verification: '+', '.join(goal['missing']))
                        return state
                    messages.append({'role':'user','content':'Completion withheld. Obtain the missing evidence: '+json.dumps(goal['missing'])+'. Inspect failing check results and revise the solution.'})
                    continue
                for call_index,call in enumerate(answer['tool_calls']):
                    name=call['name'];args=call['arguments']
                    title={'read_file':'Reading file','write_file':'Writing file','list_files':'Listing folder','run_argv':'Running command','bridge_status':'Checking Termux and Rish','device_argv':'Android app operation','code_search':'Searching code','edit_patch':'Applying patch','git_diff':'Inspecting Git changes','diagnose':'Checking build diagnostics','apk_tools':'Analyzing APK','import_apk':'Importing installed APK','tool_adapter':'Running '+str(args.get('tool','tool'))+' '+str(args.get('operation','')),'tool_capabilities':'Checking available tools','verify_goal':'Verifying outcome','unified_patch':'Applying unified patch'}[name]
                    detail=' '.join(args.get('argv',[])) if name in {'run_argv','device_argv','diagnose'} else args.get('path') or args.get('package') or args.get('pattern','')
                    begin(name,title,detail)
                    journal.begin(name,args)
                    revision_before=journal.data['revision']
                    try:
                        try:worker_guard.validate(name,args,call_index)
                        except ValueError as exc:raise PolicyViolation(str(exc)) from exc
                        if journal.repeated_failures(name,args)>=plan['max_identical_failures']:raise ValueError('Repeated identical failure: inspect the prior error and choose a different evidence-based step.')
                        result=workspace.invoke(name,args)
                    except (ValueError,OSError,KeyError,TypeError) as exc:result={'error':redact(exc),'policy_violation':isinstance(exc,PolicyViolation)}
                    worker_guard.observe(name,result)
                    end(result)
                    record(name,args,result)
                    blocker=worker_guard.blocker(result)
                    if blocker:
                        state.update(status='blocked',verification='NOT_VERIFIED',error=blocker,result=blocker)
                        return state
                    if journal.repeated_failures(name,args)>=plan['max_identical_failures']:
                        state.update(status='blocked',verification='NOT_VERIFIED',
                                     error='Repeated identical tool failures; stopped to preserve evidence.',
                                     result='Stopped after repeated failures. Inspect the saved diagnostics before resuming.')
                        return state
                    if (name in {'write_file','edit_patch','unified_patch'} or journal.data['revision']>revision_before) and isinstance(result,dict) and not result.get('error') and plan.get('checks') and not workspace.readonly:
                        begin('verify_goal','Checking the edit against the original failure')
                        journal.begin('verify_goal',{'run_checks':True})
                        goal=runtime.verify(True);record('verify_goal',{'run_checks':True},goal)
                        end({'success':goal['verified'],'output':json.dumps(compact(goal)),'error':None if goal['verified'] else 'Checks still failing: '+', '.join(goal['missing'])})
                        state['verification_results']=goal
                        if goal['verified']:
                            state.update(status='completed',verification='GOAL_VERIFIED',result='Verified after the edit.\nVerified workspace: '+str(workspace.root))
                            return state
                        repeated=worker_guard.repeated_check_failure(journal.data['checks'])
                        if repeated:
                            state.update(status='blocked',verification='NOT_VERIFIED',error='Two identical check failures.',result=redact(repeated))
                            return state
                        trace=[{k:c.get(k) for k in ('argv','exit_code','output','error','diagnostics')} for c in goal.get('checks',[])[-4:] if not c.get('success')]
                        messages.append({'role':'user','content':'The edit did not pass the same check. New trace: '+redact(json.dumps(trace))[:6000]+'. Read the new trace and patch the cited line.'})
                        break
                    if name=='tool_capabilities':break
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
        if journal:
            journal.export_patch(workspace)
            journal.data.update(status=state['status'],messages=messages,verification=state.get('verification_results',{}));journal.save()
            state['journal_file']=str(journal.path)
            state['artifacts']=journal.data['artifacts'];state['patches']=journal.data['patches']
        state['finished_at']=time.time();state['phase']=state['status'];state.pop('current_operation',None);publish()
        if source_lock is not None:source_lock.close()
        cancel_file.unlink(missing_ok=True);signal.signal(signal.SIGTERM,previous_handler)
if __name__=='__main__':
    try:print(json.dumps(run(json.loads(Path(sys.argv[1]).read_text())),indent=2))
    except Exception as exc:print(json.dumps({'status':'failed','error':str(exc)}));sys.exit(1)
