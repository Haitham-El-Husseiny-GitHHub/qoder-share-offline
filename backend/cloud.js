const $=id=>document.getElementById(id);let models=[],job=localStorage.getItem('cloud-job')||'',polling=false;
$('directory').value=localStorage.getItem('cloud-directory')||'/data/data/com.termux/files/home/coding-workspace';
async function api(path,data){const r=await fetch('/api/qoder-cloud'+path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});const d=await r.json();if(!r.ok)throw Error(d.error||r.status);return d}
function render(){const old=$('model').value||localStorage.getItem('cloud-model')||'Qwen3.8-Flash',search=$('filter').value.toLowerCase();$('model').replaceChildren();for(const m of models.filter(m=>(m.name+' '+m.id).toLowerCase().includes(search))){const o=document.createElement('option');o.value=m.id;o.textContent=m.name;$('model').append(o)}if([...$('model').options].some(o=>o.value===old))$('model').value=old}
async function refresh(force=false){try{const d=await api('/models'+(force?'?refresh=1':''));models=d.models;render();$('catalog').textContent=models.length+' published model/tier options · no app-side subscription or region filtering'}catch(e){$('error').textContent=e.message}}
$('refresh').onclick=()=>refresh(true);$('filter').oninput=render;
$('run').onclick=async()=>{try{$('run').disabled=true;const d=await api('/run',{model:$('model').value,directory:$('directory').value,objective:$('objective').value});job=d.id;localStorage.setItem('cloud-job',job);localStorage.setItem('cloud-model',$('model').value);localStorage.setItem('cloud-directory',d.directory);$('directory').value=d.directory;$('error').textContent='';await poll()}catch(e){$('error').textContent=e.message}finally{$('run').disabled=false}};
$('stop').onclick=async()=>{try{if(job)await api('/stop',{id:job})}catch(e){$('error').textContent=e.message}};
async function poll(){if(!job||polling)return;polling=true;try{const d=await api('/job?id='+encodeURIComponent(job));$('output').textContent=d.status+' · '+d.model+'\n\n'+(d.output||d.error||'Starting…');$('run').disabled=['starting','running'].includes(d.status)}catch(e){$('error').textContent=e.message}finally{polling=false}}
refresh();setInterval(poll,1500);

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
