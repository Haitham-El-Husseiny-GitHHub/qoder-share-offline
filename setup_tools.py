#!/usr/bin/env python3
"""Selective Termux provisioning. Runtime jobs never download dependencies."""
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROFILES = ['web', 'android', 'native', 'structural', 'lsp', 'remote']
PACKAGES = {
    'python': ['python3'], 'git': ['git'], 'ripgrep': ['rg'], 'llama-cpp': ['llama-server'], 'termux-services': ['sv'],
    'nodejs-lts': ['node'], 'npm': ['npm'], 'openjdk-21': ['java', 'javac'], 'apktool': ['apktool'], 'jadx': ['jadx'],
    'aapt2': ['aapt2'], 'aapt': ['aapt', 'zipalign'], 'apksigner': ['apksigner'], 'android-tools': ['adb'],
    'clang': ['clang', 'clang++', 'clangd'], 'make': ['make'], 'cmake': ['cmake'], 'ninja': ['ninja'], 'gdb': ['gdb'],
    'rust': ['cargo'], 'openssh': ['ssh'], 'rsync': ['rsync']
}


def ensure_packages(packages, run):
    missing = [name for name in dict.fromkeys(packages) if any(not shutil.which(cmd) for cmd in PACKAGES[name])]
    if missing:
        run('pkg', 'install', '-y', *missing)
    return missing


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def download(entry, folder):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / entry['file']
    if target.exists():
        if target.stat().st_size == entry['size'] and sha256(target) == entry['sha256']:
            return target
        raise ValueError('Existing tool archive failed its pinned checksum: ' + target.name)
    partial = target.with_suffix(target.suffix + '.partial')
    with urllib.request.urlopen(entry['url'], timeout=30) as response, partial.open('wb') as out:
        for chunk in iter(lambda: response.read(1024 * 1024), b''):
            out.write(chunk)
            if out.tell() > entry['size']:
                raise ValueError('Tool download exceeds its pinned size.')
    if partial.stat().st_size != entry['size'] or sha256(partial) != entry['sha256']:
        raise ValueError('Tool archive checksum mismatch: ' + target.name)
    os.replace(partial, target)
    return target


def extract(archive, folder):
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist()) > 600_000_000:
            raise ValueError('Tool archive expands beyond limit.')
        for entry in z.infolist():
            path = Path(entry.filename)
            if path.is_absolute() or '..' in path.parts or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Unsafe tool archive path.')
            target = (folder / path).resolve()
            if not target.is_relative_to(folder.resolve()):
                raise ValueError('Tool archive leaves its directory.')
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(entry) as source, target.open('wb') as dest:
                    shutil.copyfileobj(source, dest)
                mode = entry.external_attr >> 16 & 0o777
                if mode:
                    target.chmod(mode)


def launcher(bin_dir, name, argv, prefix):
    path = bin_dir / name
    if path.exists():
        raise ValueError('Existing launcher is preserved: ' + str(path))
    path.write_text('#!' + str(prefix / 'bin/sh') + '\nexec ' + shlex.join(argv) + ' "$@"\n')
    path.chmod(0o700)
    return str(path)


