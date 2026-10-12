"""Unfiltered advertised Qoder catalog and jobs using the phone's existing Qoder login."""
import json,re,html,os,subprocess,threading,time,uuid
from pathlib import Path
from model_catalog_sync import fetch
HOME=Path('/data/data/com.termux/files/home');ROOT=Path(__file__).resolve().parent
FOLDER=ROOT/'runtime/cloud-jobs';GUARD=threading.Lock();ACTIVE={}
PUBLISHED=['Auto','Ultimate','Performance','Efficient','Sonus','Cantus','Qwen3.8-Max','Qwen3.8-Flash','Qwen3.7-Max','Qwen3.7-Plus','DeepSeek-V4-Pro','DeepSeek-V4-Flash','GLM-5.3','GLM-5.3-Flash','GLM-5.2','Kimi-K3','Kimi-K2.8-Preview','Kimi-K2.7-Code','MiniMax-M3']
def env():
 return {**os.environ,'PREFIX':'/data/data/com.termux/files/usr','TMPDIR':'/data/data/com.termux/files/usr/tmp','TERMUX_VERSION':os.environ.get('TERMUX_VERSION','remote-session')}
def catalog(force=False):
 cache=ROOT/'runtime/qoder-published-models.json'
 try:
  saved=json.loads(cache.read_text())
  if not force and time.time()-saved['updated_at']<60:return saved
 except (OSError,ValueError,KeyError):saved=None
 names=set(PUBLISHED)|{m['name'] for m in (saved or {}).get('models',[])};sources=[];rates={}
 for url in ('https://docs.qoder.com/qoder/model-selector','https://docs.qoder.com/cli/model','https://docs.qoder.com/user-guide/chat/model-tier-selector'):
  try:
   body=fetch(url);sources.append(url)
   for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',body,re.S):
    cells=re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)
    if not cells:continue
    name=html.unescape(re.sub('<[^>]+>','',cells[0])).strip()
    if re.match(r'^(Qwen|Kimi|GLM|DeepSeek|MiniMax)[A-Za-z0-9.-]+$',name):names.add(name)
    if url.endswith('/cli/model') and len(cells)>1:
     rate=html.unescape(re.sub('<[^>]+>','',cells[-1])).strip()
     match=re.search(r'([0-9]+(?:\.[0-9]+)?)\s*[x×]',rate)
     if match and (name in {'Auto','Ultimate','Performance','Efficient'} or name in names):rates[name]=float(match[1])
  except (ValueError,subprocess.TimeoutExpired):continue
 names.discard('DeepSeek-Flash')
 data={'updated_at':time.time(),'sources':sources,'models':[{'id':name.lower() if name in {'Auto','Ultimate','Performance','Efficient'} else name,'name':name,**({'cli_multiplier':rates[name]} if name in rates else {})} for name in sorted(names)],'unfiltered':True}
 cache.parent.mkdir(exist_ok=True);cache.write_text(json.dumps(data))
 return data
def save(data):
 FOLDER.mkdir(exist_ok=True);p=FOLDER/(data['id']+'.json');tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(data));tmp.replace(p)
def snapshot(jid):
 if not re.fullmatch('[a-f0-9]{32}',jid):raise ValueError('Invalid job ID.')
 return json.loads((FOLDER/(jid+'.json')).read_text())
def worker(data):
 from coding_runner import redact
 import fcntl,hashlib,source_lookup
 source_lock=None
 try:
  lockdir=ROOT/'runtime/source-locks';lockdir.mkdir(parents=True,exist_ok=True)
  canonical=source_lookup.project_for_path(data['directory'])
  source_lock=(lockdir/(hashlib.sha256(str(canonical).encode()).hexdigest()+'.lock')).open('a')
  fcntl.flock(source_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if data.get('cancel_requested'):data['status']='stopped';return
  argv=['qodercli','-p','--no-session-persistence','--model',data['model'],'--cwd',data['directory'],'--output-format','text',data['objective']]
  with (FOLDER/(data['id']+'.output')).open('w') as output:
   proc=subprocess.Popen(argv,stdout=output,stderr=subprocess.STDOUT,env=env(),start_new_session=True)
   with GUARD:ACTIVE[data['id']]={'process':proc,'record':data}
   data['status']='running';save(data)
   while proc.poll() is None:
    data['output']=redact((FOLDER/(data['id']+'.output')).read_text(errors='replace')[-30000:]);save(data);time.sleep(1)
   data['exit_code']=proc.returncode;data['status']='completed' if proc.returncode==0 else 'stopped' if data.get('cancel_requested') else 'failed'
   data['output']=redact((FOLDER/(data['id']+'.output')).read_text(errors='replace')[-30000:])
 except Exception as exc:data.update(status='failed',error=str(exc))
 finally:
  with GUARD:ACTIVE.pop(data['id'],None)
  if source_lock is not None:source_lock.close()
  data['finished_at']=time.time();save(data)
def run(data):
 import source_lookup
 directory=source_lookup.project_for_path(data.get('directory') or HOME/'coding-workspace')
 objective=str(data.get('objective','')).strip()
 if not objective:raise ValueError('Enter a coding task.')
 model=str(data.get('model',''))
 if model not in {m['id'] for m in catalog()['models']}:raise ValueError('Select a published Qoder model.')
 report=source_lookup.acquire(objective,directory,config={'offline':True})
 if report.get('root'):directory=Path(report['root'])
 elif source_lookup.app_token(objective):raise ValueError(report.get('chosen',{}).get('reason','Source not found.'))
 record={'id':uuid.uuid4().hex,'model':model,'directory':str(directory),'objective':objective,'status':'starting','started_at':time.time(),'output':''}
 with GUARD:
  if ACTIVE:raise ValueError('A Qoder cloud task is running. Stop it or wait for completion.')
  ACTIVE[record['id']]={'process':None,'record':record}
 try:
  save(record);threading.Thread(target=worker,args=(record,),daemon=True).start()
 except Exception:
  with GUARD:ACTIVE.pop(record['id'],None)
  raise
 return record
def stop(jid):
 import signal
 with GUARD:
  active=ACTIVE.get(jid)
  if active:
   data=active['record'];data['cancel_requested']=True;save(data)
   proc=active['process']
   if proc:os.killpg(proc.pid,signal.SIGTERM)
 return {'stopping':bool(active)}
