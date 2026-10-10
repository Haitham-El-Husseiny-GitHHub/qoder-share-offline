#!/usr/bin/env python3
"""Resume and verify a pinned GGUF download; no inference or GPU rental."""
import argparse,hashlib,json,os,shutil,urllib.request
from pathlib import Path

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def valid(p,e):
 return p.is_file() and p.stat().st_size==e['size'] and digest(p)==e['sha256']
def fetch(e,root,source=None):
 root.mkdir(parents=True,exist_ok=True);p=root/e['file']
 if p.exists():
  if valid(p,e):print('Already verified:',p);return p
  raise ValueError('Existing model differs from the pinned checksum; it was preserved: '+str(p))
 part=p.with_name(p.name+'.download.partial')
 if source:
  source=Path(source)
  if not valid(source,e):raise ValueError('Imported model size/checksum does not match this entry.')
  shutil.copyfile(source,part)
 else:
  offset=part.stat().st_size if part.exists() else 0
  if offset>e['size']:raise ValueError('Partial file is larger than expected.')
  if offset<e['size']:
   url='https://huggingface.co/'+e['repo']+'/resolve/'+e['revision']+'/'+e.get('source_file',e['file'])+'?download=true'
   req=urllib.request.Request(url,headers={'Range':'bytes='+str(offset)+'-'})
   with urllib.request.urlopen(req,timeout=90) as r:
    if r.status==206:
     if not r.headers.get('Content-Range','').startswith('bytes '+str(offset)+'-'):raise ValueError('Incorrect resumed range.')
     mode='ab'
    elif r.status==200:offset=0;mode='wb'
    else:raise ValueError('Unexpected download status.')
    with part.open(mode) as f:
     last=offset//(128*1024*1024)
     while b:=r.read(4*1024*1024):
      if offset+len(b)>e['size']:raise ValueError('Download exceeds expected model size.')
      f.write(b);offset+=len(b)
      if offset//(128*1024*1024)>last:print(e['mode'],round(100*offset/e['size'],1),'%',flush=True);last=offset//(128*1024*1024)
 if not valid(part,e):raise ValueError('Download verification failed; partial retained for inspection. Remove it before retrying a corrupt transfer.')
 with part.open('rb') as f:
  if f.read(4)!=b'GGUF':raise ValueError('Not a GGUF model.')
 os.chmod(part,0o600);os.replace(part,p);print('Verified:',p);return p
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('model',nargs='?',default='coding');a.add_argument('--list',action='store_true');a.add_argument('--import-file');a.add_argument('--root',type=Path,default=Path.home()/'qoder-selfhost/models');args=a.parse_args()
 entries=json.loads((Path(__file__).parent/'models.json').read_text())
 if args.list:print('\n'.join(e['mode']+' — '+e['name']+' — '+str(round(e['size']/1e9,2))+' GB' for e in entries))
 else:
  e=next((e for e in entries if e['mode']==args.model),None)
  if e is None:a.error('Unknown download option. Use --list.')
  fetch(e,args.root,args.import_file)
