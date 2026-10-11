"""Opt-in SSH worker transport. Inference and edits remain on the phone."""
import json
import re
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path

from tool_catalog import CATALOG

EXCLUDES = ['.git', '.ssh', '.env*', '*.key', '*.pem', '*.keystore', '*.jks', 'runtime', 'sessions', 'models', 'node_modules', '.qoder-original-apks']


def settings(config):
    remote = config.get('remote', {})
    host, worker = remote.get('host'), remote.get('worker')
    if not remote.get('enabled') or not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*', host):
        raise ValueError('Configure remote.host as a trusted SSH host alias or user@host.')
    if not isinstance(worker, list) or not worker or not all(isinstance(a, str) and '\0' not in a for a in worker):
        raise ValueError('Configure remote.worker as its Python/script argv on the remote machine.')
    if not shutil.which('ssh'):
        raise ValueError('openssh is required for the configured remote builder.')
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=yes', '-T', host]
    return remote, ssh, worker


def discover_remote(ws, config):
    try:
        _, ssh, worker = settings(config)
        result = ws.command(ssh + [shlex.join(worker + ['--capabilities'])], timeout=15, output_limit=200_000)
        if result['exit_code'] or result.get('output_may_be_truncated'):
            raise ValueError(result['output'] or 'Remote capability probe failed.')
        capabilities = json.loads(result['output'])
        return {'available': True, 'tools': capabilities['tools'], 'access': capabilities['access']}
    except (ValueError, OSError, KeyError) as error:
        return {'available': False, 'error': str(error)}


def invoke_remote(ws, name, operation, inputs, timeout, config):
    remote, ssh, worker = settings(config)
    if name not in remote.get('tools', []) or name in {'adb', 'rish', 'http', 'language_server', 'apksigner', 'zipalign', 'bundletool'}:
        raise ValueError('Adapter is not enabled for remote execution: ' + name)
    if not shutil.which('rsync'):
        raise ValueError('rsync is required to transfer the remote build workspace.')
    capabilities = discover_remote(ws, config)
    if not capabilities['available'] or not capabilities['tools'].get(name, {}).get('installed'):
        raise ValueError('Remote prerequisite is unavailable: ' + capabilities.get('error', name))
    transfer_id = uuid.uuid4().hex
    prepare = ws.command(ssh + [shlex.join(worker + ['--prepare', transfer_id])], timeout=15, output_limit=16000)
    if prepare['exit_code']:
        raise ValueError('Remote workspace preparation failed: ' + prepare['output'])
    root = json.loads(prepare['output'])['workspace']
    if not isinstance(root, str) or not root.startswith('/') or not re.fullmatch(r'[A-Za-z0-9_./-]+', root):
        raise ValueError('Remote worker returned an unsafe workspace path.')
    transport = shlex.join(ssh[:-2])  # options, excluding target host
    upload = ws.command(['rsync', '-az', '--protect-args', '-e', transport,
                         *[flag for pattern in EXCLUDES for flag in ('--exclude', pattern)],
                         '--', str(ws.root) + '/', remote['host'] + ':' + root + '/'], timeout=min(timeout, 300))
    if upload['exit_code']:
        raise ValueError('Remote workspace transfer failed: ' + upload['output'])
    request = {'id': transfer_id, 'tool': name, 'operation': operation, 'inputs': inputs, 'timeout': timeout}
    try:
        executed = ws.command(ssh + [shlex.join(worker + ['--worker'])], timeout=min(1250, timeout + 30),
                              input_data=json.dumps(request).encode(), output_limit=1_000_000)
    except BaseException:
        # A new, bounded connection cancels the remote process group via its worker.
        try:
            subprocess.run(ssh + [shlex.join(worker + ['--cancel', transfer_id])], capture_output=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise
    if executed.get('timeout'):
        try:
            subprocess.run(ssh + [shlex.join(worker + ['--cancel', transfer_id])], capture_output=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            pass
    if executed['exit_code'] or executed.get('output_may_be_truncated'):
        raise ValueError('Remote worker did not return a complete result: ' + executed['output'][:500])
    result = json.loads(executed['output'])
    local_root = ws.root / '.qoder-artifacts' / ('remote-' + transfer_id)
    for item in result.get('artifacts', []):
        if not item.get('exists'):
            continue
        rel = Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts or any(p in {'.git', 'runtime', 'models'} for p in rel.parts):
            raise ValueError('Remote artifact path is unsafe.')
        destination = ws.file(str(local_root.relative_to(ws.root) / rel))
        destination.parent.mkdir(parents=True, exist_ok=True)
        downloaded = ws.command(['rsync', '-az', '--protect-args', '-e', transport, '--',
                                  remote['host'] + ':' + root + '/' + str(rel), str(destination)], timeout=min(timeout, 300))
        if downloaded['exit_code']:
            raise ValueError('Remote artifact transfer failed: ' + downloaded['output'])
        from job_journal import fingerprint
        if item.get('sha256') and fingerprint(destination) != item['sha256']:
            raise ValueError('Remote artifact checksum mismatch.')
        item['remote_path'] = item['path']
        item['path'] = str(destination.relative_to(ws.root))
    return {**result, 'location': 'remote', 'remote_job': transfer_id}
