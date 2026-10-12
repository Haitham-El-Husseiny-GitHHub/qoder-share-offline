"""Refresh OpenCode Zen from its public API, published endpoint table and model metadata."""
import json,re,html,subprocess,time,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'runtime/model-catalog.json'
LOCK=threading.Lock()
def model_developer(model):
 """Developer grouping inside Go; not a separate API credential/provider route."""
 name=(model.get('id','')+' '+model.get('family','')+' '+model.get('name','')).lower()
 for prefixes,label in [(('claude','anthropic'),'Anthropic'),(('deepseek',),'DeepSeek'),(('gemini','gemma'),'Google'),(('glm','z-ai','zai'),'Z.AI'),(('gpt','o1','o3','o4'),'OpenAI'),(('grok',),'xAI'),(('kimi',),'Moonshot AI'),(('longcat',),'Meituan'),(('mimo',),'Xiaomi'),(('minimax',),'MiniMax'),(('muse','llama'),'Meta'),(('qwen',),'Alibaba'),(('step',),'StepFun'),(('hy3','hy4','hunyuan'),'Tencent')]:
  if any(name.startswith(prefix) for prefix in prefixes):return label
 return 'OpenCode'
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
def published_prices(text):
 """Read the first Go price table (Go, rather than Go Plus allowances)."""
 prices={}
 for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',text,re.S):
  cells=[html.unescape(re.sub('<[^>]+>','',c)).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)]
  if len(cells)<6:continue
  def amount(value):
   if value.lower()=='free':return 0.0
   match=re.fullmatch(r'\$([0-9]+(?:\.[0-9]+)?)',value)
   return float(match.group(1)) if match else None
  cost={'input':amount(cells[1]),'output':amount(cells[2])}
  if None in cost.values():continue
  label=re.sub(r'\s+',' ',cells[0]).strip()
  prices.setdefault(label,cost)
 return prices
def refresh(call,force=False):
 with LOCK:
  cached={}
  try:cached=json.loads(CACHE.read_text())
  except (OSError,ValueError):pass
  if cached and not force and time.time()-cached.get('updated_at',0)<60:return cached
  try:
   served=json.loads(fetch('https://opencode.ai/zen/v1/models'))['data']
   docs=published_rows(fetch('https://docs.opencode.ai/docs/zen/'))
   registry_data=json.loads(fetch('https://models.dev/api.json'))
   registry=registry_data['opencode']['models']
   go_html=fetch('https://opencode.ai/docs/go/')
   go_docs=published_rows(go_html)
   go_prices=published_prices(go_html)
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
    row['cost']=go_prices.get(row['name'],meta.get('cost'))
    peak=go_prices.get(row['name']+' (Peak)')
    offpeak=go_prices.get(row['name']+' (Off-Peak)')
    if peak and offpeak and row['id'].startswith('deepseek-'):
     row['pricing_schedule']='deepseek';row['pricing']={'peak':peak,'offpeak':offpeak}
    definition={k:meta[k] for k in ('id','name','family','release_date','attachment','reasoning','temperature','tool_call','cost','limit','modalities') if k in meta}
    definition.setdefault('name',row['name']);definition.setdefault('limit',{'context':32768,'output':8192})
    definition['provider']={'npm':row['npm'],'api':'https://opencode.ai/zen/go/v1'}
    go_definitions[row['id']]=definition
   call('/config','PATCH',{'provider':{'opencode-go':{'models':go_definitions}}})
   data={'provider_registry':registry_data,'go_models':go_docs,'go_documented_count':len(go_docs),'updated_at':time.time(),'public_count':len(live),'documented_count':len(documented),'models':list(rows.values()),'source':'https://opencode.ai/zen/v1/models','documentation':'https://docs.opencode.ai/docs/zen/'}
   CACHE.parent.mkdir(parents=True,exist_ok=True)
   tmp=CACHE.with_suffix('.tmp');tmp.write_text(json.dumps(data));tmp.replace(CACHE)
   return data
  except Exception as exc:
   if cached:return {**cached,'refresh_error':str(exc)}
   raise
def catalog(runtime,cache):
 connected=runtime.get('connected',[])
 providers=[]
 merged={p['id']:p for p in runtime.get('all',[])}
 for pid,entry in cache.get('provider_registry',{}).items():
  prior=merged.get(pid,{'id':pid,'name':entry.get('name',pid),'models':{}})
  merged[pid]={**prior,'models':{**entry.get('models',{}),**prior.get('models',{})}}
 for provider in merged.values():
  records=[{'id':m['id'],'name':m.get('name',m['id']),'cost':m.get('cost'),'available':provider['id'] in connected,'reason':'' if provider['id'] in connected else 'Connect this provider API key.'} for m in provider.get('models',{}).values()]
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
  if provider['id']=='opencode-go':
   records=[{**m,'developer':model_developer(m),'credential_provider':'opencode-go'} for m in records]
  providers.append({'id':provider['id'],'name':provider.get('name',provider['id']),'connected':provider['id'] in connected,'models':sorted(records,key=lambda m:(m['name'].casefold(),m['id']))})
 return {'connected':connected,'providers':sorted(providers,key=lambda p:(p['name'].casefold(),p['id'])),'catalog':{k:v for k,v in cache.items() if k not in {'models','go_models','provider_registry'}}}
