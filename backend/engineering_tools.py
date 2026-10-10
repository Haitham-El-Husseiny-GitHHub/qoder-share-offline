"""Precise workspace edits, coding evidence and Android APK analysis."""
import difflib, hashlib, json, os, re, shutil, stat, tempfile, uuid, zipfile
from pathlib import Path

def rel(ws,p):return str(p.relative_to(ws.root))
def require_write(ws):
    if ws.readonly:raise ValueError('Editing and APK conversion require BUILD mode.')
def output_path(ws,args):
    p=ws.file(args['output'])
    if p==ws.root or p.exists():raise ValueError('Choose a new output path; existing files are preserved.')
    p.parent.mkdir(parents=True,exist_ok=True)
    return p
def diagnostics(result):
    issues=[]
    for line in result['output'].splitlines():
        line=re.sub(r'^\s*(?:W:|E:)\s*','',line)
        m=re.search(r'^(.+?):(\d+)(?::(\d+))?:\s*(?:(error|warning|note):\s*)?(.+)$',line)
        py=re.search(r'File "([^"]+)", line (\d+)',line)
        if m:issues.append({'file':m[1],'line':int(m[2]),'column':int(m[3]) if m[3] else None,'severity':m[4] or 'error','message':m[5][:500]})
        elif py:issues.append({'file':py[1],'line':int(py[2]),'severity':'error','message':line.strip()[:500]})
        elif re.search(r'(Error:|Exception:|FAILED|FAIL:|error:|BUILD FAILED|FAILURE:)',line):issues.append({'severity':'error','message':line.strip()[:500]})
        if len(issues)>=30:break
    return {**result,'success':result['exit_code']==0,'diagnostics':issues,
            'output_may_be_truncated':len(result['output'])>=5900}

