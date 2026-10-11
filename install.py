#!/usr/bin/env python3
"""Install the portable offline companion in official Termux."""
import argparse,fcntl,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from fetch_model import fetch
from setup_tools import ensure_packages,install_tools
BASE=Path(__file__).resolve().parent
PREFIX=Path('/data/data/com.termux/files/usr')
HOME=Path('/data/data/com.termux/files/home')
STAMP_NAME='.qoder-companion-stamp.json'

def manifest():
 manifest=json.loads((BASE/'package.json').read_text())
 if not isinstance(manifest.get('build'),int) or manifest['build']<1:
  raise ValueError('Companion package has no valid build number.')
 return manifest

def read_stamp(target):
 stamp=target/STAMP_NAME
 if not stamp.exists():return None
 try:data=json.loads(stamp.read_text())
 except (OSError,ValueError) as exc:raise ValueError('Companion stamp is unreadable; repair the installation before updating.') from exc
 if not isinstance(data,dict) or not isinstance(data.get('companion_build'),int):
  raise ValueError('Companion stamp is invalid; repair the installation before updating.')
 return data

def refuse_downgrade(target,incoming):
 current=read_stamp(target) if target.exists() else None
 if current and current['companion_build']>incoming:
  raise ValueError('Refusing companion downgrade from build %d to %d.'%(current['companion_build'],incoming))

def write_stamp(target,data):
 stamp=target/STAMP_NAME;temporary=stamp.with_suffix('.tmp')
 temporary.write_text(json.dumps(data,indent=2)+'\n');temporary.chmod(0o600);os.replace(temporary,stamp)

def verify():
 manifest=json.loads((BASE/'package.json').read_text())
 for name,expected in manifest['sha256'].items():
  p=(BASE/name).resolve()
  if not p.is_relative_to(BASE) or not p.is_file():raise ValueError('Missing or unsafe package file: '+name)
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
  if h.hexdigest()!=expected:raise ValueError('Package checksum mismatch: '+name)
 print('Package checksums verified.')
def run(*args):subprocess.run(args,check=True)
def offline_run(*args):
 if args and str(args[0]) in {'pkg','apt','apt-get','npm','cargo','sdkmanager'}:
  raise ValueError('Offline mode refused remote package/bootstrap command: '+str(args[0]))
 run(*args)
