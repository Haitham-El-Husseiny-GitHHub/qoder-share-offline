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
        data['checks'] = [{'kind': 'build', 'argv': ['./gradlew', '--offline', 'assembleDebug']},
                          {'kind': 'tests', 'argv': ['./gradlew', '--offline', 'testDebugUnitTest']}]
    elif (root / 'pyproject.toml').is_file() or (root / 'tests').is_dir() or list(root.glob('test_*.py')):
        data.update(source=True, kind='python')
        data['checks'] = [{'kind': 'tests', 'argv': ['python3', '-m', 'unittest', 'discover', '-s', 'tests' if (root / 'tests').is_dir() else '.', '-v']}]
    elif (root / 'CMakeLists.txt').exists():
        data.update(source=True, kind='native')
        # Configuration must precede build; the model gets the exact commands.
        data['checks'] = [{'kind': 'configure', 'argv': ['cmake', '-S', '.', '-B', 'qoder-build']},
                          {'kind': 'build', 'argv': ['cmake', '--build', 'qoder-build']},
                          {'kind': 'tests', 'argv': ['ctest', '--test-dir', 'qoder-build', '--output-on-failure']}]
    return data


def launch_failure(text):
    return bool(re.search(r"\b(crash(?:es|ed)?|does not load|doesn't load|doesnt load|will not open|won't open|upon opening|on opening|on launch|force[- ]close)\b", text.lower()))


def device_intent(objective):
    text=objective.lower()
    source_target=bool(re.search(r'\bsource\b|\b[\w/-]+\.(?:py|js|ts|java|kt|c|cpp)\b',text))
    return not source_target and bool(re.search(
        r'\b(installed app|app installed|logcat|shizuku|dumpsys|device crash)\b|'
        r'\bapp\b.*\b(crash(?:es|ing)?|not opening|not launching|shuts down|closing|won.t open)\b',text))


def select(root, objective, profile, inventory, config):
    """Pure first-match routing. No discovery, network requests or tool calls."""
    detected=project(root)
    text=objective.lower()
    source=detected['source']
    fix=profile=='FIX' or bool(re.search(r'\b(fix|repair|bug|failing|failure|broken)\b',text))
    crash=launch_failure(text) or bool(re.search(r'\b(crashing|not opening|shuts down)\b',text))
    modify=bool(re.search(r'\b(modify|rebuild|repack|merge|sign|resign|edit|patch)\b',text)) and bool(re.search(r'\b(apk|apks|apkm|xapk|smali)\b',text))
    if config.get('ambiguous_source'):
        workflow,adapters,required,reason='device',['adb','rish'],['device_inspection'],'ambiguous source'
    elif modify:
        workflow='apk_modify';adapters=['jadx','apktool','apkeditor','baksmali','smali','zipalign','apksigner','bundletool']
        required=['apk_rebuild'] if re.search(r'\b(modify|rebuild|repack|merge|edit|patch)\b',text) else []
        if 'unsigned' not in text and re.search(r'\b(sign|resign|signed|signature)\b',text):required.append('apk_signature')
        if re.search(r'\binstall(?:ation)?\b',text):adapters+=['adb','rish'];required.append('installation')
        if re.search(r'\b(functional|instrumentation|ui test)\b',text):adapters.append('ui');required.append('functional')
        reason='explicit APK modification'
    elif re.search(r'\b(readme|documentation|typo|spelling)\b',text):
        workflow,adapters,required,reason='text_edit',[],['change','text_validation'],'explicit text edit'
    elif profile=='AUDIT' or re.search(r'\b(security|vulnerability|vulnerabilities|cve)\b',text):
        workflow,adapters,required,reason='security',['ast_grep'],['security_scan'],'source scan; findings do not imply repair'
    elif re.search(r'\b(segfault|backtrace|fuzz|native|ghidra)\b|\.so\b',text) and not (source and fix) and re.search(r'\b(analyse|analyze|analysis|segfault|backtrace|fuzz|ghidra)\b',text):
        workflow,adapters,required,reason='native',['debugger','frida','libfuzzer'],['runtime_observation'],'native runtime analysis'
    elif not source and not crash and re.search(r'\b(api|http|https|endpoint|request)\b',text):
        workflow,adapters,required,reason='api',['http','mitmproxy'],['api_response'],'API response inspection'
    elif not source and (crash or device_intent(objective)):
        workflow,adapters,required,reason='device',['adb','rish'],['device_inspection'],'device diagnosis without a source project'
    elif not source and re.search(r'\b(apk|aab|dex|smali)\b',text):
        workflow,adapters,required,reason='apk_inspect',['jadx','apktool','apkeditor','baksmali'],['apk_inspection'],'decode or decompile an existing APK'
    elif profile=='REVIEW' or re.search(r'^\s*(explain|inspect|read|find|search|summarize)\b',text):
        workflow,adapters,required,reason='inspect',[],['inspection'],'read-only inspection'
    elif fix:
        workflow,adapters,required,reason='source_fix',['language_server','ast_grep'],['reproduction','tests','change'],'repair an existing source project' if source else 'no source project'
    elif source:
        workflow,adapters,required,reason='source_build',['language_server','ast_grep'],['tests'],'build the open project; no edit required'
    else:
        workflow,adapters,required,reason='inspect',[],['project'],'no source project or diagnostic target'
    checks=[]
    if workflow in {'source_fix','source_build'}:
        checks=detected['checks']
        builder={'android':'gradle','gradle':'gradle','node':'node','native':'cmake'}.get(detected['kind'])
        if builder:adapters.append(builder)
        if any(c['kind']=='build' for c in checks):required.append('build')
        if re.search(r'\brefactor\b',text) and any(c['kind']=='typecheck' for c in checks):required.append('typecheck')
        # Optional tools must be explicitly requested rather than implied by words like API.
        if re.search(r'\b(language server|lsp)\b',text) and 'language_server' not in adapters:adapters.append('language_server')
        if re.search(r'\bui\b|instrumentation',text):adapters.append('ui')
        if re.search(r'\bhttp client\b',text):adapters.append('http')
        if re.search(r'\bapktool\b',text):adapters.append('apktool')
    if android_scope(config):adapters=[n for n in adapters if n not in ANDROID_EXCLUDED]
    return {'workflow':workflow,'adapters':list(dict.fromkeys(adapters)),'required':required,'checks':checks,'reason':reason}


def execution_plan(root, objective, profile, inventory, config):
    """Add runner bookkeeping to a pure five-field routing decision."""
    decision=select(root,objective,profile,inventory,config)
    detected=project(root)
    custom=config.get('verification_commands',[])
    if not isinstance(custom,list):raise ValueError('verification_commands must be an array.')
    if custom and decision['workflow'] in {'source_fix','source_build'}:decision['checks']=custom
    return {**decision,'target_kind':detected['kind'],'manager':detected['manager'],
            'source_preferred':detected['source'] and decision['workflow'] in {'source_fix','source_build'},
            'custom_checks':bool(custom),'readonly':profile in {'REVIEW','AUDIT'} or decision['workflow']=='inspect',
            'mutating':decision['workflow'] in {'source_fix','source_build','text_edit','apk_modify'} and profile not in {'REVIEW','AUDIT','VERIFY'},
            'prerequisites':{n:inventory['tools'].get(n,{}).get('missing',['Unavailable adapter']) for n in decision['adapters'] if not inventory['tools'].get(n,{}).get('installed')},
            'max_steps':6,'max_identical_failures':2}


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
