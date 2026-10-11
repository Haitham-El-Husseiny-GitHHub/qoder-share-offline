import sys, tempfile, unittest, json, threading, shutil
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import source_lookup as lookup, coding_runner as runner, server
from job_journal import Journal, recovery_workspace
class DiscoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.home=Path(self.tmp.name);self.source=self.home/'unusual'/'deeper'/'my-app'; self.source.mkdir(parents=True);(self.source/'pyproject.toml').write_text('[project]\nname="my-app"\n');(self.source/'main.py').write_text('value = 1\n')
 def tearDown(self):self.tmp.cleanup()
 def test_outside_workspace_api_folder_and_file(self):
  self.assertEqual(server.resolve_source_folder(self.source),self.source)
  self.assertEqual(server.resolve_source_folder(self.source/'main.py'),self.source)
 def test_explicit_objective_path(self):
  self.assertEqual(lookup.acquire('Fix "'+str(self.source/'main.py')+'"',self.home)['root'],str(self.source))
 def test_automatic_discovery_under_home(self):
  with patch.object(Path,'home',return_value=self.home):
   result=lookup.acquire('Fix app my-app',self.home/'coding-workspace',config={'offline':True})
  self.assertEqual(result['root'],str(self.source))
 def test_package_metadata_identifies_source(self):
  (self.source/'package.json').write_text('{"name":"com.example.special"}')
  self.assertIn(self.source,lookup.find_local('com.example.special',[self.home]))
 def test_deep_source(self):
  p=self.home/'one'/'two'/'three'/'four'/'five'/'deep-app';p.mkdir(parents=True);(p/'package.json').write_text('{}')
  self.assertIn(p,lookup.find_local('deep-app',[self.home]))
 def test_absolute_read_edit_in_place_and_backup(self):
  ws=runner.Workspace(self.source,False);job={'id':'a'*32,'workspace':str(self.source),'objective':'fix','profile':'BUILD'}
  journal=Journal(self.home/'jobs',job);recovery=recovery_workspace(ws,journal,{'edit_in_place':True});ws.journal=journal
  self.assertEqual(ws.root,self.source);self.assertEqual(recovery['mode'],'in_place_backups')
  data=ws.invoke('read_file',{'path':str(self.source/'main.py')})
  result=ws.invoke('edit_patch',{'path':str(self.source/'main.py'),'old_text':'value = 1','new_text':'value = 2','expected_sha256':data['sha256']})
  self.assertIn('value = 2',(self.source/'main.py').read_text())
  self.assertEqual(Path(journal.data['patches'][0]['backup']).read_text(),'value = 1\n')
 def test_cross_project_path_requires_target_selection(self):
  with self.assertRaises(ValueError):runner.Workspace(self.source,False).file(str(self.home/'other.py'))
 def test_missing_path_has_real_error(self):
  with self.assertRaises(FileNotFoundError):server.resolve_source_folder(self.home/'missing')
if __name__=='__main__':unittest.main()
