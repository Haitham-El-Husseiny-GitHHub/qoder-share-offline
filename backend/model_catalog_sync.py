"""Refresh OpenCode Zen from its public API, published endpoint table and model metadata."""
import json,re,html,subprocess,time,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'runtime/model-catalog.json'
LOCK=threading.Lock()
def fetch(url):
 p=subprocess.run(['curl','--fail','--silent','--show-error','--location','--max-time','15','--user-agent','Mozilla/5.0',url],capture_output=True,text=True,timeout=20)
 if p.returncode:raise ValueError('Catalog fetch failed: '+url)
 return p.stdout
def published_rows(text):
 rows=[]
 for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',text,re.S):
  cells=[html.unescape(re.sub('<[^>]+>','',c)).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)]
  if len(cells)>=4 and cells[2].startswith('https://opencode.ai/zen/'):
   rows.append({'id':cells[1],'name':cells[0],'endpoint':cells[2],'npm':cells[3]})
 return rows
def refresh(call,force=False):
 with LOCK:
  cached={}
  try:cached=json.loads(CACHE.read_text())
  except (OSError,ValueError):pass
  if cached and not force and time.time()-cached.get('updated_at',0)<3600:return cached
  try:
   served=json.loads(fetch('https://opencode.ai/zen/v1/models'))['data']
   docs=published_rows(fetch('https://docs.opencode.ai/docs/zen/'))
   registry_data=json.loads(fetch('https://models.dev/api.json'))
   registry=registry_data['opencode']['models']
   go_docs=published_rows(fetch('https://docs.opencode.ai/docs/go/'))
   go_registry=registry_data.get('opencode-go',{}).get('models',{})
   live={m['id'] for m in served};documented={m['id'] for m in docs}
   rows={m['id']:{'id':m['id'],'name':registry.get(m['id'],{}).get('name',m['id']),'served':True,'documented':False} for m in served}
   for m in docs:rows[m['id']]={**rows.get(m['id'],{}),**m,'served':m['id'] in live,'documented':True}
   definitions={}
   for mid,row in rows.items():
    meta=registry.get(mid,{})
    definition={k:meta[k] for k in ('id','name','family','release_date','attachment','reasoning','temperature','tool_call','cost','limit','modalities','provider') if k in meta}
    definition.setdefault('name',row['name'])
    definition.setdefault('limit',{'context':32768,'output':8192})
    if row.get('npm','').startswith('@ai-sdk/'):
     definition['provider']={'npm':row['npm'],'api':'https://opencode.ai/zen/v1'}
    row['cost']=meta.get('cost')
    row['coding_compatible']=not mid.startswith('jev-')
    if not mid.startswith('jev-'):definitions[mid]=definition
   # Preserve existing settings and credentials; register supported endpoint definitions.
   call('/config','PATCH',{'provider':{'opencode':{'models':definitions}}})
   go_definitions={}
   for row in go_docs:
    meta=go_registry.get(row['id'],{})
    definition={k:meta[k] for k in ('id','name','family','release_date','attachment','reasoning','temperature','tool_call','cost','limit','modalities') if k in meta}
    definition.setdefault('name',row['name']);definition.setdefault('limit',{'context':32768,'output':8192})
    definition['provider']={'npm':row['npm'],'api':'https://opencode.ai/zen/go/v1'}
    go_definitions[row['id']]=definition
   call('/config','PATCH',{'provider':{'opencode-go':{'models':go_definitions}}})
   data={'go_models':go_docs,'go_documented_count':len(go_docs),'updated_at':time.time(),'public_count':len(live),'documented_count':len(documented),'models':list(rows.values()),'source':'https://opencode.ai/zen/v1/models','documentation':'https://docs.opencode.ai/docs/zen/'}
   CACHE.parent.mkdir(parents=True,exist_ok=True)
   tmp=CACHE.with_suffix('.tmp');tmp.write_text(json.dumps(data));tmp.replace(CACHE)
   return data
  except Exception as exc:
   if cached:return {**cached,'refresh_error':str(exc)}
   raise
def catalog(runtime,cache):
 connected=runtime.get('connected',[])
 providers=[]
 for provider in runtime.get('all',[]):
  records=[{'id':m['id'],'name':m.get('name',m['id']),'available':provider['id'] in connected,'reason':'' if provider['id'] in connected else 'Connect this provider API key.'} for m in provider.get('models',{}).values()]
  if provider['id']=='opencode':
   native={m['id']:m for m in records}
   for row in cache.get('models',[]):
    mid=row['id'];known=native.get(mid)
    reason='Decision API; requires structured questions.' if not row.get('coding_compatible',True) else '' if known else 'Connect OpenCode Zen API key.' if row.get('served') else 'Published on website; absent from current public API.'
    native[mid]={**row,'available':bool(known and row.get('coding_compatible',True)),'reason':reason}
   records=list(native.values())
  if provider['id']=='opencode-go':
   native={m['id']:m for m in records}
   for row in cache.get('go_models',[]):
    known=native.get(row['id'])
    native[row['id']]={**row,'available':bool(known and known.get('available')),'reason':'' if known and known.get('available') else 'OpenCode Go provider authentication applies.'}
   records=list(native.values())
  providers.append({'id':provider['id'],'name':provider.get('name',provider['id']),'connected':provider['id'] in connected,'models':sorted(records,key=lambda m:(not m.get('available'),m['name'].lower()))})
 return {'connected':connected,'providers':providers,'catalog':{k:v for k,v in cache.items() if k not in {'models','go_models'}}}
