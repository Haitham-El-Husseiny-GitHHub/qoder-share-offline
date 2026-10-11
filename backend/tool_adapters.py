"""One structured contract for local engineering tools.

Commands use argv, workspace-confined inputs, new output paths, bounded execution
and the worker's existing cancellation/progress callbacks. Missing prerequisites
are results, never claims that a tool ran.
"""
import hashlib
import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

import engineering_tools
import language_tools
from job_journal import fingerprint
from task_router import test_result
from tool_catalog import BASE, CATALOG, ANDROID_EXCLUDED, android_scope, command_for, load_config


def artifact(ws, path, kind='file'):
    path = ws.file(str(path))
    return {'path': str(path.relative_to(ws.root)), 'kind': kind, 'exists': path.exists(),
            'sha256': fingerprint(path), 'bytes': path.stat().st_size if path.is_file() else None}


def build_artifacts(ws, family):
    """Return existing deliverables; successful exit alone does not invent outputs."""
    items=[]
    if family=='gradle':
        for folder,dirs,files in os.walk(ws.root,followlinks=False):
            dirs[:]=[d for d in dirs if d not in {'.git','node_modules','.gradle','.venv','venv'} and not d.startswith('.qoder-')]
            if ws.cancel:ws.cancel()
            for name in sorted(files):
                path=Path(folder)/name
                if 'build' in path.relative_to(ws.root).parts and path.suffix in {'.apk','.aab','.jar'} and not path.is_symlink():
                    items.append(artifact(ws,relative(ws,path),path.suffix[1:]))
                    if len(items)>=32:return items
    else:
        for name in ('dist','build','out','.next'):
            path=ws.root/name
            if path.is_dir():
                items.append(artifact(ws,name,'web_build'))
                # Keep hashes for the important output files, alongside the directory.
                count=0
                for folder,dirs,files in os.walk(path,followlinks=False):
                    dirs[:]=[d for d in dirs if d not in {'node_modules','cache'}]
                    if ws.cancel:ws.cancel()
                    for filename in sorted(files):
                        output=Path(folder)/filename
                        if output.suffix in {'.html','.js','.css','.json'} and not output.is_symlink():
                            items.append(artifact(ws,relative(ws,output),'web_file'));count+=1
                            if count>=64:break
                    if count>=64:break
    return items


def new_output(ws, inputs, suffix=''):
    value = inputs.get('output')
    if value is None:
        value = '.qoder-artifacts/' + uuid.uuid4().hex + suffix
    return engineering_tools.output_path(ws, {'output': value})


def strip_apk_signatures(path,cancel=None):
    """Copy ZIP entries to remove stale v1 files and any v2/v3 signing block."""
    temporary=Path(str(path)+'.unsigned.tmp')
    try:
        with zipfile.ZipFile(path) as source,zipfile.ZipFile(temporary,'w') as target:
            target.comment=source.comment
            for info in source.infolist():
                if re.fullmatch(r'META-INF/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA|EC))',info.filename,re.I):continue
                if cancel:cancel()
                with source.open(info) as incoming,target.open(info,'w') as outgoing:
                    for chunk in iter(lambda:incoming.read(1024*1024),b''):
                        if cancel:cancel()
                        outgoing.write(chunk)
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def relative(ws, path):
    return str(Path(path).relative_to(ws.root))


def parsed_json(path, max_size=16_000_000):
    if path.stat().st_size > max_size:
        raise ValueError('Report exceeds structured result limit; inspect the saved artifact.')
    return json.loads(path.read_text())


def run(ws, argv, timeout, env=None):
    return engineering_tools.diagnostics(ws.command(argv, env=env, timeout=timeout))


def certificate(ws, path, config, timeout):
    command = command_for('apksigner', config)
    if not command:
        raise ValueError('apksigner is required for signature and signing-compatibility checks.')
    result = run(ws, command + ['verify', '--verbose', '--print-certs', relative(ws, path)], timeout)
    certs = sorted(set(re.findall(r'certificate SHA-256 digest:\s*([0-9a-fA-F]{64})', result['output'])))
    result['certificates_sha256'] = [s.lower() for s in certs]
    result['success'] = result['success'] and bool(certs)
    return result


def signing(config,ws=None):
    settings = config.get('signing', {})
    key = Path(settings.get('keystore', ''))
    password = Path(settings.get('password_file', ''))
    if not key.is_file() or not password.is_file() or not settings.get('alias'):
        raise ValueError('Configure signing.keystore, alias and password_file outside the model workspace in tools.json.')
    if os.name == 'posix' and password.stat().st_mode & 0o077:
        raise ValueError('Signing password file must be private (chmod 600).')
    if ws and any(p.resolve().is_relative_to(ws.root) for p in (key,password)):raise ValueError('Signing credentials must be outside the model workspace.')
    return settings, key.resolve(), password.resolve()


def manager(ws, inputs):
    from task_router import project
    detected = project(ws.root)
    if detected['kind'] != 'node':
        raise ValueError('Node operations require package.json in the selected project root.')
    chosen = detected['manager']
    if not shutil.which(chosen):
        raise ValueError('Project package manager is missing: ' + chosen)
    return chosen


