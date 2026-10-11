"""Durable job evidence, edit backups and isolated source recovery."""
import hashlib
import difflib
import json
import os
import re
import shutil
import time
from pathlib import Path


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def fingerprint(path):
    path = Path(path)
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def test_inputs(root):
    root=Path(root);result={};total=0
    ignored={'.git','node_modules','.venv','venv','__pycache__','build','dist','.gradle','.qoder-artifacts'}
    for folder,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if d not in ignored and not d.startswith('.qoder-')]
        for name in files:
            path=Path(folder)/name;relative=path.relative_to(root)
            is_test=any(p in {'tests','test','__tests__'} for p in relative.parts) or name.startswith('test_') or name.endswith(('_test.py','_test.go','.test.js','.test.ts','.spec.js','.spec.ts')) or name in {'tests.py','pytest.ini','jest.config.js','vitest.config.ts'}
            if is_test and not path.is_symlink() and path.stat().st_size<=1_000_000:
                total+=path.stat().st_size
                if len(result)>2000 or total>64_000_000:raise ValueError('Test-input inventory exceeds verification limit; use a narrower project.')
                result[str(relative)]=fingerprint(path)
    package=root/'package.json'
    if package.is_file():
        scripts=json.loads(package.read_text()).get('scripts',{})
        result['@package_test_script']=hashlib.sha256(str(scripts.get('test','')).encode()).hexdigest()
    return result


