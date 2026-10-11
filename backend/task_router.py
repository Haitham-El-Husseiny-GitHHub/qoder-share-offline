"""Select a small workflow and enforce evidence-based completion."""
import json
import re
from pathlib import Path
from tool_catalog import android_scope, ANDROID_EXCLUDED


def project(root):
    root = Path(root)
    data = {'source': False, 'kind': 'files', 'manager': None, 'checks': []}
    if (root / 'package.json').is_file():
        package = json.loads((root / 'package.json').read_text())
        lockfiles = [(n, m) for n, m in [('pnpm-lock.yaml', 'pnpm'), ('yarn.lock', 'yarn'), ('bun.lock', 'bun'), ('bun.lockb', 'bun'), ('package-lock.json', 'npm')] if (root / n).exists()]
        managers = {m for _, m in lockfiles}
        declared = package.get('packageManager', '').split('@')[0]
        if len(managers) > 1 and declared not in managers:
            raise ValueError('Conflicting package-manager lockfiles. Set packageManager in package.json.')
        manager = declared if declared in {'npm', 'pnpm', 'yarn', 'bun'} else next(iter(managers), 'npm')
        data.update(source=True, kind='node', manager=manager)
        for script, kind in [('build', 'build'), ('test', 'tests'), ('typecheck', 'typecheck'), ('check', 'typecheck')]:
            if script in package.get('scripts', {}):
                data['checks'].append({'kind': kind, 'argv': [manager, 'run', script]})
    elif (root / 'gradlew').is_file():
        android = any('com.android.' in p.read_text(errors='replace')[:50000] for p in list(root.glob('*.gradle*')) + list(root.glob('*/build.gradle*')))
        data.update(source=True, kind='android' if android else 'gradle')
        data['checks'] = [{'kind': 'build', 'argv': ['./gradlew', '--offline', 'assembleDebug' if android else 'assemble']},
                          {'kind': 'tests', 'argv': ['./gradlew', '--offline', 'testDebugUnitTest' if android else 'test']}]
    elif (root / 'pyproject.toml').is_file() or (root / 'tests').is_dir() or list(root.glob('test_*.py')):
        data.update(source=True, kind='python')
        pytest_project = (root / 'pytest.ini').exists() or ((root / 'pyproject.toml').exists() and 'pytest' in (root / 'pyproject.toml').read_text())
        if pytest_project:
            data['checks'] = [{'kind': 'tests', 'argv': ['python3', '-m', 'pytest', '-q']}]
        else:
            data['checks'] = [{'kind': 'tests', 'argv': ['python3', '-m', 'unittest', 'discover', '-s', 'tests' if (root / 'tests').is_dir() else '.', '-v']}]
    elif (root / 'CMakeLists.txt').exists():
        data.update(source=True, kind='native')
        # Configuration must precede build; the model gets the exact commands.
        data['checks'] = [{'kind': 'configure', 'argv': ['cmake', '-S', '.', '-B', 'qoder-build']},
                          {'kind': 'build', 'argv': ['cmake', '--build', 'qoder-build']},
                          {'kind': 'tests', 'argv': ['ctest', '--test-dir', 'qoder-build', '--output-on-failure']}]
    return data


