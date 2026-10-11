"""Declarative adapters and bounded, observed prerequisite discovery."""
import json
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / 'tools.json'

ANDROID_EXCLUDED = {'ghidra', 'semgrep', 'codeql', 'mobsf'}
ADAPTER_GROUPS = {
    'code_intelligence': ['code_search', 'language_server', 'ast_grep'],
    'file_editing': ['read_file', 'write_file', 'edit_patch', 'unified_patch'],
    'version_control': ['git_diff', 'recovery_workspace'],
    'command_execution': ['run_argv', 'diagnose'],
    'android_build': ['gradle', 'zipalign', 'apksigner', 'bundletool'],
    'web_pwa_build': ['node'],
    'device_diagnostics': ['adb', 'rish', 'bridge_status', 'device_argv'],
    'apk_analysis_editing': ['jadx', 'apktool', 'smali', 'baksmali', 'apkeditor', 'import_apk'],
    'runtime_inspection': ['frida', 'debugger'],
    'network_inspection': ['http', 'mitmproxy'],
    'security_testing': ['zap'],
    'verification': ['verify_goal', 'diagnose', 'ui', 'libfuzzer', 'node', 'gradle', 'cmake'],
}


def android_scope(config):
    return config.get('execution_platform') == 'android' or bool(os.environ.get('TERMUX_VERSION')) or os.environ.get('PREFIX', '').startswith('/data/data/com.termux/')


def spec(commands, operations, purpose, prerequisites=(), heavy=False, verify='exit_and_artifacts'):
    return dict(commands=commands, operations=operations, capabilities=purpose,
                prerequisites=list(prerequisites), heavy=heavy, verification=verify,
                timeout_seconds=600 if heavy else 120, max_timeout_seconds=1200 if heavy else 600)


CATALOG = {
    'language_server': spec([], ['definition', 'references', 'diagnostics'], 'Code definitions, references and diagnostics', ['A configured stdio language server for the file language']),
    'ast_grep': spec(['ast-grep', 'sg'], ['search', 'rewrite'], 'Structural code search and checked rewrites', verify='diff_and_tests'),
    'gradle': spec(['java', 'javac'], ['build', 'test', 'tasks'], 'Project Gradle Wrapper builds', ['Project gradlew and cached Gradle/dependencies; Android SDK for Android projects'], True),
    'node': spec(['node'], ['build', 'test', 'typecheck', 'install'], 'Frontend/backend builds using the project lockfile', ['Matching package manager and cached dependencies']),
    'cmake': spec(['cmake'],['configure','build','test'],'Native project builds and CTest',['CMake project, compiler and project dependencies'],True),
    'adb': spec(['adb'], ['devices', 'logcat', 'package', 'install'], 'Authorized Android device diagnostics', ['An authorized ADB connection'], verify='device_observation'),
    'rish': spec(['rish'], ['logcat', 'package', 'permissions', 'install'], 'Shizuku Android shell diagnostics', ['Running Shizuku with Termux authorized'], verify='device_observation'),
    'jadx': spec(['jadx'], ['decompile'], 'Java/Kotlin APK inspection', ['JDK'], True),
    'apktool': spec(['apktool'], ['decode', 'rebuild'], 'APK resource/DEX decoding and rebuilding', ['JDK'], True),
    'apkeditor': spec(['APKEditor', 'apkeditor'], ['decode', 'rebuild', 'merge'], 'REAndroid APK resources and compatible split merging', ['JDK'], True),
    'smali': spec(['smali'], ['assemble'], 'Assemble editable DEX instructions', ['JDK']),
    'baksmali': spec(['baksmali'], ['disassemble'], 'Disassemble DEX into smali', ['JDK']),
    'zipalign': spec(['zipalign'], ['align', 'verify'], 'APK alignment before signing'),
    'apksigner': spec(['apksigner'], ['sign', 'verify'], 'APK signing and certificate verification', ['Signing keystore configured outside the model workspace'], verify='signature_verification'),
    'bundletool': spec(['bundletool'], ['build', 'extract', 'install', 'validate'], 'AAB to device-specific APK sets', ['JDK; explicit signing configuration for APK sets'], True),
    'frida': spec(['frida', 'frida-inject'], ['processes', 'instrument'], 'Observe a running app with an explicit script', ['Native injection requires target process access, often root; server/Gadget clients require matching versions'], True, 'runtime_observation'),
    'ghidra': spec(['analyzeHeadless'], ['analyze'], 'Native binary analysis and function decompilation', ['Supported host, JDK, native Ghidra components'], True, 'analysis_and_observation'),
    'semgrep': spec(['semgrep'], ['scan'], 'Source security analysis with local rules', ['Local rules; supported Python/native runtime'], True, 'findings_and_retest'),
    'codeql': spec(['codeql'], ['database', 'analyze'], 'Repository dataflow vulnerability analysis', ['Supported host; locally installed queries and language packs'], True, 'findings_and_retest'),
    'mobsf': spec([], ['scan'], 'MobSF APK security assessment and JSON reports', ['Configured reachable MobSF service and private API key'], True, 'findings_and_retest'),
    'zap': spec(['zap.sh', 'zap-baseline.py'], ['scan'], 'ZAP headless passive scan with JSON output', ['Working Java/headless ZAP and Automation/Reports add-ons; explicit target URL; Android compatibility test'], True, 'findings_and_retest'),
    'mitmproxy': spec(['mitmdump'], ['capture', 'replay'], 'HTTP interception and saved-flow replay', ['Configured client proxy/trust for HTTPS interception'], True, 'request_replay'),
    'http': spec([], ['request'], 'HTTP client for API reproduction', ['Explicit target URL'], verify='expected_response'),
    'libfuzzer': spec(['clang++'], ['compile', 'run'], 'Coverage-guided native fuzzing', ['Compatible libFuzzer runtime; an existing harness'], True, 'harness_run'),
    'debugger': spec(['gdb'], ['backtrace'], 'Native crash reproduction and stack trace', ['Debuggable executable and symbols'], True, 'runtime_observation'),
    'ui': spec(['adb', 'rish', 'maestro', 'playwright'], ['test'], 'Android instrumentation or existing project UI automation', ['Installed instrumentation test APK and authorized ADB/Rish; or a compatible project test runner'], True, 'test_result'),
}


