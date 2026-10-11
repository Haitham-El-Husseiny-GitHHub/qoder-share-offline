"""Find an app's source before the model is asked. Phone, GitHub, then Cloudflare."""
import json, os, re, shutil, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

IGNORE={'.git','node_modules','.venv','venv','__pycache__','build','dist','.gradle','.qoder-workspaces','.qoder-worktrees','.qoder-artifacts','.qoder-sources'}
MARKERS=('package.json','gradlew','CMakeLists.txt','pyproject.toml','setup.py','Cargo.toml','go.mod','pubspec.yaml','AndroidManifest.xml')

STOP={'the','this','an','my','installed','android','open','source','mobile','is','on','for','in','at','to','of','and','or','a','was','has','not','does','from','with','that','it','its','fix','crash','crashes'}

def app_token(text):
    lowered=text.lower()
    found=[]
    for pattern in (r'\bapp\s+([a-z0-9][a-z0-9._-]{1,48})\b', r'\b([a-z0-9][a-z0-9._-]{1,48})\s+app\b', r'\bpackage\s+((?:[a-z][a-z0-9_]*)(?:\.[a-z0-9_]+)+)\b'):
        for match in re.finditer(pattern, lowered):
            token=match.group(1).strip('._-')
            if token and token not in STOP:found.append(token)
    return found[0] if found else ''

def preferred_place(text):
    lowered=text.lower()
    if 'cloudflare' in lowered:return 'cloudflare'
    if 'github' in lowered:return 'github'
    if re.search(r'\b(phone|installed|device|termux)\b', lowered):return 'phone'
    return ''

def _project(path):
    from task_router import python_files
    return any((path/name).exists() for name in MARKERS) or bool(python_files(path))

def _score(path, token):
    name=path.name.lower().replace('_','-')
    wanted=token.lower().replace('_','-')
    if name==wanted:return 3
    if name.replace('-','')==wanted.replace('-',''):return 2
    if wanted in name:return 1
    return 0


def project_for_path(value):
    """Resolve a source file to its nearest project, preserving its actual location."""
    path=Path(value).expanduser().resolve(strict=True)
    folder=path.parent if path.is_file() else path
    for candidate in (folder,*folder.parents):
        if any((candidate/name).exists() for name in MARKERS) or (candidate/'.git').exists():
            return candidate
    return folder

def explicit_source(objective):
    # Quoted paths allow spaces. Bare paths stop at whitespace/punctuation.
    patterns=(r"""["']((?:/|~/)[^"'\n]+)["']""",r"(?:^|\s)((?:/|~/)[^\s,;]+)")
    for pattern in patterns:
        for match in re.finditer(pattern,objective):
            value=match.group(1).rstrip('.,)')
            try:
                path=Path(value).expanduser().resolve(strict=True)
                if path.is_dir() or path.is_file():return project_for_path(path)
            except (OSError,ValueError):continue
    return None

def search_roots(workspace, config):
    roots=[Path(workspace)]
    for item in (config or {}).get('source_roots') or []:
        if isinstance(item,str) and item:roots.append(Path(item).expanduser())
    home=Path.home()
    for name in ('projects','coding-workspace','src','git','work'):
        roots.append(home/name)
    roots.extend([home,home/'storage'/'shared',Path('/storage/emulated/0'),Path('/sdcard')])
    seen=set();chosen=[]
    for root in roots:
        try:
            if not root.is_dir():continue
            key=root.resolve()
        except OSError:continue
        if key in seen:continue
        seen.add(key);chosen.append(root)
    return chosen

def find_local(token, roots, limit=30000):
    hits=[];seen=set()
    wanted=token.lower().replace('_','-')
    for root in roots:
        for current, dirs, files in os.walk(root, followlinks=False):
            here=Path(current)
            try:key=here.resolve()
            except OSError:dirs.clear();continue
            if key in seen:dirs.clear();continue
            if len(seen)>=limit:return hits
            seen.add(key)
            dirs[:]=[d for d in dirs if d not in IGNORE and d not in {'.cache','.npm','.rustup','.local','Android'} and not d.startswith('.')]
            try:depth=len(here.relative_to(root).parts)
            except ValueError:depth=99
            if depth>12:dirs.clear();continue
            matches=bool(token and _score(here,token))
            # Package/application IDs can identify source even when its folder has another name.
            if token and not matches:
                for marker in ('package.json','AndroidManifest.xml','build.gradle','build.gradle.kts','pyproject.toml'):
                    if marker not in files:continue
                    try:
                        p=here/marker
                        if p.stat().st_size>256000:continue
                        body=p.read_text(errors='replace').lower()
                        if re.search(r'(?<![a-z0-9_.-])'+re.escape(wanted)+r'(?![a-z0-9_.-])',body):
                            matches=True;break
                    except OSError:pass
            if matches:
                try:valid=_project(here)
                except OSError:valid=False
                if valid and here not in hits:hits.append(here)
    return hits