def http_request(ws, inputs, timeout, offline=True):
    url = inputs['url']
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username:
        raise ValueError('Supply an HTTP(S) URL without embedded credentials.')
    method = inputs.get('method', 'GET').upper()
    if method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}:
        raise ValueError('Unsupported HTTP method.')
    body = inputs.get('body')
    if body is not None and (not isinstance(body, str) or len(body.encode()) > 1_000_000):
        raise ValueError('Request body must be text up to 1 MB.')
    headers = inputs.get('headers', {})
    if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) and '\n' not in k + v and '\r' not in k + v for k, v in headers.items()):
        raise ValueError('Headers must be a string map without newlines.')
    if ws.cancel:
        ws.cancel()
    req = urllib.request.Request(url, data=body.encode() if body is not None else None, method=method, headers=headers)
    from offline_policy import local_url, LocalRedirects
    if offline and not local_url(url):raise ValueError('Offline HTTP requires a loopback URL.')
    handlers=[urllib.request.ProxyHandler({})]
    if offline:handlers.append(LocalRedirects())
    opener = urllib.request.build_opener(*handlers)
    try:
        response = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read(1_000_001)
        status = response.code
        data = raw[:1_000_000].decode(errors='replace')
    if ws.cancel:
        ws.cancel()
    expected = inputs.get('expected_status')
    expected_text = inputs.get('expected_text')
    checked = expected is not None or bool(expected_text)
    passed = (expected is None or status == expected) and (not expected_text or expected_text in data)
    return {'exit_code': 0 if passed else 1, 'success': passed, 'status_code': status,
            'output': data[:6000], 'truncated': len(raw) > 6000, 'expectation_checked': checked,
            'request_fingerprint': hashlib.sha256(json.dumps([url, method, body], sort_keys=True).encode()).hexdigest(), 'artifacts': []}


def mobsf_call(settings, endpoint, body, content_type, timeout, cancel=None):
    url = urllib.parse.urlsplit(settings['url'])
    if url.scheme not in {'http', 'https'} or not url.hostname or url.username:
        raise ValueError('MobSF URL must be HTTP(S) without embedded credentials.')
    key_file = Path(settings['key_file'])
    if not key_file.is_file() or key_file.stat().st_mode & 0o077:
        raise ValueError('MobSF API key file must exist and be private (chmod 600).')
    key = key_file.read_text().strip()
    cls = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
    connection = cls(url.hostname, url.port, timeout=timeout)
    try:
        connection.request('POST', url.path.rstrip('/') + endpoint, body=body,
                           headers={'Authorization': key, 'Content-Type': content_type})
        response = connection.getresponse()
        data = response.read(16_000_001)
        if len(data) > 16_000_000 or response.status != 200:
            raise ValueError('MobSF returned HTTP ' + str(response.status) + ' or an oversized report.')
        if cancel:
            cancel()
        return json.loads(data)
    finally:
        connection.close()


def invoke(ws, name, operation, inputs, timeout=120, config=None, allow_remote=True):
    config = config or load_config()
    allow_remote = allow_remote and not android_scope(config) and not config.get('offline', True)
    if name not in CATALOG or operation not in CATALOG[name]['operations']:
        raise ValueError('Unknown adapter or unsupported operation.')
    if not isinstance(inputs, dict):
        raise ValueError('Adapter inputs must be an object.')
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
        raise ValueError('timeout must be a positive integer.')
    timeout = min(timeout, CATALOG[name]['max_timeout_seconds'])
    if android_scope(config) and name in ANDROID_EXCLUDED:
        return {'tool': name, 'operation': operation, 'location': 'local', 'exit_code': 126, 'success': False,
                'error': name + ' is outside the Android tool list.', 'unsupported_platform': True,
                'diagnostics': [], 'artifacts': []}
    if allow_remote and config.get('remote', {}).get('enabled') and name in config['remote'].get('tools',[]) and (name in config['remote'].get('prefer', []) or CATALOG[name]['heavy'] and config['remote'].get('prefer_heavy',True) or not command_for(name, config) and name not in {'http', 'mobsf', 'language_server'}):
        from remote_tools import invoke_remote
        return invoke_remote(ws, name, operation, inputs, timeout, config)
    if ws.readonly and operation in {'rewrite', 'build', 'install', 'instrument', 'align', 'sign', 'assemble', 'compile'}:
        raise ValueError('This operation requires a writable task profile.')
    if config.get('offline',True):
        from offline_policy import local_url
        target=inputs.get('url') or (config.get('mobsf',{}).get('url') if name=='mobsf' else None)
        if target and name in {'http','mobsf','zap'} and not local_url(target):
            raise ValueError('Offline job requires a loopback service or saved local data; remote API access needs an explicitly online job.')
    command = command_for(name, config)
    if name not in {'http', 'mobsf', 'language_server', 'node', 'gradle', 'ui'} and not command:
        return {'tool': name, 'operation': operation, 'location': 'local', 'exit_code': 127, 'success': False,
                'error': name + ' is unavailable. ' + '; '.join(CATALOG[name]['prerequisites']),
                'missing_prerequisite': True, 'diagnostics': [], 'artifacts': []}
    result = _local(ws, name, operation, inputs, timeout, config, command)
    return {**result, 'tool': name, 'operation': operation, 'location': 'local', 'timeout_seconds': timeout,
            'diagnostics': result.get('diagnostics', []), 'artifacts': result.get('artifacts', [])}


