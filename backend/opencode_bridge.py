"""Same-origin OpenCode API adapter; server credentials never reach the interface."""
import base64,json,re,urllib.request,urllib.parse,urllib.error
from pathlib import Path
HOME=Path('/data/data/com.termux/files/home')
def call(path,method='GET',body=None,directory=None):
 secret=(HOME/'opencode-runtime/server.password').read_text().strip()
 suffix=('&' if '?' in path else '?')+urllib.parse.urlencode({'directory':directory}) if directory else ''
 req=urllib.request.Request('http://127.0.0.1:4096'+path+suffix,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Basic '+base64.b64encode(('opencode:'+secret).encode()).decode(),'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=45) as response:
   raw=response.read(8*1024*1024)
   return json.loads(raw) if raw else {'accepted':True}
 except urllib.error.HTTPError as exc:
  raise ValueError('OpenCode API returned HTTP '+str(exc.code)+': '+exc.read(2000).decode(errors='replace'))
def get(query):
 path=query.get('path',['/global/health'])[0]
 if not (path in {'/global/health','/provider','/session/status','/session','/mcp'} or re.fullmatch(r'/session/[a-zA-Z0-9_-]+(?:/message|/diff)?',path)):raise ValueError('Unknown OpenCode read route.')
 result=call(path,directory=query.get('directory',[''])[0])
 if path=='/provider':
  connected=result.get('connected',[])
  return {'connected':connected,'providers':[{'id':p['id'],'name':p.get('name',p['id']),'models':[{'id':m['id'],'name':m.get('name',m['id'])} for m in p.get('models',{}).values()]} for p in result.get('all',[]) if p['id'] in connected]}
 return result
def post(data):
 action=data.get('action');directory=str(data.get('directory') or HOME/'coding-workspace')
 import source_lookup
 directory=source_lookup.project_for_path(directory)
 if action=='discover':
  report=source_lookup.acquire(data.get('objective',''),directory,config={'offline':True})
  return {'directory':report.get('root'),'discovery':source_lookup.public(report)}
 if action=='run':
  text=str(data.get('objective','')).strip()
  if not text:raise ValueError('Enter a task.')
  report=source_lookup.acquire(text,directory,config={'offline':True})
  if report.get('root'):directory=Path(report['root'])
  elif source_lookup.app_token(text):raise ValueError(report.get('chosen',{}).get('reason','Source not found.')+' '+json.dumps(report.get('places',[])[:1]))
  session=data.get('session')
  if not session:session=call('/session','POST',{'title':text[:80]},str(directory))['id']
  if not re.fullmatch(r'[a-zA-Z0-9_-]+',session):raise ValueError('Invalid session.')
  model=data.get('model','').split('/',1)
  if len(model)!=2:raise ValueError('Select a provider/model.')
  payload={'parts':[{'type':'text','text':text}],'model':{'providerID':model[0],'modelID':model[1]},'agent':data.get('agent','build')}
  call('/session/'+session+'/prompt_async','POST',payload,str(directory))
  return {'session':session,'directory':str(directory),'accepted':True}
 if action=='abort':
  session=data.get('session','')
  if not re.fullmatch(r'[a-zA-Z0-9_-]+',session):raise ValueError('Invalid session.')
  return call('/session/'+session+'/abort','POST',{},str(directory))
 if action=='connect':
  provider=data.get('provider','').strip()
  if not re.fullmatch(r'[a-zA-Z0-9_-]+',provider):raise ValueError('Invalid provider ID.')
  key=data.get('key','').strip()
  if not key:raise ValueError('Enter the provider API key.')
  base=data.get('baseURL','').strip();model=data.get('modelID','').strip()
  if base:
   if not base.startswith(('https://','http://127.0.0.1:')) or not model:raise ValueError('Enter an HTTPS API base URL and model ID.')
   call('/config','PATCH',{'provider':{provider:{'npm':'@ai-sdk/openai-compatible','name':provider,'options':{'baseURL':base},'models':{model:{'name':model}}}}})
  call('/auth/'+provider,'PUT',{'type':'api','key':key})
  return {'connected':provider}
 raise ValueError('Unknown OpenCode action.')