def load_config(path=CONFIG_PATH):
    if not Path(path).exists():
        return {'schema': 1, 'commands': {}, 'language_servers': {}, 'remote': {'enabled': False}}
    data = json.loads(Path(path).read_text())
    if data.get('schema') != 1 or not isinstance(data.get('commands', {}), dict):
        raise ValueError('Invalid tools.json schema.')
    return data


def command_for(name, config=None):
    config = config or load_config()
    configured = config.get('commands', {}).get(name)
    if configured is not None:
        if not isinstance(configured, list) or not configured or not all(isinstance(x, str) and '\0' not in x for x in configured):
            raise ValueError('Configured commands must be nonempty string argv arrays.')
        return configured if shutil.which(configured[0]) else None
    for candidate in CATALOG[name]['commands']:
        resolved = shutil.which(candidate)
        if not resolved:
            continue
        if name == 'ast_grep' and candidate == 'sg':
            try:
                probe = subprocess.run([resolved, '--version'], capture_output=True, text=True, timeout=3)
                if probe.returncode != 0 or 'ast-grep' not in probe.stdout:
                    continue
            except (OSError, subprocess.TimeoutExpired):
                continue
        return [resolved]
    return None


def discover(config=None, device=True):
    config = config or load_config()
    tools = {}
    for name, definition in CATALOG.items():
        if android_scope(config) and name in ANDROID_EXCLUDED:
            continue
        cmd = command_for(name, config)
        available = bool(cmd) or name == 'http'
        if name == 'language_server':
            available = any(isinstance(v, list) and v and shutil.which(v[0]) for v in config.get('language_servers', {}).values())
        if name == 'mobsf':
            available = bool(config.get('mobsf', {}).get('url') and config.get('mobsf', {}).get('key_file'))
        if name=='gradle':available=bool(shutil.which('java') and shutil.which('javac'))
        tools[name] = {**definition, 'installed': available, 'access': 'unverified',
                       'command': cmd, 'status':'present_unverified' if available else 'missing',
                       'verification_operation':{'tool':'verify_goal','inputs':{'run_checks':True}},
                       'missing': [] if available else definition['prerequisites'] or ['Executable not installed']}
    access = {'termux': bool(os.environ.get('TERMUX_VERSION') or os.environ.get('PREFIX', '').startswith('/data/data/com.termux/')),
              'architecture': platform.machine(), 'root': 'unverified', 'adb': 'unverified', 'rish': 'unverified',
              'remote': 'disabled_android_scope' if android_scope(config) else ('configured_unverified' if config.get('remote', {}).get('enabled') else 'not_configured')}
    if device:
        from bridge import status
        bridge = status()
        access['rish'] = 'available' if bridge['rish_connected'] else 'unavailable'
        access['root'] = 'available' if bridge['access_level'] == 'root' else 'not_granted'
        tools['rish']['access'] = access['rish']
        adb = command_for('adb', config)
        if adb:
            try:
                p = subprocess.run(adb + ['devices'], capture_output=True, text=True, timeout=4)
                access['adb'] = 'available' if p.returncode == 0 and re.search(r'\tdevice\s*$', p.stdout, re.M) else 'unavailable'
            except (OSError, subprocess.TimeoutExpired):
                access['adb'] = 'unavailable'
        else:
            access['adb'] = 'missing'
        tools['adb']['access'] = access['adb']
    sdk = Path(config.get('android_sdk') or os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or str(Path.home() / 'Android/Sdk'))
    access['android_sdk'] = str(sdk) if (sdk / 'platforms').is_dir() else 'missing'
    return {'schema': 1, 'checked_at': time.time(), 'tools': tools, 'access': access, 'adapter_groups': ADAPTER_GROUPS}


def public_capabilities(inventory):
    """Keep private host paths and credentials outside model/UI inventories."""
    return {'schema': 1, 'checked_at': inventory['checked_at'], 'access': inventory['access'],
            'adapter_groups': inventory.get('adapter_groups', ADAPTER_GROUPS),
            'tools': {n: {k: v for k, v in d.items() if k != 'command'} for n, d in inventory['tools'].items()}}