class Journal:
    def __init__(self, folder, job, resume=None):
        self.folder = Path(folder)
        if not re.fullmatch(r'[0-9a-f]{32}', job['id']):
            raise ValueError('Invalid job identifier.')
        self.path = self.folder / (job['id'] + '.journal.json')
        self.data = {'schema': 1, 'id': job['id'], 'target': job['workspace'], 'workspace': job['workspace'],
                     'objective': job['objective'], 'profile': job['profile'], 'route': job.get('route'),
                     'steps': [], 'patches': [], 'artifacts': [], 'checks': [], 'revision': 0,
                     'file_hashes': {}, 'recovery': {}, 'status': 'running', 'messages': [], 'started_at': time.time()}
        if resume:
            if not re.fullmatch(r'[0-9a-f]{32}', resume):
                raise ValueError('Invalid recovery identifier.')
            previous = json.loads((self.folder / (resume + '.journal.json')).read_text())
            if previous['target'] != job['workspace'] or previous['objective'] != job['objective'] or previous['profile'] != job['profile']:
                raise ValueError('Recovery target, task and profile must match the interrupted job.')
            if previous['status'] not in {'interrupted', 'stopped', 'failed', 'running', 'needs_verification', 'blocked'}:
                raise ValueError('This job does not need recovery.')
            self.data.update({k: previous[k] for k in ('workspace', 'steps', 'patches', 'artifacts', 'checks', 'revision', 'file_hashes', 'recovery', 'messages', 'plan') if k in previous})
            self.data['resumed_from'] = resume
            self.check_files()
            running = previous.get('pending_step')
            if running:
                self.data['interrupted_operation'] = running
        self.save()

    def save(self):
        self.data['updated_at'] = time.time()
        atomic_json(self.path, self.data)

    def check_files(self):
        root = Path(self.data['workspace'])
        if not root.is_dir():
            raise ValueError('Recovery workspace no longer exists.')
        for relative, expected in self.data['file_hashes'].items():
            target = (root / relative).resolve()
            if not target.is_relative_to(root.resolve()) or fingerprint(target) != expected:
                raise ValueError('Recovery file changed externally: ' + relative + '. Start a fresh task to inspect it.')
        for artifact in self.data['artifacts']:
            if artifact.get('sha256'):
                target=(root/artifact['path']).resolve()
                if not target.is_relative_to(root.resolve()) or fingerprint(target)!=artifact['sha256']:raise ValueError('Recorded artifact changed externally: '+artifact['path'])

    def backup(self, ws, relative):
        target = ws.file(relative)
        relative = str(target.relative_to(ws.root))
        backups = self.folder / (self.data['id'] + '.recovery')
        destination = backups / relative
        if any(p['path'] == relative for p in self.data['patches']):
            return
        if target.exists() and not target.is_file():
            raise ValueError('Editing requires a regular file.')
        entry = {'path': relative, 'existed': target.exists(), 'before_sha256': fingerprint(target)}
        if target.exists():
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copy2(target, destination)
            entry['backup'] = str(destination)
        self.data['patches'].append(entry)
        self.save()

    def edited(self, ws, relative, result=None):
        target = ws.file(relative)
        relative = str(target.relative_to(ws.root))
        current=fingerprint(target)
        prior=self.data['file_hashes'].get(relative,next((p['before_sha256'] for p in self.data['patches'] if p['path']==relative),None))
        if current!=prior:self.data['revision'] += 1
        self.data['file_hashes'][relative] = current
        for entry in self.data['patches']:
            if entry['path'] == relative:
                entry['after_sha256'] = fingerprint(target)
                if isinstance(result, dict) and result.get('diff'):
                    entry['diff'] = result['diff']
        self.save()

    def begin(self, tool, args):
        self.data['pending_step'] = {'tool': tool, 'inputs': args, 'started_at': time.time()}
        self.save()

    def finish(self, result, messages=None):
        step = self.data.pop('pending_step')
        step.update(result=result, revision=self.data['revision'], finished_at=time.time())
        step['verified'] = isinstance(result, dict) and not result.get('error') and result.get('success', result.get('exit_code', 0) == 0)
        if not isinstance(result, dict):
            step['verified'] = True
        self.data['steps'].append(step)
        self.data['last_verified_step'] = max((i for i, s in enumerate(self.data['steps']) if s['verified']), default=-1)
        if messages is not None:
            self.data['messages'] = messages
        if isinstance(result, dict):
            for artifact in result.get('artifacts', []):
                path = artifact.get('path')
                if path:
                    self.data['artifacts']=[a for a in self.data['artifacts'] if a.get('path')!=path]+[artifact]
        self.save()

    def repeated_failures(self, tool, args):
        return sum(1 for s in self.data['steps'] if not s['verified'] and s['tool'] == tool and s['inputs'] == args and s['revision']==self.data['revision'])

    def check(self, kind, result, argv=None, name=None):
        entry = {'kind': kind, 'name': name or kind, 'argv': argv, 'revision': self.data['revision'],
                 'exit_code': result.get('exit_code'), 'success': bool(result.get('success', result.get('exit_code') == 0)) and not result.get('error'),
                 'at': time.time(), 'diagnostics': result.get('diagnostics', []),
                 'error': result.get('error'), 'output': result.get('output', '')[-6000:],
                 'timeout': result.get('timeout', False), 'missing_prerequisite': result.get('missing_prerequisite', False)}
        if kind=='tests':entry['test_inputs']=test_inputs(self.data['workspace'])
        self.data['checks'].append(entry)
        self.save()
        return entry

    def export_patch(self, ws):
        chunks=[]
        for entry in self.data['patches']:
            target=ws.file(entry['path'])
            before=Path(entry['backup']).read_bytes() if entry.get('backup') else b''
            after=target.read_bytes() if target.is_file() else b''
            if before==after:continue
            try:
                lines=difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),
                    fromfile='a/'+entry['path'] if entry['existed'] else '/dev/null',
                    tofile='b/'+entry['path'] if target.exists() else '/dev/null')
                for line in lines:
                    chunks.append(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n')
            except UnicodeDecodeError:continue
        if not chunks:return None
        path=ws.file('.qoder-artifacts/'+self.data['id']+'-changes.patch')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(''.join(chunks))
        item={'path':str(path.relative_to(ws.root)),'kind':'unified_patch','exists':True,'sha256':fingerprint(path),'bytes':path.stat().st_size}
        self.data['artifacts']=[a for a in self.data['artifacts'] if a.get('path')!=item['path']]+[item]
        self.save()
        return item


def recovery_workspace(ws, journal, config):
    if journal.data.get('recovery'):
        ws.root = Path(journal.data['workspace']).resolve(strict=True)
        return journal.data['recovery']
    recovery = {'mode': 'file_backups', 'target': str(ws.root)}
    if config.get('edit_in_place'):
        recovery.update(mode='in_place_backups',workspace=str(ws.root))
        journal.data.update(workspace=str(ws.root),recovery=recovery)
        journal.save()
        return recovery

    if config.get('worktrees', True) and shutil.which('git'):
        top = ws.command(['git', 'rev-parse', '--show-toplevel'], timeout=10)
        head = ws.command(['git', 'rev-parse', '--verify', 'HEAD'], timeout=10)
        if top['exit_code'] == head['exit_code'] == 0:
            repository = Path(top['output'].strip()).resolve(strict=True)
            relative = ws.root.relative_to(repository)
            snapshot = ws.command(['git', '-c', 'user.name=Qoder Recovery', '-c', 'user.email=qoder@local', 'stash', 'create', 'Qoder recovery ' + journal.data['id']], timeout=30)
            if snapshot['exit_code'] != 0:
                raise ValueError('Git recovery snapshot failed: ' + snapshot['output'])
            revision = snapshot['output'].strip() or head['output'].strip()
            destination = ws.root.parent / '.qoder-worktrees' / journal.data['id']
            destination.parent.mkdir(parents=True, exist_ok=True)
            add = ws.command(['git', 'worktree', 'add', '--detach', str(destination), revision], timeout=30)
            if add['exit_code'] != 0:
                raise ValueError('Cannot create recovery worktree: ' + add['output'])
            # Include untracked project files without altering the original index or worktree.
            untracked = ws.command(['git', 'ls-files', '--others', '--exclude-standard', '-z', '--', '.'], timeout=10, output_limit=1_000_000)
            if untracked.get('output_may_be_truncated') or untracked['exit_code'] != 0:
                raise ValueError('Untracked inventory exceeded the recovery limit; select a narrower project.')
            for name in untracked['output'].split('\0'):
                if not name:
                    continue
                try:
                    original = ws.file(name)
                except ValueError:
                    continue
                if original.is_file():
                    copy = destination / relative / name
                    copy.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, copy)
            ws.root = (destination / relative).resolve(strict=True)
            for source,copy_root in ((repository,destination),(Path(recovery['target']),ws.root)):
                for dependency in ('node_modules','.venv','venv'):
                    if (source/dependency).is_dir() and not (copy_root/dependency).exists():(copy_root/dependency).symlink_to(source/dependency,target_is_directory=True)
            recovery.update(mode='git_worktree', workspace=str(ws.root), snapshot=revision)
    if recovery['mode']=='file_backups':
        original=ws.root
        destination=original.parent/'.qoder-workspaces'/journal.data['id']
        ignored={'node_modules','.venv','venv','__pycache__','.git','build','dist','.gradle','.qoder-workspaces','.qoder-worktrees','.qoder-artifacts'}
        count=total=0
        for folder,dirs,files in os.walk(original,followlinks=False):
            dirs[:]=[d for d in dirs if d not in ignored]
            for name in files:
                p=Path(folder)/name
                if p.is_symlink():continue
                count+=1;total+=p.stat().st_size
                if count>20000 or total>1_000_000_000:raise ValueError('Source snapshot exceeds 1 GB/20,000 files; use a Git project or narrower workspace.')
        shutil.copytree(original,destination,symlinks=True,ignore=lambda folder,names:[n for n in names if n in ignored])
        for dependency in ('node_modules','.venv','venv'):
            if (original/dependency).is_dir():(destination/dependency).symlink_to(original/dependency,target_is_directory=True)
        ws.root=destination.resolve(strict=True)
        recovery.update(mode='workspace_snapshot',workspace=str(ws.root))
    journal.data.update(workspace=str(ws.root), recovery=recovery)
    journal.save()
    return recovery
