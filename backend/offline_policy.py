"""Offline guards for managed commands, not an OS network sandbox."""
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import urllib.request


def local_url(url):
    host=urlsplit(url).hostname
    try:return ipaddress.ip_address(host).is_loopback
    except (ValueError,TypeError):return host=='localhost'


class LocalRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not local_url(newurl):raise ValueError('Offline job refused a non-loopback HTTP redirect.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def command(argv):
    """Reject known remote bootstrap/fetch operations before spawning a child."""
    name=Path(argv[0]).name
    args=argv[1:]
    if name in {'apt','apt-get','pkg','sdkmanager','curl','wget'}:
        raise ValueError('Offline job refused network/bootstrap executable: '+name)
    if name=='git' and (any(a in {'fetch','pull','clone','ls-remote'} for a in args) or 'submodule' in args and 'update' in args):
        raise ValueError('Offline job refused Git network operation.')
    if name in {'pip','pip3'} or name.startswith('python') and len(args)>2 and args[:2]==['-m','pip']:
        if '--no-index' not in args:raise ValueError('Offline pip requires --no-index and a verified local cache.')
    gradle=name in {'gradle','gradlew'} or name in {'sh','bash'} and args and Path(args[0]).name=='gradlew'
    if gradle and '--offline' not in args:raise ValueError('Offline Gradle requires --offline; wrapper distribution must already be cached.')
    if name=='cargo' and '--offline' not in args:raise ValueError('Offline Cargo requires --offline.')
    if name=='npx' and '--offline' not in args:raise ValueError('Offline npx requires --offline.')
    if name in {'npm','pnpm','yarn','bun'} and args and args[0]!='run' and any(a in {'install','ci','add','update','upgrade','dlx','exec'} for a in args) and '--offline' not in args:
        raise ValueError('Offline package installation requires --offline and a verified local cache.')