def install(args):
 verify()
 package=manifest();incoming_build=package['build']
 if args.check:return
 if not PREFIX.is_dir() or Path.home()!=HOME:raise ValueError('Run this installer inside official Termux (com.termux).')
 target=HOME/'qoder-selfhost'
 if target.exists() and not args.update:raise ValueError('Backend already exists. Use --update to replace only application files while retaining models and sessions.')
 refuse_downgrade(target,incoming_build)
 if os.uname().machine!='aarch64':raise ValueError('This release supports ARM64 Android phones.')
 if (target/'sessions').is_dir():
  for p in (target/'sessions').glob('*.json'):
   if json.loads(p.read_text()).get('current',{}).get('status')=='running':raise ValueError('Stop active coding jobs before updating.')
 runner=offline_run if getattr(args,'offline',False) else run
 ensure_packages(['python','git','ripgrep','llama-cpp','termux-services'],runner)
 if args.apk_tools:ensure_packages(['openjdk-21','apktool','jadx','aapt2','apksigner','aapt'],runner)
 help_text=subprocess.run(['llama-server','--help'],capture_output=True,text=True,check=True).stdout
 for flag in ['--api-key-file','--parallel','--reasoning-budget','--chat-template-kwargs','--cache-type-k','--no-webui']:
  if flag not in help_text:raise ValueError('Installed llama-cpp lacks '+flag+'. Update llama-cpp before continuing.')
 update_lock=None
 if target.exists() and args.update:
  lockpath=target/'runtime/server.lock';lockpath.parent.mkdir(parents=True,exist_ok=True);update_lock=lockpath.open('a')
  try:fcntl.flock(update_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise ValueError('A coding worker or model switch is active; stop it before updating.')
  service=PREFIX/'var/service/qoder-selfhost'
  if service.exists():run('sv','down',str(service))
 # Remove readiness only after all update guards have succeeded.
 if getattr(args,'defer_stamp',False):
  (target/STAMP_NAME).unlink(missing_ok=True)
 target.mkdir(mode=0o700,exist_ok=True)
 for p in (BASE/'backend').iterdir():
  if p.is_file():shutil.copyfile(p,target/p.name)
  elif p.is_dir() and p.name!='__pycache__':shutil.copytree(p,target/p.name,dirs_exist_ok=True)
 install_tools(target,getattr(args,'tools',[]),runner,PREFIX,getattr(args,'android_sdk',False))
 (target/'runtime').mkdir(mode=0o700,exist_ok=True)
 (target/'models').mkdir(mode=0o700,exist_ok=True)
 for name in ['fetch_model.py','models.json','setup-rish.sh','setup_tools.py','tools.lock.json']:
  shutil.copyfile(BASE/name,target/name)
 # Each recipient gets a new private inference credential on first startup.
 import importlib.util
 spec=importlib.util.spec_from_file_location('_qoder_install_runtime',target/'runtime_config.py');runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime);runtime.ensure()
 (HOME/'coding-workspace').mkdir(exist_ok=True)
 if not args.no_model:fetch(json.loads((BASE/'models.json').read_text())[0],target/'models')
 props=HOME/'.termux/termux.properties';props.parent.mkdir(exist_ok=True)
 content=props.read_text() if props.exists() else ''
 import re
 content=re.sub(r'^\s*allow-external-apps\s*=.*$', 'allow-external-apps = true',content,flags=re.M)
 if not re.search(r'^allow-external-apps = true$',content,re.M):content+='\nallow-external-apps = true\n'
 props.write_text(content)
 if shutil.which('termux-reload-settings'):run('termux-reload-settings')
 service=PREFIX/'var/service/qoder-selfhost';service.mkdir(parents=True,exist_ok=True)
 (service/'run').write_text('#!'+str(PREFIX/'bin/sh')+'\nexec '+str(PREFIX/'bin/python3')+' '+str(target/'server.py')+'\n');os.chmod(service/'run',0o700)
 os.chmod(target/'bridge-start.sh',0o700)
 boot=HOME/'.termux/boot/08-qoder-selfhost';boot.parent.mkdir(parents=True,exist_ok=True);boot.write_text('#!'+str(PREFIX/'bin/sh')+'\nexec '+str(target/'bridge-start.sh')+'\n');os.chmod(boot,0o700)
 (HOME/'bin').mkdir(exist_ok=True);cli=HOME/'bin/qoder-local-code';cli.write_text('#!'+str(PREFIX/'bin/sh')+'\nexec '+str(PREFIX/'bin/python3')+' '+str(target/'local_cli.py')+' "$@"\n');os.chmod(cli,0o700)
 if update_lock:update_lock.close()
 run(str(target/'bridge-start.sh'))
 if not getattr(args,'defer_stamp',False):
  write_stamp(target,{'schema':1,'companion_build':incoming_build,'apk_build':package.get('apk_build'),
                      'state':'companion-installed','package_kind':package.get('kind'),
                      'installed_at':int(time.time())})
  print('Companion build %d installed. Continue using the signed build 79 APK and its existing task box. Follow README for tool setup and Shizuku/Rish; model startup can take up to two minutes.'%incoming_build)
 else:
  print('Companion files installed; readiness stamp is deferred until offline probes pass.')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--check',action='store_true');a.add_argument('--update',action='store_true');a.add_argument('--no-model',action='store_true');a.add_argument('--offline',action='store_true');a.add_argument('--defer-stamp',action='store_true');a.add_argument('--apk-tools',action='store_true');a.add_argument('--tools',nargs='*',choices=['all','web','android','native','structural','lsp','remote'],default=[]);a.add_argument('--android-sdk',action='store_true');args=a.parse_args()
 try:install(args)
 except (OSError,ValueError,subprocess.CalledProcessError) as exc:print('Setup stopped:',exc,file=sys.stderr);sys.exit(1)