def parse_packages(output, token):
    found=[]
    for line in (output or '').splitlines():
        line=line.strip()
        if line.startswith('package:'):line=line[8:]
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+', line):continue
        if token.lower() in line.lower():found.append(line)
    exact=[p for p in found if p.lower().endswith('.'+token.lower()) or p.lower().endswith(token.lower())]
    return exact or found

def github_repos(token, run):
    if not token or not shutil.which('gh'):return {'available':False,'repos':[]}
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,48}', token):return {'available':True,'repos':[],'error':'Refusing an unsafe repository query.'}
    def rows(result, own=False):
        if result.get('exit_code'):return [], (result.get('output') or 'GitHub query failed.')[:240]
        try:parsed=json.loads(result.get('output') or '[]')
        except ValueError:return [], 'GitHub returned invalid JSON.'
        if not isinstance(parsed,list):return [], 'GitHub returned an unexpected list.'
        found=[]
        for row in parsed:
            url=str(row.get('url') or '')
            full=str(row.get('fullName') or row.get('name') or '')
            if url.endswith('.git'):url=url[:-4]
            if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', url):continue
            found.append({'full_name':full if '/' in full else url.split('/',3)[-1],'url':url,'description':str(row.get('description') or '')[:180],'own':own})
        return found, ''
    own, own_error=rows(run(['gh','repo','list','--limit','30','--json','name,url,description'], timeout=8), True)
    found, search_error=rows(run(['gh','search','repos',token,'--limit','5','--json','fullName,url,description'], timeout=8), False)
    seen={item['url'] for item in own}
    repos=own+[item for item in found if item['url'] not in seen]
    return {'available':True,'repos':repos[:12],'error':'' if repos else (own_error or search_error)}

def _exact_repos(repos, token):
    wanted=token.lower().replace('_','-')
    return [r for r in repos if r['full_name'].split('/')[-1].lower().replace('_','-')==wanted]

def clone_repo(url, dest):
    if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', url):
        return {'ok':False,'error':'Only https://github.com/owner/repo clones are allowed.'}
    if dest.exists():return {'ok':_project(dest),'path':str(dest),'reused':True}
    dest.parent.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'never'}
    try:
        proc=subprocess.run(['git','clone','--depth','1',url+'.git',str(dest)],capture_output=True,text=True,timeout=45,env=env)
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {'ok':False,'error':str(exc)[:300]}
    if proc.returncode!=0 or not dest.is_dir():
        return {'ok':False,'error':((proc.stderr or proc.stdout or 'git clone failed')[:300])}
    return {'ok':True,'path':str(dest)}

