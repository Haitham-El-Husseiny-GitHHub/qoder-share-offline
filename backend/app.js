const el=id=>document.getElementById(id), storageKey='qoder-selfhost-history-v1';
let messages=[],aborter=null,readyModel=null,switching=false,poll=null,refreshing=false;
try{const parsed=JSON.parse(localStorage.getItem(storageKey)||'[]');if(Array.isArray(parsed))messages=parsed.filter(m=>m&&['user','assistant'].includes(m.role)&&typeof m.content==='string').slice(-100);el('system').value=localStorage.getItem('qoder-selfhost-system')||'';}catch{}
function save(){try{let copy=messages.slice(-100);while(JSON.stringify(copy).length>500000&&copy.length)copy.shift();localStorage.setItem(storageKey,JSON.stringify(copy));}catch{el('error').textContent='Browser storage unavailable; export your chat to keep it.';}}
function render(){el('chat').replaceChildren();for(const m of messages){const a=document.createElement('article'),b=document.createElement('strong');b.textContent=m.role==='user'?'You':'Model';a.append(b,document.createTextNode(m.content));el('chat').append(a);}}
async function api(path,options={}){const r=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});let j;try{j=await r.json();}catch{throw Error('Backend returned an invalid response');}if(!r.ok)throw Error(j.error?.message||j.error||r.statusText);return j;}
async function refresh(){
if(refreshing)return;refreshing=true;
try{const m=await api('/api/models');el('model').replaceChildren();for(const v of m.data||[]){const o=document.createElement('option');o.value=v.id;o.textContent=v.name||v.id;o.dataset.mode=v.mode;el('model').append(o);}
const s=await api('/api/status');readyModel=s.ready||null;switching=s.status==='LOADING';
if(readyModel)el('model').value=readyModel;
el('status').textContent=(s.status||'Unknown')+' — '+(s.phase||'')+' | Cloud cost: $'+Number(s.hourly_usd||0).toFixed(4)+'/hour';
el('chat-mode').setAttribute('aria-pressed',String(readyModel?.startsWith('Llama3')||false));el('coding-mode').setAttribute('aria-pressed',String(readyModel?.startsWith('Qwen2.5')||false));
if(switching&&!poll)poll=setInterval(refresh,2000);if(!switching&&poll){clearInterval(poll);poll=null;}
}catch(e){readyModel=null;el('status').textContent=e.message;}finally{refreshing=false;controls();}
}
function controls(){const busy=!!aborter||switching;for(const id of ['chat-mode','coding-mode','model'])el(id).disabled=busy;el('send').disabled=busy||!readyModel;}
async function switchMode(mode){if(aborter||switching)return;el('error').textContent='';switching=true;controls();
try{await api('/api/switch',{method:'POST',body:JSON.stringify({mode})});if(!poll)poll=setInterval(refresh,2000);}
catch(e){switching=false;el('error').textContent=e.message;}finally{await refresh();controls();}}
el('chat-mode').onclick=()=>switchMode('chat');el('coding-mode').onclick=()=>switchMode('coding');el('model').onchange=()=>switchMode(el('model').selectedOptions[0].dataset.mode);
el('refresh').onclick=refresh;
el('system').onchange=()=>{try{localStorage.setItem('qoder-selfhost-system',el('system').value);}catch{}};
el('clear').onclick=()=>{if(!aborter&&confirm('Clear this self-hosted chat?')){messages=[];save();render();}};
el('export').onclick=()=>{const text=messages.map(m=>'## '+(m.role==='user'?'You':'Model')+'\n\n'+m.content).join('\n\n');const url=URL.createObjectURL(new Blob([text],{type:'text/markdown'}));const a=document.createElement('a');a.href=url;a.download='Qoder-Selfhost-Chat.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
el('cancel').onclick=()=>aborter?.abort();
el('form').onsubmit=async e=>{e.preventDefault();if(aborter||switching)return;el('error').textContent='';const prompt=el('prompt').value.trim();if(!prompt)return;await refresh();const model=el('model').value;if(readyModel!==model){el('error').textContent='Local model is not ready. Tap Refresh when it is loaded, then send again.';return;}
const pending=[...messages,{role:'user',content:prompt}],system=el('system').value.trim();aborter=new AbortController();el('send').disabled=true;el('cancel').disabled=false;el('clear').disabled=true;controls();
try{const r=await api('/api/chat',{method:'POST',signal:aborter.signal,body:JSON.stringify({model,messages:[...(system?[{role:'system',content:system}]:[]),...pending],max_tokens:1024,stream:false})});const text=r.choices?.[0]?.message?.content;if(typeof text!=='string')throw Error('No text answer returned');messages=[...pending,{role:'assistant',content:text}].slice(-100);save();render();el('prompt').value='';}catch(e){el('error').textContent=e.name==='AbortError'?'Stopped waiting. Local processing may continue until the backend finishes.':e.message;}finally{aborter=null;el('send').disabled=false;el('cancel').disabled=true;el('clear').disabled=false;controls();refresh();}};
render();refresh();
