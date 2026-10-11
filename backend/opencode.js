const $=id=>document.getElementById(id);
let session=localStorage.getItem('oc-session')||'',polling=false;
$('directory').value=localStorage.getItem('oc-directory')||'/data/data/com.termux/files/home/coding-workspace';
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});let d=await r.json();if(!r.ok)throw Error(d.error||r.status);return d}
function get(path){return api('/api/opencode?'+new URLSearchParams({path,directory:$('directory').value}))}
function post(action,extra={}){return api('/api/opencode',{action,directory:$('directory').value,session,objective:$('objective').value,model:$('model').value,agent:$('agent').value,...extra})}
function error(e){$('error').textContent=e.message||e}
async function refresh(){try{const h=await get('/global/health');$('status').textContent=h.healthy?'Connected · OpenCode '+h.version:'Offline';const d=await get('/provider'),previous=$('model').value||localStorage.getItem('oc-model')||'opencode/mimo-v2.6-flash-free';$('model').replaceChildren();for(const p of d.providers)for(const m of p.models){const o=document.createElement('option');o.value=p.id+'/'+m.id;o.textContent=p.name+' / '+m.name;$('model').append(o)}if([...$('model').options].some(o=>o.value===previous))$('model').value=previous;if(!$('model').options.length)$('status').textContent+=' · connect an API provider';$('error').textContent=''}catch(e){error(e)}}
$('refresh').onclick=refresh;
$('connect').onclick=async()=>{try{await post('connect',{provider:$('provider').value,key:$('key').value,baseURL:$('base').value,modelID:$('modelID').value});$('key').value='';await refresh()}catch(e){error(e)}};
$('discover').onclick=async()=>{try{const d=await post('discover');if(d.directory){$('directory').value=d.directory;localStorage.setItem('oc-directory',d.directory)}$('output').textContent=JSON.stringify(d.discovery,null,2)}catch(e){error(e)}};
$('send').onclick=async()=>{try{$('send').disabled=true;const d=await post('run');session=d.session;$('directory').value=d.directory;localStorage.setItem('oc-directory',d.directory);localStorage.setItem('oc-session',session);localStorage.setItem('oc-model',$('model').value);$('status').textContent='Task started';$('error').textContent='';await poll()}catch(e){error(e)}finally{$('send').disabled=false}};
$('stop').onclick=async()=>{try{await post('abort');$('status').textContent='Stopped'}catch(e){error(e)}};
$('fresh').onclick=()=>{session='';localStorage.removeItem('oc-session');$('output').textContent='New session';$('objective').value=''};
$('diff').onclick=async()=>{if(!session)return;try{$('output').textContent=JSON.stringify(await get('/session/'+session+'/diff'),null,2)}catch(e){error(e)}};
async function poll(){if(!session||polling)return;polling=true;try{const messages=await get('/session/'+session+'/message');$('output').textContent=messages.flatMap(m=>m.parts||[]).map(p=>p.type==='text'?p.text:p.type==='tool'?'Tool: '+p.tool+'\n'+JSON.stringify(p.state,null,2):'').filter(Boolean).join('\n\n');const statuses=await get('/session/status');$('status').textContent='OpenCode · '+(statuses[session]?.type||'idle')}catch(e){error(e)}finally{polling=false}}
refresh();setInterval(poll,2000);