def cloudflare_projects(token, config, http_get):
    local=[]
    cf=(config or {}).get('cloudflare') or {}
    account=str(cf.get('account_id') or '')
    token_file=cf.get('api_token_file')
    if not account or not token_file:
        return {'configured':False,'projects':local}
    if not re.fullmatch(r'[a-f0-9]{32}', account):
        return {'configured':False,'projects':[],'error':'Cloudflare account_id must be 32 hex characters.'}
    path=Path(token_file).expanduser()
    if not path.is_file() or path.stat().st_mode & 0o077:
        return {'configured':False,'projects':[],'error':'Cloudflare token file must exist and be mode 600.'}
    secret=path.read_text().strip()
    if not secret:return {'configured':False,'projects':[],'error':'Cloudflare token file is empty.'}
    projects=[]
    for kind,url in (
        ('pages','https://api.cloudflare.com/client/v4/accounts/%s/pages/projects?per_page=20'%account),
        ('worker','https://api.cloudflare.com/client/v4/accounts/%s/workers/scripts'%account),
    ):
        try:payload=http_get(url, secret)
        except (OSError,ValueError,TimeoutError) as exc:
            return {'configured':True,'projects':projects,'error':str(exc)[:200]}
        rows=payload.get('result') if isinstance(payload,dict) else None
        if not isinstance(rows,list):continue
        for row in rows:
            if not isinstance(row,dict):continue
            name=str(row.get('name') or row.get('id') or '')
            if token.lower() not in name.lower():continue
            source=((row.get('source') or {}).get('config') or {}) if isinstance(row.get('source'),dict) else {}
            owner,repo=source.get('owner'),source.get('repo_name')
            git='https://github.com/%s/%s'%(owner,repo) if isinstance(owner,str) and isinstance(repo,str) and re.fullmatch(r'[A-Za-z0-9_.-]+', owner) and re.fullmatch(r'[A-Za-z0-9_.-]+', repo) else ''
            projects.append({'name':name,'kind':kind,'git':git})
            if len(projects)>=5:break
    return {'configured':True,'projects':projects}

def _http_get(url, secret):
    import urllib.request
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+secret,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=8) as response:
        return json.loads(response.read(1_000_000).decode())

def _default_run(argv, timeout):
    try:proc=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc:return {'exit_code':1,'output':str(exc)[:300]}
    return {'exit_code':proc.returncode,'output':(proc.stdout or proc.stderr or '')[:4000]}

def public(report):
    data={k:report[k] for k in ('token','preference','chosen','places','package','ambiguous') if k in report}
    return data

def acquire(objective, workspace, device=None, config=None, run=None, clone=None, http_get=None):
    explicit=explicit_source(objective)
    if explicit is not None:
        return {'token':'','root':str(explicit),'chosen':{'where':'phone','path':str(explicit),'reason':'Explicit accessible source path.'},'places':[],'package':None}
    token=app_token(objective)
    preference=preferred_place(objective)
    report={'token':token,'preference':preference,'places':[],'chosen':None,'root':None,'package':None}
    if not token:return report
    config=config or {}
    run=run or _default_run
    clone=clone or clone_repo
    http_get=http_get or _http_get
    def phone():
        found=find_local(token, search_roots(workspace, config))
        found.sort(key=lambda p:(-_score(p, token), str(p)))
        return found
    def installed():
        if not device:return [], ''
        try:
            listed=device(['pm','list','packages',token])
            return parse_packages(listed.get('output') if isinstance(listed,dict) else str(listed), token), ''
        except (OSError,ValueError,TypeError) as exc:
            return [], str(exc)[:240]
    with ThreadPoolExecutor(max_workers=4) as pool:
        local_f=pool.submit(phone)
        device_f=pool.submit(installed)
        online=not config.get('offline',True)
        git_f=pool.submit(github_repos, token, run) if online else pool.submit(lambda:{'available':False,'repos':[],'error':'Remote discovery disabled for offline job.'})
        cloud_f=pool.submit(cloudflare_projects, token, config, http_get) if online else pool.submit(lambda:{'configured':False,'projects':[],'error':'Remote discovery disabled for offline job.'})
        local=local_f.result()
        packages,device_error=device_f.result()
        github=git_f.result()
        cloud=cloud_f.result()
    report['places'].append({'where':'phone','count':len(local),'paths':[str(p) for p in local[:4]]})
    report['places'].append({'where':'installed','packages':packages[:4],'error':device_error})
    if len(packages)==1:report['package']=packages[0]
    report['places'].append({'where':'github','available':github.get('available',False),'repos':[r['full_name'] for r in github.get('repos',[])],'error':github.get('error','')})
    report['places'].append({'where':'cloudflare','configured':cloud.get('configured',False),'projects':[p['name'] for p in cloud.get('projects',[])],'error':cloud.get('error','')})
    exact_local=[p for p in local if _score(p, token)>=2]
    report['ambiguous']=len(local)>1 and not any(_score(p,token)==3 for p in local)
    exact_git=_exact_repos(github.get('repos',[]), token)
    owned=[item for item in exact_git if item.get('own')]
    if len(owned)==1:exact_git=owned
    cloud_git=[p for p in cloud.get('projects',[]) if p.get('git')]
    dest=Path(workspace).resolve().parent/'.qoder-sources'/re.sub(r'[^a-z0-9._-]+','-',token.lower()).strip('.-')
    order={'phone':('phone','github','cloudflare'),'github':('github','phone','cloudflare'),'cloudflare':('cloudflare','phone','github')}.get(preference,('phone','github','cloudflare'))
    for place in order:
        if report['root']:break
        if place=='phone' and len(exact_local)==1:
            report['chosen']={'where':'phone','path':str(exact_local[0]),'reason':'A phone directory matches the app name.'}
            report['root']=report['chosen']['path']
        elif place=='phone' and len(local)==1:
            report['chosen']={'where':'phone','path':str(local[0]),'reason':'One phone project contains the app name.'}
            report['root']=report['chosen']['path']
        elif place=='github' and len(exact_git)==1:
            cloned=clone(exact_git[0]['url'], dest)
            report['places'].append({'where':'github-clone','ok':bool(cloned.get('ok')),'error':cloned.get('error','')})
            if cloned.get('ok'):
                report['chosen']={'where':'github','path':str(dest),'reason':'Cloned the one GitHub repository whose name matches.','url':exact_git[0]['url']}
                report['root']=str(dest)
        elif place=='cloudflare' and len(cloud_git)==1:
            cloned=clone(cloud_git[0]['git'], dest)
            report['places'].append({'where':'cloudflare-clone','ok':bool(cloned.get('ok')),'error':cloned.get('error','')})
            if cloned.get('ok'):
                report['chosen']={'where':'cloudflare','path':str(dest),'reason':'Cloned the GitHub repository connected to the Cloudflare project.','url':cloud_git[0]['git']}
                report['root']=str(dest)
    if not report['root'] and report['package']:
        report['chosen']={'where':'installed','package':report['package'],'reason':'The app is installed, but no source tree was found in accessible device locations.'}
    elif not report['root']:
        report['chosen']={'where':'none','reason':'ambiguous source' if report.get('ambiguous') else 'No source matched in accessible device locations.'}
    return report


