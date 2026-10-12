const $=id=>document.getElementById(id);
let session=localStorage.getItem('oc-session')||'',polling=false,models=[];
$('directory').value=localStorage.getItem('oc-directory')||'/data/data/com.termux/files/home/coding-workspace';
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});let d=await r.json();if(!r.ok)throw Error(d.error||r.status);return d}
function get(path,extra={}){return api('/api/opencode?'+new URLSearchParams({path,directory:$('directory').value,...extra}))}
function post(action,extra={}){return api('/api/opencode',{action,directory:$('directory').value,session,objective:$('objective').value,model:$('model').value,agent:$('agent').value,...extra})}
function error(e){$('error').textContent=e.message||e}
function chosen(){return models.find(m=>$('model').value===($('providerList').value+'/'+m.id))}
function access(){const m=chosen();$('modelAccess').textContent=m?(m.available?'Provider connection ready':m.reason||'Provider authentication may be required'):'No matching model';$('send').disabled=!m;if(m&&!m.available)$('provider').value=$('providerList').value}
function renderModels(){const previous=$('model').value||localStorage.getItem('oc-model')||'opencode/mimo-v2.6-flash-free',search=$('filter').value.toLowerCase();$('model').replaceChildren();for(const m of models.filter(m=>(m.name+' '+m.id).toLowerCase().includes(search))){const o=document.createElement('option');o.value=$('providerList').value+'/'+m.id;o.textContent=m.name;$('model').append(o)}if([...$('model').options].some(o=>o.value===previous))$('model').value=previous;access()}
async function refresh(force=false){try{const h=await get('/global/health');$('status').textContent=h.healthy?'Connected · OpenCode '+h.version:'Offline';const selected=$('providerList').value||localStorage.getItem('oc-provider')||'opencode',d=await get('/provider',{provider:selected,refresh:force?'1':'0'});$('providerList').replaceChildren();for(const p of d.provider_index){const o=document.createElement('option');o.value=p.id;o.textContent=p.name+' ('+p.count+')'+(p.connected?'':' · connect key');$('providerList').append(o)}$('providerList').value=selected;models=d.providers[0]?.models||[];renderModels();$('catalogStatus').textContent=models.length+' models listed · '+models.filter(m=>m.available).length+' ready'+(selected==='opencode'?' · '+d.catalog.public_count+' in public API / '+d.catalog.documented_count+' on website':'')+(d.catalog.refresh_error?' · using last saved catalog':'');$('error').textContent=''}catch(e){error(e)}}
$('refresh').onclick=()=>refresh(true);$('providerList').onchange=()=>{localStorage.setItem('oc-provider',$('providerList').value);$('filter').value='';refresh()};$('filter').oninput=renderModels;$('model').onchange=access;
$('connect').onclick=async()=>{try{await post('connect',{provider:$('provider').value,key:$('key').value,baseURL:$('base').value,modelID:$('modelID').value});$('key').value='';$('providerList').value=$('provider').value;localStorage.setItem('oc-provider',$('provider').value);await refresh()}catch(e){error(e)}};
$('discover').onclick=async()=>{try{const d=await post('discover');if(d.directory){$('directory').value=d.directory;localStorage.setItem('oc-directory',d.directory)}$('output').textContent=JSON.stringify(d.discovery,null,2)}catch(e){error(e)}};
$('send').onclick=async()=>{try{$('send').disabled=true;const d=await post('run');session=d.session;$('directory').value=d.directory;localStorage.setItem('oc-directory',d.directory);localStorage.setItem('oc-session',session);localStorage.setItem('oc-model',$('model').value);$('status').textContent='Task started';$('error').textContent='';await poll()}catch(e){error(e)}finally{access()}};
$('stop').onclick=async()=>{try{await post('abort');$('status').textContent='Stopped'}catch(e){error(e)}};
$('fresh').onclick=()=>{session='';localStorage.removeItem('oc-session');$('output').textContent='New session';$('objective').value=''};
$('diff').onclick=async()=>{if(!session)return;try{$('output').textContent=JSON.stringify(await get('/session/'+session+'/diff'),null,2)}catch(e){error(e)}};
async function poll(){if(!session||polling)return;polling=true;try{const messages=await get('/session/'+session+'/message');$('output').textContent=messages.flatMap(m=>[...(m.parts||[]),...(m.info?.error?[{type:'text',text:'Provider error: '+JSON.stringify(m.info.error)}]:[])]).map(p=>p.type==='text'?p.text:p.type==='tool'?'Tool: '+p.tool+'\n'+JSON.stringify(p.state,null,2):'').filter(Boolean).join('\n\n');const statuses=await get('/session/status');$('status').textContent='OpenCode · '+(statuses[session]?.type||'idle')}catch(e){error(e)}finally{polling=false}}
refresh();setInterval(poll,2000);

async function bridgeStatus(){
 try{const r=await fetch('/api/bridge'),d=await r.json();$('bridge').textContent='Termux connected · '+(d.rish_connected?'Rish connected · '+d.access_level+' access':'Rish reconnecting · start Shizuku if Android requires it');}
 catch(e){$('bridge').textContent='Termux bridge reconnecting…';}
}
bridgeStatus();setInterval(bridgeStatus,5000);
window.addEventListener('online',()=>{bridgeStatus();refresh()});

let catalogRefreshing=false;
async function autoCatalog(){if(catalogRefreshing)return;catalogRefreshing=true;try{await refresh()}finally{catalogRefreshing=false}}
setInterval(autoCatalog,15000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)autoCatalog()});
