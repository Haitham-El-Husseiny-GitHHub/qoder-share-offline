#!/usr/bin/env python3
"""Install downloaded Android tools without using internet repositories."""
import argparse, hashlib, json, lzma, os, re, shutil, subprocess, tarfile, tempfile, time, zipfile
from pathlib import Path

COMMANDS = {
    'python':['python3'], 'python-pip':['pip'], 'git':['git'], 'ripgrep':['rg'],
    'llama-cpp':['llama-server'], 'termux-services':['sv'], 'nodejs-lts':['node'],
    'npm':['npm'], 'openjdk-21':['java','javac'], 'apktool':['apktool'], 'jadx':['jadx'],
    'aapt2':['aapt2'], 'aapt':['aapt','zipalign'], 'apksigner':['apksigner'],
    'android-tools':['adb'], 'aidl':['aidl'], 'clang':['clang','clang++','clangd'],
    'make':['make'], 'cmake':['cmake'], 'ninja':['ninja'], 'gdb':['gdb'],
    'rust':['cargo'], 'openssh':['ssh'], 'rsync':['rsync'], 'curl':['curl'],
    'unzip':['unzip'], 'proot':['proot'], 'gradle':['gradle'], 'termux-am':['am']
}

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

STAMP_NAME='.qoder-companion-stamp.json'

def companion_manifest(cache,companion=None):
    package=json.loads(((companion or cache/'android/qoder-companion')/'package.json').read_text())
    if not isinstance(package.get('build'),int) or package['build']<1:
        raise ValueError('Companion package has no valid build number.')
    return package

def refuse_downgrade(target,incoming):
    stamp=Path(target)/STAMP_NAME
    if not stamp.exists():return
    try:data=json.loads(stamp.read_text())
    except (OSError,ValueError) as exc:raise ValueError('Companion stamp is unreadable; repair the installation before updating.') from exc
    current=data.get('companion_build')
    if not isinstance(current,int):raise ValueError('Companion stamp is invalid; repair the installation before updating.')
    if current>incoming:raise ValueError('Refusing companion downgrade from build %d to %d.'%(current,incoming))

def write_stamp(target,data):
    stamp=Path(target)/STAMP_NAME;temporary=stamp.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,indent=2)+'\n');temporary.chmod(0o600);os.replace(temporary,stamp)

def probe(argv,timeout=20,tool=None):
    try:
        result=subprocess.run([str(x) for x in argv],capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {'argv':[str(x) for x in argv],'passed':False,'error':str(exc)}
    output=result.stdout+result.stderr
    # APKEditor 1.4.9 intentionally exits 2 for its version command.
    # Only this exact version response is accepted; operational failures stay failures.
    version_query=list(argv)[-1:] in [['-v'],['-version'],['--version']]
    known_version=(tool=='apkeditor' and version_query and result.returncode==2 and
                   output.strip()=='APKEditor version 1.4.9, ARSCLib version 1.3.9')
    return {'argv':[str(x) for x in argv],'passed':result.returncode==0 or known_version,
            'exit_code':result.returncode,'output':output[-1000:]}

def zipalign_probe():
    with tempfile.TemporaryDirectory(prefix='qoder-zipalign-') as folder:
        source=Path(folder)/'input.apk';aligned=Path(folder)/'aligned.apk'
        with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED) as archive:
            archive.writestr('assets/probe.bin',b'Qoder alignment probe')
        result=probe(['zipalign','-f','4',source,aligned])
        if result['passed']:result=probe(['zipalign','-c','4',aligned])
        return {'tool':'zipalign',**result}

def node_command(script,*args):
    # npm bin shebangs use /usr/bin/env, which is absent on Android.
    script=Path(script).resolve(strict=True)
    node=shutil.which('node')
    if not node:raise ValueError('Node runtime is missing.')
    return [node,str(script),*args]

