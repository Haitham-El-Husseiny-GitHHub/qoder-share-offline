import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import attachment_store as attachments

class AttachmentTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_streamed_text_image_apk_and_hashes(self):
        for name,kind in [('policy.md','text'),('screenshot.png','image'),('example.apk','apk'),('document.pdf','file'),('bundle.zip','file'),('.env','file'),('private.pem','file')]:
            data=b'x'*150000
            result=attachments.store(self.root,name,io.BytesIO(data),len(data),[self.root])
            self.assertEqual(result['kind'],kind);self.assertEqual(result['sha256'],hashlib.sha256(data).hexdigest())
            self.assertEqual((self.root/result['path']).read_bytes(),data)
    def test_reference_survives_project_change_and_rejects_forged_paths(self):
        result=attachments.store(self.root,'sample.apk',io.BytesIO(b'apk'),3,[self.root])
        self.assertEqual(attachments.references([result],self.root),[self.root/result['path']])
        for path in ['../outside','source.py','attachments/not-an-id/sample.apk','/etc/passwd']:
            with self.assertRaises(ValueError):attachments.references([{**result,'path':path}],self.root)
        target=self.root/result['path'];target.unlink();target.symlink_to(self.root/'source.txt');(self.root/'source.txt').write_text('source')
        with self.assertRaises(ValueError):attachments.references([result],self.root)
    def test_duplicate_names_never_overwrite_source(self):
        (self.root/'policy.md').write_text('original')
        paths=[attachments.store(self.root,'policy.md',io.BytesIO(b'a'),1,[self.root])['path'] for _ in range(2)]
        self.assertNotEqual(*paths);self.assertEqual((self.root/'policy.md').read_text(),'original')
    def test_invalid_paths_and_size_limit(self):
        for name in ['../escape.txt','a/b.md','a\\b.md','name\n.txt']:
            with self.subTest(name=name),self.assertRaises(ValueError):attachments.store(self.root,name,io.BytesIO(b'a'),1,[self.root])
        with self.assertRaises(ValueError):attachments.store(self.root,'a.txt',io.BytesIO(),attachments.MAX_BYTES+1,[self.root])
        with tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(ValueError):attachments.store(outside,'a.txt',io.BytesIO(b'a'),1,[self.root])
    def test_incomplete_transfer_is_removed(self):
        with self.assertRaises(ValueError):attachments.store(self.root,'a.txt',io.BytesIO(b'a'),10,[self.root])
        self.assertEqual(list((self.root/'attachments').iterdir()),[])
    def test_attachment_directory_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root/'attachments').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):attachments.store(self.root,'a.txt',io.BytesIO(b'a'),1,[self.root])

if __name__=='__main__':unittest.main()
