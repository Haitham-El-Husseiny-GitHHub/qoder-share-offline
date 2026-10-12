"""Read verified account quotas through the installed Qoder client's own reader."""
import json, os, subprocess, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path('/data/data/com.termux/files/home')
LOCK = threading.Lock()
CACHE = None

def normalize(usage, checked_at=None):
    if isinstance(usage, dict) and isinstance(usage.get('data'), dict):
        usage = usage['data']
    if not isinstance(usage, dict):
        raise ValueError('Account quota format unavailable.')
    parts = []
    for key, label in [('userQuota', 'Plan'), ('addOnQuota', 'Add-on'), ('orgResourcePackage', 'Organization')]:
        raw = usage.get(key, usage.get({'userQuota':'user_quota','addOnQuota':'add_on_quota','orgResourcePackage':'org_resource_package'}[key]))
        if not isinstance(raw, dict):
            continue
        remaining, total, used = raw.get('remaining'), raw.get('total'), raw.get('used')
        if remaining is None and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (total, used)):
            remaining = max(0, total-used)
        if isinstance(remaining, (int, float)) and not isinstance(remaining, bool):
            parts.append({'label':label, 'remaining':remaining, 'total':total, 'used':used})
    if not parts:
        raise ValueError('Account response does not expose a credit balance.')
    personal = [p for p in parts if p['label'] != 'Organization']
    return {'available':True, 'remaining':sum(p['remaining'] for p in personal) if personal else None,
            'unit':'Credits', 'parts':parts, 'checked_at':checked_at or time.time(),
            'quota_exceeded':bool(usage.get('isQuotaExceeded', usage.get('is_quota_exceeded', False)))}

def install_reader():
    bundle = Path('/data/data/com.termux/files/usr/lib/node_modules/@qoder-ai/qodercli/bundle/qodercli.js')
    source = bundle.read_text()
    anchor = 'CY(),Eir(async()=>'
    position = source.rfind(anchor)
    if position < 0 or 'static async load(){let A=await this.loadDetailed()' not in source:
        raise ValueError('Installed Qoder client changed; account adapter requires an update.')
    # Initialize the existing credential store and WASM reader without running a coding task.
    harness = '''CY();d2();await e9();const user=await I6A.QoderCredentialStorage.load();
if(!user)throw Error("Qoder login unavailable");
const fs=await import("node:fs/promises");const home=process.env.HOME;
const endpoints=JSON.parse(await fs.readFile(home+"/.qoder/.cache/qoder-client-endpoint-cache.json","utf8"));
const base=endpoints.entries.prod.endpointSets.openapi.selected;
const path=user.organization_id?"/sash/api/v2/me/usage":"/api/v2/quota/usage";
const r=await fetch(base+path,{headers:{Accept:"application/json",Authorization:"Bearer "+(user.security_oauth_token??user.access_token)},signal:AbortSignal.timeout(12000)});
if(!r.ok)throw Error("Account quota HTTP "+r.status);let data=await r.json();
if(data.displayMode==="qoder")data=data.qoderUsage;
console.log("SHARE_ACCOUNT:"+JSON.stringify(data));process.exit(0);
'''
    reader = bundle.with_name('share-account-reader.mjs')
    if not reader.exists() or reader.stat().st_mtime < bundle.stat().st_mtime or 'SHARE_ACCOUNT:' not in reader.read_text()[-3000:]:
        reader.write_text(source[:position]+harness)
        reader.chmod(0o600)
    return reader

def qoder(force=False):
    global CACHE
    with LOCK:
        from qoder_credentials import read
        if read():
            return {'available':False,'checked_at':time.time(),'error':'Qoder PAT saved. View its subscription and usage in your Qoder account.'}
        if CACHE and not force and time.time()-CACHE['checked_at'] < 60:
            return dict(CACHE)
        try:
            reader = install_reader()
            result = subprocess.run(['node',str(reader)], capture_output=True, text=True, timeout=20,
                env={**os.environ,'PREFIX':'/data/data/com.termux/files/usr','TMPDIR':'/data/data/com.termux/files/usr/tmp','TERMUX_VERSION':'remote-session'})
            line = next((s[14:] for s in result.stdout.splitlines() if s.startswith('SHARE_ACCOUNT:')), None)
            if not line:
                raise ValueError('Qoder account quota could not be refreshed.')
            CACHE = normalize(json.loads(line))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            if CACHE and CACHE.get('available'):
                return {**CACHE, 'stale':True, 'error':str(exc)}
            CACHE = {'available':False,'checked_at':time.time(),'error':str(exc)}
        return dict(CACHE)

def go():
    from opencode_bridge import call
    data = call('/provider')
    connected = 'opencode-go' in data.get('connected', [])
    return {'available':False,'connected':connected,'checked_at':time.time(),
            'label':'Go allowance: view account' if connected else 'Go allowance: connect account',
            'detail':'OpenCode Go does not expose a verified allowance endpoint to this adapter.',
            'url':'https://opencode.ai/console'}