def _local(ws, name, operation, inputs, timeout, config, command):
    if name in {'http','mobsf'} and not config.get('_api_worker'):
        if ws.readonly and name=='http' and inputs.get('method','GET').upper() not in {'GET','HEAD','OPTIONS'}:raise ValueError('Read-only API inspection permits GET, HEAD and OPTIONS.')
        payload={'workspace':str(ws.root),'tool':name,'operation':operation,'inputs':inputs,'timeout':timeout,
                 'config':{'schema':1,'mobsf':config.get('mobsf',{}),'offline':config.get('offline',True),'_api_worker':True}}
        executed=ws.command([sys.executable,str(BASE/'api_worker.py')],input_data=json.dumps(payload).encode(),timeout=timeout,output_limit=1_000_000)
        if executed.get('timeout'):return {**executed,'success':False,'error':'API operation timed out; its process was cancelled.'}
        try:return json.loads(executed['output'].splitlines()[-1])
        except (ValueError,IndexError):return {**executed,'success':False,'error':'API helper did not return a complete structured result.'}
    if name == 'language_server':
        return language_tools.invoke(ws, operation, inputs, config, timeout)
    if name == 'http':
        return http_request(ws, inputs, timeout, config.get('offline',True))
    if name == 'ast_grep':
        pattern, language = inputs['pattern'], inputs['language']
        if not isinstance(pattern, str) or not pattern or len(pattern) > 4000 or not re.fullmatch(r'[A-Za-z0-9_-]+', language):
            raise ValueError('Supply a structural pattern and language identifier.')
        target = ws.file(inputs.get('path', '.'))
        if operation == 'rewrite':
            # Rewrites are generated first, then go through the existing checksum editor.
            if not target.is_file() or target.stat().st_size > 1_000_000:
                raise ValueError('Checked rewrites target one source file at a time.')
            result = run(ws, command + ['run', '--pattern', pattern, '--lang', language, '--rewrite', inputs['replacement'], '--json=compact', relative(ws, target)], timeout)
            if result['exit_code'] not in (0, 1):
                return result
            try:
                matches = json.loads(result['output'])
            except ValueError:
                raise ValueError('ast-grep returned incomplete JSON; narrow the pattern.')
            if not isinstance(matches, list) or not matches:
                raise ValueError('No structural rewrite matches.')
            before = target.read_bytes()
            after = before
            spans = sorted([(m['range']['byteOffset']['start'], m['range']['byteOffset']['end'], m['replacement']) for m in matches], reverse=True)
            previous = len(before) + 1
            for start, end, replacement in spans:
                if not 0 <= start <= end <= previous:
                    raise ValueError('Overlapping structural replacements require narrower patterns.')
                after = after[:start] + replacement.encode() + after[end:]
                previous = start
            result = ws.invoke('edit_patch', {'path': relative(ws, target), 'old_text': before.decode(),
                               'new_text': after.decode(), 'expected_sha256': hashlib.sha256(before).hexdigest()})
            return {**result, 'exit_code': 0, 'success': True, 'matches': len(matches)}
        result = run(ws, command + ['run', '--pattern', pattern, '--lang', language, '--json=compact', relative(ws, target)], timeout)
        if result['exit_code'] in (0, 1):
            result.update(exit_code=0, success=True)
            try:
                result['matches'] = json.loads(result['output'])[:30]
            except ValueError:
                result['structured_output_truncated'] = True
        if ws.runtime and ws.runtime.plan['workflow']=='security' and result.get('success'):
            if result.get('structured_output_truncated'):raise ValueError('Scan JSON is incomplete; narrow the target/pattern.')
            report=new_output(ws,{},'.json');report.parent.mkdir(parents=True,exist_ok=True)
            report.write_text(json.dumps({'scanner':'ast-grep','pattern':pattern,'language':language,'path':relative(ws,target),'matches':result['matches'],'scope':'structural pattern only; findings are not fixes'})+'\n')
            result['artifacts']=[artifact(ws,relative(ws,report),'structural_scan')]
        return result
    if name == 'gradle':
        if not (ws.root / 'gradlew').is_file():
            raise ValueError('Use the original project Gradle Wrapper; gradlew is missing.')
        if not shutil.which('javac'):
            raise ValueError('A JDK is required; a Java runtime alone is insufficient.')
        targets = inputs.get('tasks') or [{'build': 'assembleDebug', 'test': 'testDebugUnitTest', 'tasks': 'tasks'}[operation]]
        if not isinstance(targets, list) or not targets or not all(isinstance(t, str) and re.fullmatch(r'[:A-Za-z0-9_-]+', t) for t in targets):
            raise ValueError('Gradle tasks must be task-name strings.')
        extra = []
        if os.environ.get('PREFIX', '').startswith('/data/data/com.termux/') and shutil.which('aapt2'):
            extra = ['-Pandroid.aapt2FromMavenOverride=' + shutil.which('aapt2'), '-Dorg.gradle.native=false', '-Dorg.gradle.vfs.watch=false']
        env = None
        if config.get('android_sdk'):
            env = {'ANDROID_HOME': config['android_sdk'], 'ANDROID_SDK_ROOT': config['android_sdk']}
        result = run(ws, ['sh', './gradlew', '--offline', '--no-daemon', *extra, *targets], timeout, env=env)
        if operation=='build' and result['success']:result['artifacts']=build_artifacts(ws,'gradle')
        return test_result(result) if operation == 'test' else result
    if name == 'node':
        chosen = manager(ws, inputs)
        if operation == 'install':
            argv = {'npm': ['npm', 'ci', '--offline'], 'pnpm': ['pnpm', 'install', '--offline', '--frozen-lockfile'],
                    'yarn': ['yarn', 'install', '--offline', '--frozen-lockfile'], 'bun': ['bun', 'install', '--offline', '--frozen-lockfile']}[chosen]
        else:
            script = inputs.get('script') or {'build': 'build', 'test': 'test', 'typecheck': 'typecheck'}[operation]
            package = json.loads((ws.root / 'package.json').read_text())
            if script not in package.get('scripts', {}):
                raise ValueError('Requested script is not declared in package.json: ' + script)
            argv = [chosen, 'run', script]
        result = run(ws, argv, timeout)
        result['package_manager'] = chosen
        if operation=='build' and result['success']:result['artifacts']=build_artifacts(ws,'node')
        return test_result(result) if operation == 'test' else result
    if name=='cmake':
        build=ws.file(inputs.get('build_dir','qoder-build'))
        if operation=='configure':
            source=ws.file(inputs.get('path','.'))
            argv=command+['-S',relative(ws,source),'-B',relative(ws,build)]
        elif operation=='build':argv=command+['--build',relative(ws,build),'--parallel','2']
        else:argv=['ctest','--test-dir',relative(ws,build),'--output-on-failure']
        result=run(ws,argv,timeout)
        return test_result(result) if operation=='test' else result
    if name in {'jadx', 'apktool'}:
        action = {'decompile': 'decompile', 'decode': 'decode', 'rebuild': 'rebuild'}[operation]
        # Preserve build 79's existing implementation and its all-DEX decoding.
        result = engineering_tools.invoke(ws, 'apk_tools', {'action': action, **inputs, '_command':command, '_timeout':timeout}, str)
        if result.get('output_path'):
            if operation=='rebuild' and result.get('exit_code')==0 and result.get('artifact_exists'):
                strip_apk_signatures(ws.file(result['output_path']),ws.cancel);result['unsigned']=True
            result['artifacts'] = [artifact(ws, result['output_path'], 'apk' if operation == 'rebuild' else 'directory')]
        result['success'] = result.get('exit_code') == 0 and result.get('artifact_exists', False)
        return result
    if name in {'apkeditor', 'smali', 'baksmali'}:
        source = ws.file(inputs['path'])
        out = new_output(ws, inputs, '.apk' if operation in {'rebuild', 'merge'} else '.dex' if operation == 'assemble' else '')
        if name == 'apkeditor':
            flag = {'decode': 'd', 'rebuild': 'b', 'merge': 'm'}[operation]
            argv = command + [flag, '-i', relative(ws, source), '-o', relative(ws, out)]
            if operation=='rebuild':argv+=['-t','xml','-no-cache']
        else:
            argv = command + [('assemble' if name == 'smali' else 'disassemble'), relative(ws, source), '-o', relative(ws, out)]
        result = run(ws, argv, timeout)
        if name=='apkeditor' and operation in {'rebuild','merge'} and result['success'] and out.is_file():
            strip_apk_signatures(out,ws.cancel);result['unsigned']=True
        result.update(artifacts=[artifact(ws, relative(ws, out))], success=result['success'] and out.exists())
        return result
    if name == 'zipalign':
        source = ws.file(inputs['path'])
        if operation == 'verify':
            return run(ws, command + ['-c', '-P', '16', '4', relative(ws, source)], timeout)
        out = new_output(ws, inputs, '.apk')
        result = run(ws, command + ['-P', '16', '4', relative(ws, source), relative(ws, out)], timeout)
        if result['success']:
            verified = run(ws, command + ['-c', '-P', '16', '4', relative(ws, out)], timeout)
            result.update(success=verified['success'], alignment_verification=verified, artifacts=[artifact(ws, relative(ws, out), 'apk')])
        return result
    if name == 'apksigner':
        source = ws.file(inputs['path'])
        if operation == 'verify':
            return certificate(ws, source, config, timeout)
        align = command_for('zipalign', config)
        if not align:
            raise ValueError('zipalign is required before APK signing.')
        aligned = run(ws, align + ['-c', '-P', '16', '4', relative(ws, source)], timeout)
        if not aligned['success']:
            raise ValueError('APK alignment check failed. Align to a new output before signing.')
        settings, keystore, password = signing(config,ws)
        out = new_output(ws, inputs, '.apk')
        argv = command + ['sign', '--ks', str(keystore), '--ks-key-alias', settings['alias'], '--ks-pass', 'file:' + str(password), '--out', relative(ws, out), relative(ws, source)]
        result = run(ws, argv, timeout)
        if result['success']:
            verified = certificate(ws, out, config, timeout)
            result.update(success=verified['success'], signature_verification=verified, artifacts=[artifact(ws, relative(ws, out), 'signed_apk')])
        return result
    if name == 'bundletool':
        source = ws.file(inputs['path'])
        if operation == 'validate':
            return run(ws, command + ['validate', '--bundle=' + relative(ws, source)], timeout)
        if operation == 'build':
            settings, keystore, password = signing(config,ws)
            out = new_output(ws, inputs, '.apks')
            argv = command + ['build-apks', '--bundle=' + relative(ws, source), '--output=' + relative(ws, out), '--ks=' + str(keystore), '--ks-key-alias=' + settings['alias'], '--ks-pass=file:' + str(password)]
            if inputs.get('device_spec'):
                argv.append('--device-spec=' + relative(ws, ws.file(inputs['device_spec'])))
        elif operation == 'extract':
            out = new_output(ws, inputs)
            argv = command + ['extract-apks', '--apks=' + relative(ws, source), '--output-dir=' + relative(ws, out), '--device-spec=' + relative(ws, ws.file(inputs['device_spec']))]
        else:
            adb=command_for('adb',config)
            if not adb:raise ValueError('bundletool installation requires an authorized ADB connection.')
            connected=run(ws,adb+['devices'],min(timeout,10))
            devices=[line.split()[0] for line in connected['output'].splitlines() if '\tdevice' in line]
            serial=config.get('adb_serial')
            if serial and serial not in devices or not serial and len(devices)!=1:raise ValueError('Select one authorized ADB device for the APK set.')
            serial=serial or devices[0]
            staging=new_output(ws,{})
            staging.mkdir()
            spec=staging/'device.json'
            detected=run(ws,command+['get-device-spec','--device-id='+serial,'--output='+relative(ws,spec)],timeout)
            if not detected['success']:return detected
            selected=staging/'selected'
            extracted=run(ws,command+['extract-apks','--apks='+relative(ws,source),'--device-spec='+relative(ws,spec),'--output-dir='+relative(ws,selected)],timeout)
            if not extracted['success']:return extracted
            apks=sorted(p for p in selected.rglob('*.apk') if p.is_file())
            if not apks or len(apks)>128:raise ValueError('No compatible, bounded APK selection was extracted.')
            return device_operation(ws,'adb','install',{'path':relative(ws,apks[0]),'paths':[relative(ws,p) for p in apks],'package':inputs['package']},timeout,config,adb)
        result = run(ws, argv, timeout)
        result.update(artifacts=[artifact(ws, relative(ws, out))], success=result['success'] and out.exists())
        return result
    if name in {'adb', 'rish'}:
        return device_operation(ws, name, operation, inputs, timeout, config, command)
    if name == 'frida':
        native = config.get('frida', {}).get('mode') == 'inject' or 'frida-inject' in Path(command[0]).name
        if native:
            if operation == 'processes':
                result = run(ws, ['/system/bin/ps', '-A', '-o', 'PID,NAME'], timeout)
                result['process_scope'] = 'Processes visible to the current Android UID; device access may be required.'
                return result
            pid = inputs.get('pid')
            if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
                raise ValueError('Native Frida injection needs an observed positive pid and permission to attach. Use root where required.')
            script = ws.file(inputs['script'])
            result = run(ws, command + ['-p', str(pid), '-s', relative(ws, script)], timeout)
            result['observation_matched'] = bool(inputs.get('expected_text') and inputs['expected_text'] in result['output'])
            return result
        connection=['-H',config['frida']['host']] if config.get('frida',{}).get('host') else ['-U']
        if operation == 'processes':
            ps_command = config.get('commands', {}).get('frida_ps') or ['frida-ps']
            return run(ws, ps_command + connection + ['-ai'], timeout)
        script = ws.file(inputs['script'])
        target = inputs['package']
        if not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+', target):
            raise ValueError('Supply an Android package identifier.')
        argv = command + connection + ['-f', target, '-l', relative(ws, script), '-q', '-t', str(min(timeout, 120))]
        result = run(ws, argv, timeout)
        result['observation_matched'] = bool(inputs.get('expected_text') and inputs['expected_text'] in result['output'])
        return result
    if name == 'ghidra':
        source = ws.file(inputs['path'])
        out = new_output(ws, inputs)
        out.mkdir()
        report = out / 'functions.jsonl'
        result = run(ws, command + [relative(ws, out), 'qoder', '-import', relative(ws, source), '-analysisTimeoutPerFile', str(max(1, timeout - 30)),
                                   '-scriptPath', str(BASE / 'ghidra_scripts'), '-postScript', 'QoderExport.java', str(report)], timeout)
        result.update(artifacts=[artifact(ws, relative(ws, report), 'native_analysis')], success=result['success'] and report.is_file() and report.stat().st_size > 0)
        return result
    if name == 'semgrep':
        source = ws.file(inputs.get('path', '.'))
        rules = ws.file(inputs['rules'])
        out = new_output(ws, inputs, '.json')
        result = run(ws, command + ['scan', '--config', relative(ws, rules), '--json', '--output', relative(ws, out), '--metrics=off', '--disable-version-check', relative(ws, source)], timeout)
        if out.is_file() and result['exit_code'] in (0, 1):
            report = parsed_json(out)
            result.update(success=not report.get('errors'), findings=report.get('results', [])[:50], finding_count=len(report.get('results', [])), artifacts=[artifact(ws, relative(ws, out), 'security_report')])
        return result
    if name == 'codeql':
        out = new_output(ws, inputs, '.sarif' if operation == 'analyze' else '')
        if operation == 'database':
            language = inputs['language']
            if language not in {'java', 'javascript', 'python', 'cpp', 'csharp', 'go', 'ruby', 'swift', 'rust'}:
                raise ValueError('Unsupported CodeQL language.')
            argv = command + ['database', 'create', relative(ws, out), '--language=' + language, '--source-root=.', '--threads=2']
            build = inputs.get('build_argv')
            if build:
                import shlex
                ws.validate_argv(build)
                argv.append('--command=' + shlex.join(build))
        else:
            database = ws.file(inputs['path'])
            queries = ws.file(inputs['queries'])
            argv = command + ['database', 'analyze', relative(ws, database), relative(ws, queries), '--format=sarifv2.1.0', '--output=' + relative(ws, out), '--threads=2']
        result = run(ws, argv, timeout)
        if out.exists():
            result['artifacts'] = [artifact(ws, relative(ws, out), 'security_report' if operation == 'analyze' else 'codeql_database')]
            if operation == 'analyze' and result['success']:
                report = parsed_json(out)
                findings = [f for run_data in report.get('runs', []) for f in run_data.get('results', [])]
                result.update(findings=findings[:50], finding_count=len(findings))
        return result
    if name == 'mobsf':
        settings = config.get('mobsf', {})
        if not settings.get('url') or not settings.get('key_file'):
            raise ValueError('Configure mobsf.url and a private mobsf.key_file in tools.json.')
        source = ws.file(inputs['path'])
        if source.stat().st_size > 256_000_000:
            raise ValueError('APK exceeds upload size limit.')
        boundary = 'qoder' + uuid.uuid4().hex
        body = ('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="target.apk"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + source.read_bytes() + ('\r\n--' + boundary + '--\r\n').encode()
        uploaded = mobsf_call(settings, '/api/v1/upload', body, 'multipart/form-data; boundary=' + boundary, timeout, ws.cancel)
        identifier = uploaded.get('hash')
        if not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{32}', identifier):
            raise ValueError('MobSF did not return a valid uploaded APK hash.')
        form = urllib.parse.urlencode({'hash': identifier}).encode()
        mobsf_call(settings, '/api/v1/scan', form, 'application/x-www-form-urlencoded', timeout, ws.cancel)
        report = mobsf_call(settings, '/api/v1/report_json', form, 'application/x-www-form-urlencoded', timeout, ws.cancel)
        out = new_output(ws, inputs, '.json')
        out.write_text(json.dumps(report))
        return {'exit_code': 0, 'success': True, 'output': 'MobSF static report saved; findings require validation.',
                'artifacts': [artifact(ws, relative(ws, out), 'security_report')], 'findings_provisional': True}
    if name == 'zap':
        url = inputs['url']
        if urllib.parse.urlsplit(url).scheme not in {'http', 'https'}:
            raise ValueError('Supply an explicit HTTP(S) target URL.')
        out = new_output(ws, inputs)
        out.mkdir()
        report = out / 'report.json'
        # Automation Framework uses the cross-platform Java distribution locally.
        # The baseline wrapper remains available for previously configured hosts.
        headless = config.get('zap', {}).get('mode') == 'headless' or any(Path(a).name == 'zap.sh' for a in command)
        if headless:
            plan = out / 'plan.yaml'
            plan.write_text(json.dumps({'env': {'contexts': [{'name': 'qoder', 'urls': [url]}],
                'parameters': {'failOnError': True, 'progressToStdout': True}}, 'jobs': [
                {'type': 'spider', 'parameters': {'context': 'qoder', 'url': url, 'maxDuration': min(5, max(1, timeout // 120))}},
                {'type': 'passiveScan-wait', 'parameters': {'maxDuration': min(5, max(1, timeout // 120))}},
                {'type': 'report', 'parameters': {'template': 'traditional-json', 'reportDir': str(out), 'reportFile': 'report', 'displayReport': False}}
            ]}, indent=2))
            argv = command + ['-cmd', '-silent', '-config', 'autoupdate.checkOnStart=false', '-config', 'autoupdate.installAddonUpdates=false', '-autorun', str(plan)]
        else:
            argv = command + ['-t', url, '-J', str(report), '-m', str(min(10, max(1, timeout // 60)))]
        result = run(ws, argv, timeout, env={'JAVA_TOOL_OPTIONS': '-Djava.awt.headless=true'} if headless else None)
        result['success'] = False  # A process exit alone does not prove a security scan.
        if report.is_file() and result['exit_code'] in (0, 1, 2):
            data = parsed_json(report)
            findings = [a for site in data.get('site', []) for a in site.get('alerts', [])]
            result.update(success=result['exit_code'] == 0 if headless else True, findings=findings[:50], finding_count=len(findings), artifacts=[artifact(ws, relative(ws, report), 'security_report')])
            if result['success']:
                result['diagnostics'] = [{'severity': 'warning' if str(a.get('riskcode','0')) != '0' else 'info',
                    'message': a.get('name') or a.get('alert') or 'ZAP passive finding', 'provisional': True} for a in findings[:50]]
        return result
    if name == 'mitmproxy':
        out = new_output(ws, inputs, '.flows')
        if operation == 'capture':
            port = inputs.get('port', 8080)
            if not isinstance(port, int) or not 1024 <= port <= 65535:
                raise ValueError('Use a local proxy port from 1024 to 65535.')
            result = run(ws, command + ['--listen-host', '127.0.0.1', '--listen-port', str(port), '-w', relative(ws, out)], timeout)
            result['capture_window_ended'] = result.get('timeout', False)
            # The bounded capture window ending is expected, but a nonempty flow file is required.
            result['success'] = result['exit_code'] in (0, 124) and out.is_file() and out.stat().st_size > 0
        else:
            source = ws.file(inputs['path'])
            result = run(ws, command + ['-n', '-C', relative(ws, source), '-w', relative(ws, out)], timeout)
        result['artifacts'] = [artifact(ws, relative(ws, out), 'http_flows')]
        return result
    if name == 'libfuzzer':
        if operation == 'compile':
            source = ws.file(inputs['path'])
            out = new_output(ws, inputs)
            result = run(ws, command + ['-g', '-O1', '-fsanitize=fuzzer,address', relative(ws, source), '-o', relative(ws, out)], timeout)
            result.update(artifacts=[artifact(ws, relative(ws, out), 'fuzz_harness')], success=result['success'] and out.is_file())
            return result
        executable = ws.file(inputs['path'])
        corpus = ws.file(inputs['corpus'])
        if not corpus.is_dir():
            raise ValueError('Provide an existing corpus directory.')
        out = new_output(ws, inputs)
        out.mkdir()
        seconds = min(300, max(1, timeout - 5))
        result = run(ws, [str(executable), '-max_total_time=' + str(seconds), '-artifact_prefix=' + str(out) + '/', str(corpus)], timeout)
        result['artifacts'] = [artifact(ws, relative(ws, p), 'fuzz_crash') for p in out.iterdir() if p.is_file()]
        return result
    if name == 'debugger':
        executable = ws.file(inputs['path'])
        arguments = inputs.get('argv', [])
        if not isinstance(arguments, list) or not all(isinstance(a, str) and '\0' not in a for a in arguments):
            raise ValueError('Debugger arguments must be a string argv array.')
        result = run(ws, command + ['--batch', '-ex', 'run', '-ex', 'thread apply all bt', '--args', relative(ws, executable), *arguments], timeout)
        result['observation_matched'] = bool(re.search(r'Program received signal|#0\s+', result['output']))
        return result
    if name == 'ui':
        framework = inputs.get('framework', 'instrumentation' if android_scope(config) else 'maestro')
        if framework == 'instrumentation':
            runner = inputs.get('runner', '')
            if not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+/[A-Za-z0-9_.$]+', runner):
                raise ValueError('Supply an installed instrumentation package/runner, such as com.example.test/androidx.test.runner.AndroidJUnitRunner.')
            access = inputs.get('access', 'adb')
            argv = ['am', 'instrument', '-w', '-r', runner]
            result = android_shell(ws, access, argv, timeout, config)
            count = re.search(r'OK\s*\(\s*([0-9]+)\s+tests?\s*\)', result.get('output', ''))
            failed = re.search(r'FAILURES!!!|INSTRUMENTATION_FAILED|shortMsg=|INSTRUMENTATION_STATUS_CODE:\s*-[12]\b', result.get('output', ''))
            result.update(success=result.get('exit_code') == 0 and bool(count and int(count[1]) > 0) and not bool(failed),
                          tests_executed=int(count[1]) if count else 0)
            if not result['success']: result['error'] = 'Instrumentation did not confirm a nonempty passing test suite.'
            return result
        tests = ws.file(inputs['path'])
        if framework == 'maestro':
            argv = (config.get('commands', {}).get('maestro') or ['maestro']) + ['test', relative(ws, tests)]
        elif framework == 'playwright':
            chosen = manager(ws, inputs)
            # Use the installed project runner, never npx fetching a new package.
            runner = ws.root / 'node_modules/.bin/playwright'
            if not runner.is_file():
                raise ValueError('Project Playwright runner/browser is not installed.')
            argv = [str(runner), 'test', relative(ws, tests)]
        else:
            raise ValueError('Use instrumentation, maestro or playwright.')
        return test_result(run(ws, argv, timeout))
    raise ValueError('Adapter operation has no implementation.')


def android_shell(ws, access, argv, timeout, config):
    if access == 'rish':
        from bridge import status
        from device_tools import execute
        if not status()['rish_connected']: raise ValueError('Start Shizuku and authorize Termux; Rish is not connected.')
        return execute(argv, ws.progress, ws.cancel, str, timeout=timeout)
    if access != 'adb': raise ValueError('Android access must be adb or rish.')
    command = command_for('adb', config)
    if not command: raise ValueError('ADB is not installed.')
    result = run(ws, command + ['devices'], min(timeout, 10))
    devices = [line.split()[0] for line in result.get('output', '').splitlines() if re.search(r'\tdevice\s*$', line)]
    serial = config.get('adb_serial')
    if result.get('exit_code') != 0 or (serial and serial not in devices) or (not serial and len(devices) != 1):
        raise ValueError('Select one authorized ADB device; configure adb_serial when several are connected.')
    return run(ws, command + ['-s', serial or devices[0], 'shell', *argv], timeout)


def device_operation(ws, name, operation, inputs, timeout, config, command):
    from device_tools import execute
    from bridge import status
    if name == 'rish' and not status()['rish_connected']:
        raise ValueError('Start Shizuku and authorize Termux; Rish is not connected.')
    if name == 'adb':
        connected = run(ws, command + ['devices'], min(timeout, 10))
        if operation == 'devices':
            return connected
        lines = [line.split()[0] for line in connected['output'].splitlines() if '\tdevice' in line]
        serial = config.get('adb_serial')
        if serial and serial not in lines or not serial and len(lines) != 1:
            raise ValueError('Select exactly one authorized ADB device; configure adb_serial if needed.')
        command = command + ['-s', serial or lines[0]]
    def shell(argv):
        if name == 'rish':
            return execute(argv, ws.progress, ws.cancel, str, timeout=timeout)
        return run(ws, command + ['shell', *argv], timeout)
    if operation == 'logcat':
        count = inputs.get('lines', 100)
        if not isinstance(count, int) or not 1 <= count <= 1000:
            raise ValueError('Logcat line count must be 1..1000.')
        return shell(['logcat', '-d', '-t', str(count)])
    package = inputs['package']
    if not isinstance(package, str) or not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+', package):
        raise ValueError('Supply an Android package identifier.')
    if operation in {'package', 'permissions'}:
        return shell(['dumpsys', 'package', package])
    if operation != 'install':
        raise ValueError('Unsupported device operation.')
    source = ws.file(inputs['path'])
    paths=inputs.get('paths',[inputs['path']])
    if not isinstance(paths,list) or not 1<=len(paths)<=128 or not all(isinstance(p,str) for p in paths):raise ValueError('Use 1..128 relative APK paths.')
    sources=[ws.file(p) for p in paths]
    new_cert = certificate(ws, source, config, timeout)
    if not new_cert['success']:
        raise ValueError('APK signature verification failed; installation stopped.')
    for extra in sources:
        if extra==source:continue
        checked=certificate(ws,extra,config,timeout)
        if not checked['success'] or checked['certificates_sha256']!=new_cert['certificates_sha256']:raise ValueError('All split APK signatures must verify and use the same certificate.')
    aapt = config.get('commands', {}).get('aapt2') or ['aapt2']
    metadata = run(ws, aapt + ['dump', 'badging', relative(ws, source)], min(timeout, 30))
    found = re.search(r"package: name='([^']+)'", metadata['output'])
    if metadata['exit_code'] or not found or found[1] != package:
        raise ValueError('APK package identity could not be verified against the install target.')
    installed = shell(['pm', 'path', package])
    if installed['exit_code'] != 0:
        listing=shell(['pm','list','packages',package])
        if listing['exit_code']!=0 or 'package:'+package in listing['output'].splitlines():
            raise ValueError('Cannot inspect the installed package; installation stopped.')
        installed={'exit_code':0,'output':''}
    originals = [line[8:].strip() for line in installed['output'].splitlines() if line.startswith('package:')]
    preserved = []
    if originals:
        destination = new_output(ws, {})
        destination.mkdir()
        if name == 'rish':
            imported = engineering_tools.invoke(ws, 'import_apk', {'package': package, 'output': relative(ws, destination / 'original')}, str)
            preserved = imported['apks']
        else:
            for i, remote_path in enumerate(originals):
                if not remote_path.startswith('/') or not remote_path.endswith('.apk'):
                    raise ValueError('Unexpected installed APK path.')
                out = destination / (str(i) + '-original.apk')
                pulled = run(ws, command + ['pull', remote_path, relative(ws, out)], timeout)
                if not pulled['success']:
                    raise ValueError('Cannot preserve installed APK; installation stopped.')
                preserved.append(relative(ws, out))
        original_cert = certificate(ws, ws.file(preserved[0]), config, timeout)
        if not original_cert['success'] or original_cert['certificates_sha256'] != new_cert['certificates_sha256']:
            raise ValueError('Installed and rebuilt signing certificates differ. Originals retained; replacement stopped.')
    if name == 'adb':
        result = run(ws, command + ['install-multiple' if len(sources)>1 else 'install', '-r', *[relative(ws,p) for p in sources]], timeout)
    else:
        shared_files=[];staged_files=[];session=None;committed=False
        try:
            for apk in sources:
                shared=Path('/sdcard/Download')/('qoder-install-'+uuid.uuid4().hex+'.apk');shared_files.append(shared)
                staged='/data/local/tmp/'+shared.name;staged_files.append(staged)
                shutil.copyfile(apk,shared)
                copied=shell(['cp',str(shared),staged])
                if copied['exit_code']!=0:raise ValueError('Cannot stage APK through Android shell access.')
            if len(sources)==1:result=shell(['pm','install','-r',staged_files[0]])
            else:
                created=shell(['pm','install-create','-r','-S',str(sum(p.stat().st_size for p in sources))])
                match=re.search(r'created install session \[([0-9]+)\]',created['output'])
                if created['exit_code'] or not match:raise ValueError('Android package install session could not be created.')
                session=match[1]
                for index,(apk,staged) in enumerate(zip(sources,staged_files)):
                    written=shell(['pm','install-write','-S',str(apk.stat().st_size),session,str(index)+'.apk',staged])
                    if written['exit_code'] or 'Success' not in written['output']:raise ValueError('Split APK session write failed: '+written['output'])
                result=shell(['pm','install-commit',session]);committed=result['exit_code']==0 and 'Success' in result['output']
        finally:
            for shared in shared_files:shared.unlink(missing_ok=True)
            for cleanup in ([['pm','install-abandon',session]] if session and not committed else [])+([['rm','-f',*staged_files]] if staged_files else []):
                try:execute(cleanup,redact=str)
                except Exception:pass
    result['success'] = result['exit_code'] == 0 and 'Success' in result['output']
    result['artifacts'] = [artifact(ws, p, 'original_apk') for p in preserved]
    result['signature_verification'] = new_cert
    result['functional_verification_required'] = True
    return result