def invoke(ws,name,args,redact):
    if name=='code_search':
        folder=ws.file(args.get('path','.'));pattern=args['pattern']
        if not isinstance(pattern,str) or not pattern or len(pattern)>1000:raise ValueError('Supply a non-empty search string, at most 1000 characters.')
        result=ws.command(['rg','--json','--fixed-strings','--max-count','20','--max-filesize','1M',
            '--glob','!.git/**','--glob','!runtime/**','--glob','!.ssh/**','--glob','!.env*',
            '--glob','!*.key','--glob','!*.pem','--glob','!*.keystore','--glob','!*.jks','--',pattern,rel(ws,folder)])
        matches=[]
        for line in result['output'].splitlines():
            try:
                event=json.loads(line)
                if event.get('type')!='match':continue
                d=event['data'];p=ws.file(d['path']['text'])
                matches.append({'path':rel(ws,p),'line':d['line_number'],'text':redact(d['lines']['text'])[:500]})
            except (ValueError,KeyError,TypeError):continue
        return {'matches':matches[:30],'exit_code':0 if result['exit_code']==1 else result['exit_code'],'truncated':len(result['output'])>=5900 or len(matches)>30,'error':result['output'] if result['exit_code'] not in (0,1) else None}
    if name=='edit_patch':
        require_write(ws);p=ws.file(args['path']);old=args['old_text'];new=args['new_text']
        if not isinstance(old,str) or not old or not isinstance(new,str):raise ValueError('Supply non-empty exact old_text and replacement new_text.')
        if p.stat().st_size>1_000_000:raise ValueError('File exceeds patch limit.')
        before=p.read_bytes()
        if len(before)>1_000_000:raise ValueError('File exceeds patch limit.')
        text=before.decode('utf-8');sha=hashlib.sha256(before).hexdigest()
        if args.get('expected_sha256') and args['expected_sha256']!=sha:raise ValueError('File changed since inspection; read it again.')
        if text.count(old)!=1:raise ValueError('old_text must match exactly once. Include more surrounding lines.')
        after=text.replace(old,new,1).encode('utf-8')
        if len(after)>1_000_000:raise ValueError('Patched file exceeds size limit.')
        if ws.cancel:ws.cancel()
        fd,temp=tempfile.mkstemp(prefix='.qoder-edit-',dir=p.parent)
        try:
            with os.fdopen(fd,'wb') as f:f.write(after);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),stat.S_IMODE(p.stat().st_mode))
            if p.read_bytes()!=before:raise ValueError('Concurrent file change; patch was not applied.')
            os.replace(temp,p)
        finally:
            if os.path.exists(temp):os.unlink(temp)
        diff=''.join(difflib.unified_diff(text.splitlines(True),after.decode().splitlines(True),fromfile=rel(ws,p),tofile=rel(ws,p)))
        return {'path':rel(ws,p),'before_sha256':sha,'after_sha256':hashlib.sha256(after).hexdigest(),'diff':redact(diff)[:6000],'changed':before!=after}
    if name=='git_diff':
        p=ws.file(args.get('path','.'));path=rel(ws,p)
        status=ws.command(['git','status','--porcelain=v1','--',path])
        if status['exit_code']!=0:return diagnostics(status)
        staged=bool(args.get('staged',False))
        diff=ws.command(['git','diff','--no-ext-diff','--no-textconv',*(['--cached'] if staged else []),'--',path])
        return {'status':status['output'],'staged':staged,'diff':diff['output'],'exit_code':diff['exit_code'],'untracked_note':'Untracked file names appear in status; their contents are not included in Git diff.'}
    if name=='diagnose':return diagnostics(ws.invoke('run_argv',{'argv':args['argv']}))
    if name=='apk_tools':
        action=args['action'];p=ws.file(args['path'])
        if action=='info':
            if not zipfile.is_zipfile(p):raise ValueError('Input is not a valid APK/ZIP archive.')
            with zipfile.ZipFile(p) as z:
                entries=z.namelist()
                data={'path':rel(ws,p),'bytes':p.stat().st_size,'dex':[n for n in entries if re.fullmatch(r'classes\d*\.dex',n)],'native_libraries':[n for n in entries if n.startswith('lib/') and n.endswith('.so')][:60],'manifest_present':'AndroidManifest.xml' in entries,'entries':len(entries)}
            if shutil.which('aapt2'):data['badging']=ws.command(['aapt2','dump','badging',rel(ws,p)])
            return data
        require_write(ws)
        if action not in {'decode','decompile','rebuild'}:raise ValueError('Use info, decode, decompile or rebuild.')
        if action=='rebuild' and not p.is_dir():raise ValueError('Rebuild requires an Apktool decoded folder.')
        if action in {'decode','decompile'}:
            if not zipfile.is_zipfile(p):raise ValueError('Input is not a valid APK/ZIP archive.')
            with zipfile.ZipFile(p) as z:
                if any(Path(n).is_absolute() or '..' in Path(n).parts for n in z.namelist()):raise ValueError('Archive contains unsafe entry paths.')
        out=output_path(ws,args)
        if action=='decode':argv=['apktool','d','--all-src','-j','2',rel(ws,p),'-o',rel(ws,out)]
        elif action=='decompile':argv=['jadx','-j','2','-d',rel(ws,out),rel(ws,p)]
        elif action=='rebuild':argv=['apktool','b',rel(ws,p),'-o',rel(ws,out)]
        else:raise ValueError('Use info, decode, decompile or rebuild.')
        if not shutil.which(argv[0]):raise ValueError(argv[0]+' is not installed in Termux.')
        env={**os.environ,'JAVA_TOOL_OPTIONS':'-Xmx768m'}
        result=diagnostics(ws.command(argv,env=env));result['output_path']=rel(ws,out)
        result['artifact_exists']=out.exists();result['installed']=False
        result['note']='Decompiled Java is for inspection; rebuild edits from the Apktool decoded resources/smali. Rebuilt APKs are unsigned and are not installed automatically.'
        return result
    if name=='import_apk':
        require_write(ws);package=args['package']
        if not isinstance(package,str) or not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+',package):raise ValueError('Supply an Android package identifier.')
        from device_tools import execute
        execute_args={'progress':ws.progress,'cancel':ws.cancel,'redact':redact}
        found=execute(['pm','path',package],**execute_args)
        if found['exit_code']!=0:raise ValueError(found['output'])
        paths=[line[8:] for line in found['output'].splitlines() if line.startswith('package:')]
        if not paths:raise ValueError('No installed APK paths found.')
        if any(not p.startswith('/') or not p.endswith('.apk') for p in paths):raise ValueError('Invalid APK path returned by Android.')
        out=output_path(ws,args);out.mkdir()
        staging='/sdcard/Download/Qoder-apk-stage-'+uuid.uuid4().hex
        files=[]
        try:
            result=execute(['mkdir','-p',staging],**execute_args)
            if result['exit_code']!=0:raise ValueError(result['output'])
            for i,source in enumerate(paths):
                if ws.cancel:ws.cancel()
                filename=str(i)+'-'+Path(source).name
                result=execute(['cp',source,staging+'/'+filename],**execute_args)
                if result['exit_code']!=0:raise ValueError(result['output'])
                with open(staging+'/'+filename,'rb') as src, (out/filename).open('wb') as dst:
                    while chunk:=src.read(1024*1024):
                        if ws.cancel:ws.cancel()
                        dst.write(chunk)
                files.append(rel(ws,out/filename))
            return {'package':package,'apks':files,'split_count':len(files),'source_app_modified':False}
        finally:
            try:execute(['rm','-rf',staging],redact=redact)
            except (OSError,ValueError):pass
    raise ValueError('Unknown engineering tool.')
