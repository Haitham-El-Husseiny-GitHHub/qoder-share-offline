import subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import bridge

class BridgeTests(unittest.TestCase):
    def setUp(self):bridge._cached=None;bridge._checked=0
    def tearDown(self):bridge._cached=None;bridge._checked=0
    def check_output(self,stdout,stderr,code=0):
        with patch.object(bridge.shutil,'which',return_value='/termux/rish'),patch.object(bridge.subprocess,'run',return_value=subprocess.CompletedProcess([],code,stdout,stderr)):
            return bridge.status()
    def test_shell_identity_on_stderr_is_connected(self):
        result=self.check_output('QODER_BRIDGE_OK\n','uid=2000(shell) gid=2000(shell)\n')
        self.assertTrue(result['rish_connected']);self.assertEqual(result['access_level'],'shell');self.assertFalse(result['private_app_data'])
    def test_root_identity_on_stderr_is_reported_as_root(self):
        result=self.check_output('','uid=0(root) gid=0(root)\n')
        self.assertTrue(result['rish_connected']);self.assertEqual(result['access_level'],'root');self.assertTrue(result['private_app_data'])
    def test_split_completion_marker_is_accepted(self):
        self.assertTrue(self.check_output('uid=2000(shell)\n','QODER_BRIDGE_OK\n',1)['rish_connected'])
    def test_termux_identity_does_not_claim_shell_access(self):
        self.assertFalse(self.check_output('uid=10702(u0_a702)\n','QODER_BRIDGE_OK\n')['rish_connected'])
    def test_denied_rish_does_not_claim_connection(self):
        self.assertFalse(self.check_output('','Permission denied',1)['rish_connected'])

if __name__=='__main__':unittest.main()