def locate_project(root, objective=''):
    """Use the workspace root when it is a project. Otherwise one named or only nested project."""
    from task_router import project
    _IGNORE=IGNORE
    root = Path(root)
    if project(root)['source']:
        return root
    match = re.search(r'\bapp\s+([a-z0-9][a-z0-9._-]{1,40})\b', objective.lower())
    token = match.group(1).strip('._-') if match else ''
    found = []
    for current, dirs, _files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in _IGNORE and not d.startswith('.')]
        here = Path(current)
        if len(here.relative_to(root).parts) > 2:
            dirs.clear()
            continue
        if here != root and project(here)['source']:
            found.append(here)
            if len(found) > 8:
                break
    if token:
        named = [p for p in found if token in p.name.lower()]
        if len(named) == 1:
            return named[0]
    if len(found) == 1:
        return found[0]
    return None


def failure_brief(root, output, limit=2):
    """Load the source files a failure already named, so the model does not spend a turn searching."""
    root = Path(root)
    seen = []
    for match in re.finditer(r'(?:/|\./|\b)[\w./\\-]{1,180}\.(?:py|js|jsx|ts|tsx|kt|java|kts|gradle|xml|smali|c|cc|cpp|h|go|rs)\b', output or ''):
        raw = match.group(0).strip('.,:()')
        candidate = Path(raw)
        try:
            if candidate.is_absolute():
                rel = candidate.resolve().relative_to(root.resolve())
            else:
                rel = Path(raw)
                if not (root / rel).resolve().is_relative_to(root.resolve()):
                    continue
            path = (root / rel).resolve()
            key = str(rel)
            if path.is_file() and key not in seen:
                seen.append(key)
        except (OSError, ValueError):
            continue
    source = [p for p in seen if not any(part in {'tests', 'test', '__tests__'} for part in Path(p).parts) and not Path(p).name.startswith('test_')]
    chunks = []
    for rel in (source or seen)[:limit]:
        try:
            chunks.append(rel + '\n' + (root / rel).read_text()[:2500])
        except (OSError, UnicodeError):
            continue
    if not chunks:
        return ''
    return 'Files cited by the failure, already read. Apply one edit_patch to the cause. Do not search first.\n\n' + '\n\n'.join(chunks)
