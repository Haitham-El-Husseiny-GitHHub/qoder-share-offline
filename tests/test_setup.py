import sys,json,tempfile,unittest,hashlib,argparse
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import install,fetch_model
class SetupTests(unittest.TestCase):
 def test_clean_install_simulation_and_existing_guard(self):
  with tempfile.TemporaryDirectory() as t:
   home=Path(t)/'home';home.mkdir();prefix=Path(t)/'usr';prefix.mkdir();calls=[]
   args=argparse.Namespace(check=False,update=False,no_model=True,apk_tools=True)
   with patch.object(install,'HOME',home),patch.object(install,'PREFIX',prefix),patch.object(Path,'home',return_value=home),patch.object(install,'run',side_effect=lambda *a:calls.append(a)),patch.object(install.subprocess,'run',return_value=argparse.Namespace(stdout='--api-key-file --parallel --reasoning-budget --chat-template-kwargs --cache-type-k --no-webui')),patch.object(install.os,'uname',return_value=argparse.Namespace(machine='aarch64')):
    install.install(args)
    key=home/'qoder-selfhost/runtime/inference.key';self.assertEqual(key.stat().st_size,64)
    self.assertTrue((prefix/'var/service/qoder-selfhost/run').exists());self.assertTrue((home/'bin/qoder-local-code').exists())
    self.assertIn('allow-external-apps = true',(home/'.termux/termux.properties').read_text())
    self.assertTrue(any('apktool' in c for c in calls))
    with self.assertRaises(ValueError):install.install(args)
   sys.modules.pop('runtime_config',None)
 def test_import_checksum_and_preserve_existing(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);data=b'GGUF'+b'test weights';src=root/'original';src.write_bytes(data);entry={'mode':'test','file':'test.gguf','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
   out=fetch_model.fetch(entry,root/'models',src);self.assertEqual(out.read_bytes(),data)
   out.write_bytes(b'wrong')
   with self.assertRaises(ValueError):fetch_model.fetch(entry,root/'models',src)
   self.assertEqual(out.read_bytes(),b'wrong')
 def test_resume_download(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);data=b'GGUFfixture';(root/'t.gguf.download.partial').write_bytes(data[:4]);entry={'mode':'test','repo':'test/repo','revision':'fixed','file':'t.gguf','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
   class Response:
    status=206;headers={'Content-Range':'bytes 4-10/11'}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):r=self.data;self.data=b'';return r
   r=Response();r.data=data[4:]
   with patch.object(fetch_model.urllib.request,'urlopen',return_value=r) as op:out=fetch_model.fetch(entry,root)
   self.assertEqual(out.read_bytes(),data);self.assertEqual(op.call_args.args[0].get_header('Range'),'bytes=4-')
 def test_tamper_detection(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'file').write_text('bad');(p/'package.json').write_text(json.dumps({'sha256':{'file':'0'*64}}))
   with patch.object(install,'BASE',p),self.assertRaises(ValueError):install.verify()
if __name__=='__main__':unittest.main()