def select(root, objective, profile, inventory, config):
    text = objective.lower()
    # Explicit installed-app intent wins over unrelated files in the workspace.
    source_target = bool(re.search(r'\bsource\b|\b[\w/-]+\.(?:py|js|ts|java|kt|c|cpp)\b', text))
    device_target = not source_target and bool(re.search(
        r'\b(installed app|app installed|logcat|shizuku|dumpsys|device crash)\b|'
        r'\bapp\b.*\b(crash(?:es|ing)?|not opening|not launching|shuts down|closing|won.t open)\b', text))
    detected = {'source':False,'kind':'device','manager':None,'checks':[]} if device_target else project(root)
    mutate_apk = bool(re.search(r'\b(modify|rebuild|repack|merge|sign|resign|edit|patch)\b.{0,70}\b(apk|apks|apkm|xapk|dex|smali)\b|\b(apk|smali)\b.{0,70}\b(modify|rebuild|patch|sign)\b', text))
    if not mutate_apk and not device_target and not source_target and profile not in {'REVIEW','AUDIT','VERIFY'} and re.search(r'\b(readme|documentation|typo|spelling)\b',text):
        route,adapters,required='text_edit',[],['change','text_validation']
    elif mutate_apk:
        route, adapters, required = 'apk_modify', ['jadx', 'apktool', 'apkeditor', 'baksmali', 'smali', 'zipalign', 'apksigner', 'bundletool', 'adb', 'rish', 'ui'], ['apk_signature', 'installation', 'functional']
        if 'unsigned' in text:
            required = ['apk_rebuild']
        elif re.search(r'\b(modify|rebuild|repack|merge|edit|patch)\b',text):required.insert(0,'apk_rebuild')
    elif device_target:
        route, adapters, required = 'device', ['adb', 'rish', 'ui'], ['device_inspection', 'functional']
    elif re.search(r'\b(security|vulnerab|audit|cve|penetration)', text) or profile == 'AUDIT':
        route = 'security'
        adapters = ['semgrep', 'codeql'] if detected['source'] else ['mobsf', 'zap']
        if list(Path(root).glob('*.apk')):
            adapters.append('mobsf')
        required = ['security_scan', 'security_validation']
    elif re.search(r'\b(native|segfault|segmentation|backtrace|fuzz|ghidra)\b|\.so\b',text) and re.search(r'\b(analyse|analyze|inspect|reverse|crash|segfault|segmentation|backtrace|fuzz|ghidra)\b',text) and not (detected['source'] and (profile=='FIX' or re.search(r'\b(fix|repair)\b',text))):
        route, adapters, required = 'native', ['ghidra', 'debugger', 'frida', 'libfuzzer', 'adb', 'rish'], ['native_analysis', 'runtime_observation']
    elif re.search(r'\b(api|http|https|request|endpoint|proxy|network)\b', text) and not detected['source']:
        route, adapters, required = 'api', ['http', 'mitmproxy'], ['api_reproduction', 'api_response']
    elif re.search(r'\b(installed app|logcat|shizuku|permissions|dumpsys|device crash)\b', text) and not detected['source']:
        route, adapters, required = 'device', ['adb', 'rish', 'ui'], ['device_inspection', 'functional']
    elif not detected['source'] and re.search(r'\b(apk|aab|dex|smali)\b', text):
        route, adapters, required = 'apk_inspect', ['jadx', 'apktool', 'apkeditor', 'baksmali', 'bundletool'], ['inspection']
    elif profile == 'REVIEW' or re.search(r'^\s*(explain|inspect|read|summarize|find|search)\b', text):
        route, adapters, required = 'inspect', ['language_server', 'ast_grep'], ['inspection']
    else:
        fix = profile == 'FIX' or bool(re.search(r'\b(fix|repair|bug|failing|failure|broken)\b', text))
        route = 'source_fix' if fix else 'source_build'
        adapters = ['language_server', 'ast_grep']
        if detected['kind'] in {'android', 'gradle'}:
            adapters.append('gradle')
        elif detected['kind'] == 'node':
            adapters.append('node')
        elif detected['kind']=='native':adapters.append('cmake')
        elif re.search(r'\b(android|kotlin|java)\b',text):adapters.append('gradle')
        if re.search(r'\b(ui|instrumentation|functional|end.to.end)\b', text):adapters.append('ui')
        if re.search(r'\b(api|http|endpoint|network)\b',text):adapters.extend(['http','mitmproxy'])
        required = (['reproduction'] if fix else []) + ['tests']
        if fix or re.search(r'\b(create|extend|add|implement|modify|refactor|update|new app)\b',text):
            if profile!='VERIFY':required.append('change')
        if any(c['kind'] == 'build' for c in detected['checks']):
            required.append('build')
        if re.search(r'\brefactor\b', text) and any(c['kind'] == 'typecheck' for c in detected['checks']):
            required.append('typecheck')
    custom = config.get('verification_commands', [])
    if android_scope(config):
        adapters = [name for name in adapters if name not in ANDROID_EXCLUDED]
        if route == 'security':
            if detected['kind'] == 'node' or re.search(r'\b(web|api|http|https|service|zap)\b', text):
                adapters = ['zap','http']
            else:
                adapters = ['language_server','ast_grep'] if detected['source'] else ['jadx','apktool','frida']
                required = ['inspection','security_validation']
        if route == 'native' and 'ghidra' not in adapters:
            required = ['runtime_observation']
    if not isinstance(custom, list):
        raise ValueError('verification_commands must be an array of {kind, argv} objects.')
    checks = custom or (detected['checks'] if route in {'source_fix','source_build','inspect','security'} else [])
    return {'workflow': route, 'target_kind': detected['kind'], 'source_preferred': detected['source'] and not mutate_apk and not device_target,
            'adapters': adapters, 'required': required, 'checks': checks, 'manager': detected['manager'],
            'prerequisites': {name: inventory['tools'][name]['missing'] for name in adapters if not inventory['tools'][name]['installed']},'custom_checks':bool(custom),
            'mutating': route in {'source_fix', 'source_build', 'apk_modify','text_edit'} and profile not in {'REVIEW', 'AUDIT'},
            'max_steps': 32, 'max_identical_failures': 2}


