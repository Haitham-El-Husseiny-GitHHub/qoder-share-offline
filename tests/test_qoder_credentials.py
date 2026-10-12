import importlib,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import qoder_credentials as keys
class CredentialsTests(unittest.TestCase):
 def test_saved_key_survives_reload_replacement_and_removal(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'private/qoder.key'
   with patch.object(keys,'PATH',path):
    keys.save('first-test-token');self.assertEqual(keys.status(),{'saved':True,'persistent':True})
    self.assertEqual(path.stat().st_mode&0o777,0o600);self.assertEqual(path.parent.stat().st_mode&0o777,0o700)
    self.assertEqual(keys.environment({})['QODER_PERSONAL_ACCESS_TOKEN'],'first-test-token')
    keys.save('replacement-test-token');self.assertEqual(keys.read(),'replacement-test-token')
   importlib.reload(keys)
   with patch.object(keys,'PATH',path):
    self.assertEqual(keys.read(),'replacement-test-token');keys.remove();self.assertFalse(keys.status()['saved'])
    self.assertNotIn('QODER_PERSONAL_ACCESS_TOKEN',keys.environment({'QODER_PERSONAL_ACCESS_TOKEN':'old'}))
 def test_invalid_key_does_not_replace_saved_one(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(keys,'PATH',Path(folder)/'qoder.key'):
   keys.save('saved-test-token')
   for value in [None,'','a\nb','x'*8193]:
    with self.assertRaises(ValueError):keys.save(value)
   self.assertEqual(keys.read(),'saved-test-token')
