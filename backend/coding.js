const el=id=>document.getElementById(id);let busy=false,ready=false;
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});const j=await r.json();if(!r.ok)throw Error(j.error?.message||j.error||r.statusText);return j;}
function controls(){el('run').disabled=busy||!ready;el('load').disabled=busy;for(const id of ['workspace','profile','objective'])el(id).disabled=busy;}
async function refresh(){try{const s=await api('/api/status');ready=s.ready==='Qwen2.5-Coder-3B-Abliterated';el('status').textContent=s.status+' — '+s.phase;const j=await api('/api/coding');busy=j.status==='running';if(!el('workspace').value)el('workspace').value=j.default_workspace;if(j.id){el('result').textContent=JSON.stringify(j,null,2);}controls();}catch(e){el('error').textContent=e.message;}}
el('load').onclick=async()=>{try{el('error').textContent='';await api('/api/switch',{mode:'coding'});await refresh();}catch(e){el('error').textContent=e.message;}};
el('refresh').onclick=refresh;
el('form').onsubmit=async e=>{e.preventDefault();if(busy||!ready)return;busy=true;controls();el('error').textContent='';try{await api('/api/coding',{workspace:el('workspace').value,profile:el('profile').value,objective:el('objective').value});el('result').textContent='Running local coding task…';await refresh();}catch(e){busy=false;controls();el('error').textContent=e.message;}};
refresh();setInterval(refresh,3000);