def evidence(journal):
    data = journal.data
    revision = data['revision']
    latest={}
    for check in data['checks']:
        if check['revision']==revision:latest[(check['kind'],json.dumps(check.get('argv'),sort_keys=True),check.get('name'))]=check
    current={c['kind'] for c in latest.values() if c['success']}
    for check in latest.values():
        if not check['success']:current.discard(check['kind'])
    if any('after_sha256' in p and p.get('before_sha256')!=p.get('after_sha256') for p in data['patches']):current.add('change')
    plan = data['plan']
    if 'reproduction' in plan['required']:
        failed = [c for c in data['checks'] if c['kind'] in {'tests','build'} and c['exit_code'] not in (None, 0) and c['revision'] < revision]
        passed = [c for c in latest.values() if c['kind'] in {'tests','build'} and c['success']]
        failed = [f for f in failed if f.get('exit_code') not in {124, 126, 127} and not f.get('missing_prerequisite') and not f.get('timeout')]
        if any(f['argv'] == p['argv'] and all(p.get('test_inputs',{}).get(name)==sha for name,sha in f.get('test_inputs',{}).items()) for f in failed for p in passed):
            current.add('reproduction')
    missing = [kind for kind in plan['required'] if kind not in current]
    return {'verified': not missing, 'required': plan['required'], 'passed': sorted(current), 'missing': missing,
            'revision': revision, 'checks': data['checks'][-20:], 'artifacts': data['artifacts'], 'workspace': data['workspace']}


def check_kind(argv, plan):
    for check in plan['checks']:
        if argv == check['argv']:
            return check['kind']
    text = ' '.join(argv)
    if re.search(r'\b(pytest|unittest|ctest|testDebugUnitTest|test|tests)\b', text):
        return 'tests'
    if re.search(r'\b(assembleDebug|assemble|build)\b', text):
        return 'build'
    if re.search(r'\b(typecheck|tsc|check)\b', text):
        return 'typecheck'
    return 'command'


def test_result(result):
    """A zero exit code with no tests collected is not verification."""
    output = result.get('output', '')
    empty = bool(re.search(r'Ran 0 tests|no tests ran|no tests found|No tests found|collected 0 items|No tests were found|No test files found|\b0 passing|Running 0 tests|Test Suites:\s*0\b|# tests\s+0\b|:test\w*\s+NO-SOURCE', output))
    return {**result, 'success': result.get('exit_code') == 0 and not empty,
            **({'error': 'No tests executed; add or select a relevant project test.'} if empty else {})}