def core_probes(target,config):
    commands=config.get('commands',{})
    required=[
        ['rg','--version'],['git','--version'],['python3','--version'],['java','-version'],
        ['javac','-version'],['node','--version'],['npm','--version'],['jadx','--version'],
        ['apktool','--version'],['aapt2','version'],['apksigner','--help'],
        ['adb','version'],['clang','--version'],['cmake','--version'],['gradle','--version'],
        ['curl','--version']]
    results=[probe(argv) for argv in required]+[zipalign_probe()]
    for name in ('ast_grep','apkeditor','bundletool','smali','baksmali'):
        command=commands.get(name)
        if not isinstance(command,list) or not command:results.append({'tool':name,'passed':False,'error':'No configured command.'});continue
        args=['--version'] if name in {'ast_grep','smali','baksmali'} else (['version'] if name=='bundletool' else ['-v'])
        results.append({'tool':name,**probe(command+args,tool=name)})
    # A deterministic patch/rollback probe exercises the same file primitives
    # used by the editor without mutating the user's workspace.
    with tempfile.TemporaryDirectory(prefix='qoder-core-probe-') as folder:
        path=Path(folder)/'probe.txt';path.write_text('before\n');original=path.read_bytes();path.write_text('after\n');path.write_bytes(original)
        results.append({'tool':'patch_rollback','passed':path.read_bytes()==original})
    return results

def verify(cache):
    data=json.loads((cache/'inventory.json').read_text())
    for entry in data['files']:
        path=(cache/entry['path']).resolve()
        if not path.is_relative_to(cache.resolve()) or not path.is_file():raise ValueError('Missing or unsafe package '+entry['path'])
        if path.stat().st_size!=entry['bytes'] or sha256(path)!=entry['sha256']:raise ValueError('Package checksum mismatch '+entry['path'])
    print('Verified',len(data['files']),'downloaded files.',flush=True)
    return data

def run(*argv, **kwargs):
    print('Running:',argv[0],flush=True)
    subprocess.run([str(x) for x in argv],check=True,**kwargs)

def missing_packages():
    return [p for p, commands in COMMANDS.items() if any(not shutil.which(c) for c in commands)]

def apt_options(state):
    lists=state/'lists';(lists/'partial').mkdir(parents=True,exist_ok=True)
    return ['-o','Dir::Etc::sourcelist='+str(state/'sources.list'),'-o','Dir::Etc::sourceparts=-',
            '-o','Dir::State::lists='+str(lists),'-o','APT::Get::List-Cleanup=0']

def install_debs(cache, state):
    missing=missing_packages()
    if not missing:return
    state.mkdir(parents=True,exist_ok=True)
    repo=str((cache/'android/termux-debs').resolve())
    if any(c in repo for c in '\n\r[]'):raise ValueError('Invalid local package repository path.')
    from urllib.parse import quote
    (state/'sources.list').write_text('deb [trusted=yes] file:'+quote(repo,safe='/')+' ./\n')
    options=apt_options(state)
    run('apt-get',*options,'update')
    run('apt-get',*options,'--no-remove','install','-y',*missing)

def unzip(source, dest):
    dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source) as z:
        for info in z.infolist():
            p=Path(info.filename)
            if p.is_absolute() or '..' in p.parts or info.external_attr>>16&0o170000==0o120000:raise ValueError('Unsafe archive member.')
            target=dest/p
            if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as f,target.open('wb') as out:shutil.copyfileobj(f,out)
            if info.external_attr>>16&0o111:target.chmod(0o700)

