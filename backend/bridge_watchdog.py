"""Keep the shared bridge ready and recover Shizuku through already-authorized local ADB."""
import json,os,re,subprocess,time,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def command(argv,timeout=8):
 try:
  p=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
  return p.returncode,(p.stdout or '')+(p.stderr or '')
 except (OSError,subprocess.TimeoutExpired) as exc:return 1,str(exc)
def local_adb(output):
 return [line.split()[0] for line in output.splitlines() if line.split()[1:2]==['device'] and re.fullmatch(r'127\.0\.0\.1:\d+',line.split()[0])]
def restart_shizuku():
 code,listed=command(['adb','devices'])
 if code:return {'attempted':False,'reason':'ADB unavailable.'}
 peers=local_adb(listed)
 if not peers:return {'attempted':False,'reason':'No authorized loopback ADB connection; Shizuku must be started by its permitted Android startup method.'}
 serial=peers[0]
 code,output=command(['adb','-s',serial,'shell','pm','path','moe.shizuku.privileged.api'])
 apk=next((line[8:].strip() for line in output.splitlines() if line.startswith('package:') and line.endswith('/base.apk')),'')
 if code or not re.fullmatch(r'/data/app/[^\s;&|<>]+/base\.apk',apk):return {'attempted':False,'reason':'Installed Shizuku APK path unavailable.'}
 starter=str(Path(apk).parent/'lib/arm64/libshizuku.so')
 code,output=command(['adb','-s',serial,'shell',starter,'--apk='+apk],timeout=15)
 return {'attempted':True,'exit_code':code,'output':output[-1000:]}
def check():
 import bridge
 state=bridge.status()
 result={'checked_at':time.time(),'termux':state['termux'],'rish_connected':state['rish_connected'],'access_level':state['access_level'],'automatic':True}
 if not state['rish_connected']:
  result['recovery']=restart_shizuku()
  if result['recovery']['attempted']:
   bridge._cached=None;state=bridge.status();result.update(rish_connected=state['rish_connected'],access_level=state['access_level'])
 folder=ROOT/'runtime';folder.mkdir(exist_ok=True)
 temporary=folder/('bridge-recovery-'+str(os.getpid())+'.tmp');temporary.write_text(json.dumps(result));temporary.replace(folder/'bridge-recovery.json')
 return result
def refresh_catalogs_once():
 import qoder_cloud,model_catalog_sync,opencode_bridge
 results={}
 for name,refresh in [('qoder',lambda:qoder_cloud.catalog(True)),('opencode',lambda:model_catalog_sync.refresh(opencode_bridge.call,True))]:
  try:
   data=refresh();results[name]={'updated_at':data.get('updated_at'),'error':data.get('refresh_error')}
  except Exception as exc:results[name]={'error':str(exc)}
 return results
def catalog_monitor():
 while True:
  started=time.monotonic()
  refresh_catalogs_once()
  time.sleep(max(1,60-(time.monotonic()-started)))
if __name__=='__main__':
 if '--once' not in sys.argv:threading.Thread(target=catalog_monitor,daemon=True).start()
 while True:
  try:result=check()
  except Exception as exc:result={'error':str(exc)}
  if '--once' in sys.argv:print(json.dumps(result));break
  time.sleep(20)
