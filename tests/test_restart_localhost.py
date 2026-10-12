import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from restart_localhost import is_localhost_daemon,PREFIX

class RestartTargetsTests(unittest.TestCase):
 def test_both_cli_launch_paths_are_restarted(self):
  for path in [PREFIX/'bin/qodercli',PREFIX/'lib/node_modules/@qoder-ai/qodercli/bundle/qodercli.js']:
   self.assertTrue(is_localhost_daemon(['node',str(path),'remote-control','--name','localhost']))
 def test_session_worker_is_preserved(self):
  self.assertFalse(is_localhost_daemon(['node',str(PREFIX/'bin/qodercli'),'--remote-control','qs_existing']))
 def test_other_environment_is_preserved(self):
  self.assertFalse(is_localhost_daemon(['node',str(PREFIX/'bin/qodercli'),'remote-control','--name','other']))
 def test_shell_text_is_not_mistaken_for_a_daemon(self):
  self.assertFalse(is_localhost_daemon(['bash','-c','node '+str(PREFIX/'bin/qodercli')+' remote-control --name localhost']))