def copy_tool(source, dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():shutil.copyfile(source,dest)
    elif sha256(source)!=sha256(dest):raise ValueError('Preserving a different existing tool: '+str(dest))
    return dest

def check_npm_bundle(project):
    lock=json.loads((project/'package-lock.json').read_text())
    for name,package in lock.get('packages',{}).items():
        if package.get('os') or package.get('cpu') or package.get('hasInstallScript') or package.get('optional'):
            raise ValueError('Language bundle contains a platform dependency: '+name)
    dependencies=lock['packages']['']['dependencies']
    if dependencies.get('typescript')!='5.9.3':raise ValueError('Use the portable TypeScript 5.9.3 bundle.')
    return dependencies

def provision(cache,target,args):
    tools=target/'tools';tools.mkdir(parents=True,exist_ok=True)
    config_path=target/'tools.json'
    config=json.loads(config_path.read_text()) if config_path.exists() else {'schema':1,'commands':{},'remote':{'enabled':False},'language_servers':{}}
    config['execution_platform']='android'
    commands=config.setdefault('commands',{})
    for name,file in [('apkeditor','APKEditor-1.4.9.jar'),('bundletool','bundletool-all-1.18.3.jar'),('smali','smali-3.0.10-fat.jar'),('baksmali','baksmali-3.0.10-fat.jar')]:
        if commands.get(name) or shutil.which(name):continue
        source=cache/'android'/('smali' if name in {'smali','baksmali'} else 'java')/file
        jar=copy_tool(source,tools/'jars'/file)
        version_arg='--version' if name in {'smali','baksmali'} else ('version' if name=='bundletool' else '-v')
        result=probe(['java','-jar',str(jar),version_arg],timeout=60,tool=name)
        if not result['passed']:raise ValueError('Tool version probe failed: '+name+' '+result.get('output',result.get('error','')))
        commands[name]=['java','-jar',str(jar)]
    servers=config.setdefault('language_servers',{})
    def available(language):
        c=servers.get(language)
        if not (c and isinstance(c,list) and shutil.which(c[0])):return False
        if language in {'typescript','javascript'}:
            legacy=tools/'npm'
            if any(str(legacy)+'/' in arg for arg in c):
                if not (legacy/'node_modules/typescript/lib/tsserver.js').is_file():return False
        return True
    for language in ('typescript','javascript'):
        existing=servers.get(language)
        if isinstance(existing,list) and existing and Path(existing[0]).name=='typescript-language-server' and Path(existing[0]).is_file():
            servers[language]=node_command(existing[0],*existing[1:])
    if any(not available(k) for k in ['typescript','javascript']):
        check_npm_bundle(cache/'android/npm-project')
        ts=shutil.which('typescript-language-server')
        if not ts:
            dest=tools/'npm-ts5.9.3-lsp6.0.2';dest.mkdir(exist_ok=True)
            for file in ['package.json','package-lock.json']:copy_tool(cache/'android/npm-project'/file,dest/file)
            run('npm','ci','--offline','--ignore-scripts','--prefix',dest,'--cache',cache/'android/npm-cache',timeout=300)
            ts=str(dest/'node_modules/.bin/typescript-language-server')
        for language in ['typescript','javascript']:
            if not available(language):servers[language]=node_command(ts,'--stdio')
    if not available('python'):
        if not shutil.which('pylsp'):
            packages=cache/'android/python-packages'
            run('python3','-m','pip','install','--user','--no-cache-dir','--no-index','--find-links',packages,'setuptools','wheel','setuptools-scm','vcs-versioning==2.6.0','packaging',timeout=300)
            run('python3','-m','pip','install','--user','--no-cache-dir','--no-index','--no-build-isolation','--find-links',packages,'python-lsp-server==1.15.0','pytest',timeout=600)
        servers['python']=[shutil.which('pylsp') or str(Path.home()/'.local/bin/pylsp')]
    for language in ['c','cpp']:
        if not available(language):servers[language]=['clangd']
    for name in ['pnpm','yarn']:
        if not shutil.which(name):
            archive=next((cache/'android/npm-project').glob(name+'-*.tgz'))
            run('npm','install','--global','--offline','--ignore-scripts','--cache',cache/'android/npm-cache',archive,timeout=300)
    existing_ast=commands.get('ast_grep',[])
    if (len(existing_ast)==1 and existing_ast[0].endswith('/target/release/sg') and
            Path(existing_ast[0]).resolve().is_relative_to(tools.resolve())):
        commands.pop('ast_grep',None)
    if not commands.get('ast_grep') and not shutil.which('ast-grep'):
        source=tools/'ast-source';unzip(cache/'android/sources/ast-grep-0.50.0.zip',source)
        with tarfile.open(cache/'android/sources/ast-grep-vendor-0.50.0.tar.gz') as t:
            # Python 3.14 in this bundle provides tarfile's data extraction filter.
            t.extractall(source,filter='data')
        project=source/'ast-grep-0.50.0'
        run('cargo','build','--release','--offline','--locked','--manifest-path',project/'Cargo.toml','-p','ast-grep','--bin','ast-grep',
            '--config','source.crates-io.replace-with="qoder-vendor"','--config','source.qoder-vendor.directory="'+str(source/'vendor')+'"',timeout=3600)
        exe=project/'target/release/ast-grep';run(exe,'--version',timeout=30);commands['ast_grep']=[str(exe)]
    if not shutil.which('rish'):run('sh',cache/'android/rish/setup-rish.sh',cache/'android/rish/rish_shizuku.dex',timeout=60)
    if not commands.get('frida') and not shutil.which('frida'):
        folder=tools/'frida';folder.mkdir(exist_ok=True)
        for name in ['frida-inject','frida-server','frida-gadget']:
            archives=list((cache/'android/frida').glob(name+'-17.23.3-android-arm64.*'))
            if not archives:continue
            archive=next(p for p in archives if p.suffix=='.xz')
            out=folder/(name+('.so' if name=='frida-gadget' else ''))
            if not out.exists():
                with lzma.open(archive) as f,out.open('wb') as dest:shutil.copyfileobj(f,dest)
                out.chmod(0o700)
        commands['frida']=[str(folder/'frida-inject')]
        config.setdefault('frida',{})['mode']='inject'
    if args.android_sdk:
        sdk=Path(config.get('android_sdk') or str(Path.home()/'Android/Sdk'))
        if not (sdk/'platforms/android-35/android.jar').exists():
            license_path=cache/'android/sdk/LICENSE-android-sdk.txt'
            print(license_path.read_text())
            if input('Accept the Android SDK license above? Type yes: ').strip().lower()!='yes':raise ValueError('SDK license was not accepted.')
            unpack=tools/'sdk-unpack';unzip(cache/'android/sdk/platform-35_r02.zip',unpack)
            sdk.mkdir(parents=True,exist_ok=True);(sdk/'platforms').mkdir(exist_ok=True)
            platform=next(p for p in unpack.iterdir() if (p/'android.jar').is_file())
            shutil.copytree(platform,sdk/'platforms/android-35',dirs_exist_ok=True)
            unzip(cache/'android/sdk/build-tools-35.zip',unpack/'build')
            build=next(p for p in (unpack/'build').iterdir() if (p/'source.properties').is_file())
            shutil.copytree(build,sdk/'build-tools/35.0.0',dirs_exist_ok=True)
            unzip(cache/'android/java/commandlinetools-linux-16111833_latest.zip',unpack/'commandline')
            shutil.copytree(unpack/'commandline/cmdline-tools',sdk/'cmdline-tools/latest',dirs_exist_ok=True)
            (sdk/'licenses').mkdir(exist_ok=True)
            accepted=hashlib.sha1(license_path.read_text().strip().encode()).hexdigest()
            license_file=sdk/'licenses/android-sdk-license'
            existing=license_file.read_text() if license_file.exists() else ''
            if accepted not in existing.splitlines():license_file.write_text(existing+'\n'+accepted+'\n')
        build=sdk/'build-tools/35.0.0'
        for name in ['aapt','aapt2','zipalign','apksigner','aidl']:
            native=shutil.which(name)
            if not native:raise ValueError('Android SDK native replacement missing: '+name)
            (build/name).unlink(missing_ok=True);(build/name).symlink_to(native)
        # Remove unsupported host executables rather than exposing x86 ELF to Android.
        for name in ['dexdump','split-select','bcc_compat','lld']:
            p=build/name
            if p.exists() and not shutil.which(name):p.chmod(0o600)
        platform_tools=sdk/'platform-tools';platform_tools.mkdir(exist_ok=True)
        if not (platform_tools/'adb').exists():(platform_tools/'adb').symlink_to(shutil.which('adb'))
        config['android_sdk']=str(sdk)
    if not commands.get('zap') and not shutil.which('zap.sh'):
        unzip(cache/'android/compatibility/zap/ZAP_2.17.0_Crossplatform.zip',tools/'zap')
        script=tools/'zap/ZAP_2.17.0/zap.sh';commands['zap']=['bash',str(script)]
        config.setdefault('zap',{})['mode']='headless'
    gradle=copy_tool(cache/'android/java/gradle-8.5-bin.zip',tools/'gradle/gradle-8.5-bin.zip')
    config.setdefault('gradle_distributions',{}).setdefault('8.5',str(gradle))
    # Gradle Wrapper computes this directory from its distribution URL.
    url='https://services.gradle.org/distributions/gradle-8.5-bin.zip'
    value=int.from_bytes(hashlib.md5(url.encode()).digest(),'big');key='';digits='0123456789abcdefghijklmnopqrstuvwxyz'
    while value:key=digits[value%36]+key;value//=36
    wrapper=Path(os.environ.get('GRADLE_USER_HOME',str(Path.home()/'.gradle')))/'wrapper/dists/gradle-8.5-bin'/key
    wrapper.mkdir(parents=True,exist_ok=True)
    copy_tool(gradle,wrapper/gradle.name)
    if not (wrapper/'gradle-8.5').exists():unzip(gradle,wrapper)
    (wrapper/(gradle.name+'.ok')).touch()
    temporary=config_path.with_suffix('.offline.tmp');temporary.write_text(json.dumps(config,indent=2)+'\n');temporary.chmod(0o600);os.replace(temporary,config_path)
    result={'download_checksums':'passed','native_provisioning':'finished','on_device':True,
        'pending':['Project-specific Gradle/npm dependencies and tests','ADB pairing or Shizuku authorization',
                   'Frida target access/root or Gadget configuration','mitmproxy Android build and local compatibility test','ZAP Android headless scan compatibility test'],
        'gradle':'8.5 distribution cached; each project must keep its original wrapper version',
        'mitmproxy':'source candidates downloaded; not installed or claimed compatible'}
    result['core_probes']=core_probes(target,config)
    result['core_probe_failures']=[p for p in result['core_probes'] if not p.get('passed')]
    result['state']='offline-ready' if not result['core_probe_failures'] else 'blocked'
    (target/'offline-tools-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if result['core_probe_failures']:
        raise ValueError('Core tool probes failed; the companion stamp was not promoted to offline-ready.')
    write_stamp(target,{'schema':1,'companion_build':companion_manifest(cache,getattr(args,'companion',None))['build'],
                        'apk_build':companion_manifest(cache,getattr(args,'companion',None)).get('apk_build'),'state':'offline-ready',
                        'bundle_sha256':getattr(args,'bundle_sha256',None),
                        'core_probe_count':len(result['core_probes']),'installed_at':int(time.time()),
                        'pending':result['pending']})
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--check',action='store_true');p.add_argument('--android-sdk',action='store_true');p.add_argument('--bundle-sha256',default=None);p.add_argument('--companion',type=Path);a=p.parse_args()
    cache=a.cache.resolve();verify(cache)
    if a.check:return
    if os.uname().machine!='aarch64' or not os.environ.get('PREFIX','').startswith('/data/data/com.termux/'):
        raise ValueError('Install inside official ARM64 Termux. This installer does not install apps on a connected phone.')
    os.environ['TMPDIR']=str(Path(os.environ['PREFIX'])/'tmp')
    os.environ.setdefault('ANDROID_DATA','/data');os.environ.setdefault('ANDROID_ROOT','/system')
    target=Path.home()/'qoder-selfhost'
    # A first full install may create qoder-selfhost. When it already exists,
    # install.py updates only application files and preserves models/sessions.
    companion=(a.companion or cache/'android/qoder-companion').resolve()
    a.companion=companion
    package=companion_manifest(cache,companion);refuse_downgrade(target,package['build'])
    # Check the explicit companion before any package or application mutation.
    run('python3',companion/'install.py','--check',timeout=300)
    install_debs(cache,Path.home()/'.cache/qoder-offline-apt')
    run('python3',companion/'install.py','--update','--no-model','--offline','--defer-stamp',timeout=300)
    provision(cache,target,a)

if __name__=='__main__':main()
