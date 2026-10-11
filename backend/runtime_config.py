from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'runtime'
KEY_FILE=RUNTIME/'inference.key'
PORT=18082
UPSTREAM=f'http://127.0.0.1:{PORT}'
MODELS={
 'phone-code':('Qwen2.5-Coder-3B-Abliterated',ROOT/'models'/'Coder-Qwen2.5-3B-abliterated.gguf'),
 'omni-code':('OmniCoder-9B-Abliterated',ROOT/'models'/'OmniCoder-9B-Abliterated-Q4_K_M.gguf'),
 'phone-chat':('Llama3-8B-Abliterated-Q4_K_M',Path('/sdcard/Download/000-SuperClaw-Models/Chat-Llama3-8B-Abliterated-Q4_K_M.gguf')),
}
CODING_ROUTES={'coding':'phone-code','omni':'omni-code'}
EXPECTED={'phone-code':1929903488,'omni-code':5629109600}
LABELS={'phone-code':'Qwen Coder 3B','omni-code':'OmniCoder 9B'}
import json
EXTRA_MODELS=json.loads((ROOT/'extra_models.json').read_text())
for entry in EXTRA_MODELS:
    route=entry['route']
    MODELS[route]=(entry['id'],ROOT/'models'/entry['file'])
    CODING_ROUTES[entry['mode']]=route
    EXPECTED[route]=entry['size'];LABELS[route]=entry['name']
def context_plan(route):
    from context_policy import plan,reclaimable_runtime
    return plan(MODELS[route][1],reclaim_bytes=reclaimable_runtime(RUNTIME/'server.json'))
def model_catalog():
    import json
    try: total=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemTotal:')))*1024
    except (OSError,StopIteration):total=0
    try: state=json.loads((RUNTIME/'server.json').read_text())
    except (OSError,ValueError):state={}
    result=[]
    for mode,route in CODING_ROUTES.items():
        model,path=MODELS[route];size=EXPECTED[route]
        try:
            actual=path.stat().st_size
            with path.open('rb') as f:installed=actual==size and f.read(4)==b'GGUF'
        except OSError:actual=0;installed=False
        partial=max((min(p.stat().st_size,p.stat().st_blocks*512,size-1) for p in path.parent.glob(path.name+'.*.partial')),default=0)
        try:partial=max(0,min(size-1,int(json.loads(path.with_name(path.name+'.ranges.json').read_text())['bytes'])))
        except (OSError,ValueError,KeyError,TypeError):pass
        memory_ok=not total or size+2_000_000_000<total
        reason='Ready to load' if installed else 'Download incomplete'
        if installed and route=='omni-code':reason+=' · slower CPU model'
        if not memory_ok:reason=('' if installed else 'Download incomplete; ')+'Insufficient phone RAM; requires another device'
        limits={}
        if installed:
            try:
                limits=context_plan(route)
                if not limits['fits']: reason='Free phone RAM is too low; close other apps before loading.'
                if state.get('route')==route and state.get('context_window'):limits['context_window']=state['context_window']
                if limits['fits']:reason='Ready to load · context %s tokens'%format(limits['context_window'],',')
            except (OSError,ValueError) as exc:limits={'fits':False};reason=str(exc)
        result.append({'id':model,'name':LABELS[route],'mode':mode,'route':route,'installed':installed,'selectable':installed and memory_ok and limits.get('fits',True),'reason':reason,'bytes':actual or partial,'expected_bytes':size,'qoder_credits':0,**limits})
    return result
def ensure():
    import os,secrets
    RUNTIME.mkdir(mode=0o700,exist_ok=True)
    if not KEY_FILE.exists():
        try:
            fd=os.open(KEY_FILE,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as out:out.write(secrets.token_hex(32))
        except FileExistsError:pass
    if KEY_FILE.stat().st_size<32:raise ValueError('Local runtime credential is invalid.')
    KEY_FILE.chmod(0o600)
def request(path,body=None,timeout=10):
    import json,urllib.request
    ensure()
    req=urllib.request.Request(UPSTREAM+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+KEY_FILE.read_text().strip(),'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req,timeout=timeout) as response:return json.loads(response.read(2_000_000))

def fit_messages(messages,context_window,reply_tokens=384):
    """Use the loaded model's template/tokenizer, retaining policy, task and newest evidence."""
    prompt=[dict(message) for message in messages]
    budget=context_window-reply_tokens-32
    while True:
        rendered=request('/apply-template',{'messages':prompt},timeout=30)['prompt']
        tokens=request('/tokenize',{'content':rendered,'add_special':True,'parse_special':True},timeout=30)['tokens']
        if len(tokens)<=budget:return prompt
        if len(prompt)<=4:
            raise ValueError('Task and latest evidence need %d tokens; this model has %d available after reply reserve. Reduce the task or use a model with more context.'%(len(tokens),budget))
        del prompt[2:4]

def stream_completion(body,progress=None,timeout=600):
    """Read only public completion content; never expose reasoning fields."""
    import json,time,urllib.request
    ensure()
    req=urllib.request.Request(UPSTREAM+'/v1/chat/completions',data=json.dumps({**body,'stream':True}).encode(),headers={'Authorization':'Bearer '+KEY_FILE.read_text().strip(),'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    pieces=[];size=0;started=time.monotonic();done=False
    with opener.open(req,timeout=timeout) as response:
        for line in response:
            if time.monotonic()-started>timeout:raise TimeoutError('Model generation timed out.')
            if len(line)>2_000_000:raise ValueError('Model stream exceeds limit.')
            if not line.startswith(b'data:'):continue
            data=line[5:].strip()
            if data==b'[DONE]':done=True;break
            chunk=json.loads(data)
            if chunk.get('error'):raise ValueError('Local model stream failed.')
            for choice in chunk.get('choices',[]):
                part=choice.get('delta',{}).get('content') or ''
                if not isinstance(part,str):raise ValueError('Invalid model stream content.')
                pieces.append(part);size+=len(part)
                if size>1_000_000:raise ValueError('Model reply exceeds limit.')
                if part and progress:progress(size)
    if not done:raise ValueError('Local model stream ended before completion.')
    return ''.join(pieces)