def install_tools(target, profiles, run, prefix, sdk=False):
    target = Path(target)
    lock = json.loads((BASE / 'tools.lock.json').read_text())
    profiles = set(PROFILES if 'all' in profiles else profiles)
    unknown = profiles - set(PROFILES)
    if unknown:
        raise ValueError('Unknown tool profiles: ' + ', '.join(sorted(unknown)))
    tool_dir, bin_dir = target / 'tools', target / 'tools/bin'
    bin_dir.mkdir(parents=True, exist_ok=True)
    config_path = target / 'tools.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else json.loads((BASE / 'backend/tools.example.json').read_text())
    config['execution_platform'] = 'android'
    commands = config.setdefault('commands', {})
    packages = []
    if profiles & {'web', 'lsp'}:
        packages += ['nodejs-lts', 'npm']
    if 'android' in profiles or sdk:
        packages += ['openjdk-21', 'apktool', 'jadx', 'aapt2', 'aapt', 'apksigner', 'android-tools']
    if profiles & {'native', 'lsp'}:
        packages += ['clang', 'make', 'cmake', 'ninja']
    if 'native' in profiles:
        packages += ['gdb']
    if 'structural' in profiles:
        packages += ['rust', 'clang']
    if 'remote' in profiles:
        packages += ['openssh', 'rsync']
    ensure_packages(packages, run)
    if 'android' in profiles:
        for name in ('apkeditor', 'bundletool'):
            if commands.get(name) or shutil.which('APKEditor' if name == 'apkeditor' else name):
                continue
            jar = download(lock['downloads'][name], tool_dir / 'downloads')
            commands[name] = ['java', '-jar', str(jar)]
        if any(not commands.get(name) and not shutil.which(name) for name in ('smali', 'baksmali')):
            source_zip = download(lock['downloads']['smali_source'], tool_dir / 'downloads')
            source_root = tool_dir / 'sources'
            source_root.mkdir(exist_ok=True)
            extract(source_zip, source_root)
            project = source_root / 'smali-3.0.6'
            run('sh', str(project / 'gradlew'), '-p', str(project), ':smali:fatJar', ':baksmali:fatJar', '--no-daemon', '--max-workers=2')
            for name in ('smali', 'baksmali'):
                jars = list((project / name / 'build/libs').glob('*-fat.jar'))
                if len(jars) != 1:
                    raise ValueError('Smali build did not produce exactly one standalone JAR for ' + name)
                if not commands.get(name) and not shutil.which(name):
                    commands[name] = ['java', '-jar', str(jars[0])]
    if 'structural' in profiles:
        from importlib.util import module_from_spec, spec_from_file_location
        spec = spec_from_file_location('_qoder_catalog', BASE / 'backend/tool_catalog.py')
        catalog = module_from_spec(spec)
        spec.loader.exec_module(catalog)
        if not catalog.command_for('ast_grep', config):
            run('cargo', 'install', 'ast-grep', '--version', lock['ast_grep'], '--locked', '--root', str(tool_dir / 'ast-grep'))
            executable = tool_dir / 'ast-grep/bin/sg'
            if not executable.is_file():
                raise ValueError('ast-grep build did not create the expected executable.')
            commands['ast_grep'] = [str(executable)]
    if 'lsp' in profiles:
        servers = config.setdefault('language_servers', {})
        def available(language):
            command=servers.get(language)
            return bool(isinstance(command,list) and command and shutil.which(command[0]))
        need_ts=any(not available(language) for language in ('typescript','javascript'))
        if need_ts and not shutil.which('typescript-language-server') and not (target / 'tools/npm/node_modules/.bin/typescript-language-server').exists():
            run('npm', 'install', '--prefix', str(tool_dir / 'npm'), *lock['npm'])
        ts = shutil.which('typescript-language-server') or str(tool_dir / 'npm/node_modules/.bin/typescript-language-server')
        for language in ('typescript', 'javascript'):
            if not available(language):
                servers[language] = [ts, '--stdio']
        pylsp = shutil.which('pylsp') or str(Path.home() / '.local/bin/pylsp')
        if not available('python') and not Path(pylsp).is_file():
            # Official Termux owns pip; do not replace/upgrade its pip package.
            run('python3', '-m', 'pip', 'install', '--user', lock['python_lsp'])
        if not available('python'):
            servers['python'] = [pylsp]
    if sdk:
        sdk_dir = Path(config.get('android_sdk') or str(Path.home() / 'Android/Sdk'))
        manager = sdk_dir / 'cmdline-tools/latest/bin/sdkmanager'
        if not manager.is_file() and not shutil.which('sdkmanager'):
            archive = download(lock['downloads']['android_sdk'], tool_dir / 'downloads')
            unpack = tool_dir / 'sdk-unpack'
            unpack.mkdir(exist_ok=True)
            extract(archive, unpack)
            (sdk_dir / 'cmdline-tools').mkdir(parents=True, exist_ok=True)
            shutil.move(str(unpack / 'cmdline-tools'), str(sdk_dir / 'cmdline-tools/latest'))
        manager = str(manager) if manager.is_file() else shutil.which('sdkmanager')
        # sdkmanager presents Google's actual license terms to the person running setup.
        components=[]
        if not (sdk_dir/'platforms/android-35/android.jar').is_file():components.append('platforms;android-35')
        if not (sdk_dir/'build-tools/35.0.0/source.properties').is_file():components.append('build-tools;35.0.0')
        if components:run('sh', manager, '--sdk_root=' + str(sdk_dir), *components)
        build_tools = sdk_dir / 'build-tools/35.0.0'
        for name in ('aapt', 'aapt2', 'zipalign', 'apksigner', 'aidl'):
            native = shutil.which(name)
            if native:
                dest = build_tools / name
                dest.unlink(missing_ok=True)
                dest.symlink_to(native)
        platform_tools = sdk_dir / 'platform-tools'
        platform_tools.mkdir(exist_ok=True)
        if shutil.which('adb') and not (platform_tools / 'adb').exists():
            (platform_tools / 'adb').symlink_to(shutil.which('adb'))
        config['android_sdk'] = str(sdk_dir)
    temp = config_path.with_suffix('.tmp')
    temp.write_text(json.dumps(config, indent=2) + '\n')
    temp.chmod(0o600)
    os.replace(temp, config_path)
    print('Configured native tool profiles:', ', '.join(sorted(profiles)) or 'existing tools only')
    print('Optional external adapters require working commands/services in tools.json; availability is checked at each job.')
    return config
