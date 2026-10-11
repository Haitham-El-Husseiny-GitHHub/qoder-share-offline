import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import task_router
import source_lookup


class RecursivePythonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def put(self,path,text='value=1\n'):
        path=self.root/path;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    def test_nested_source_routes_as_project_without_metadata(self):
        self.put('src/package/ledger.py')
        project=task_router.project(self.root)
        self.assertTrue(project['source']);self.assertEqual(project['kind'],'python')
        self.assertTrue(source_lookup._project(self.root))
        plan=task_router.select(self.root,'Fix ledger.py crash','FIX',{}, {})
        self.assertEqual(plan['workflow'],'source_fix');self.assertNotIn('rish',plan['adapters'])
    def test_nonpackage_nested_tests_are_actually_run(self):
        self.put('src/ledger.py')
        for path in ['tests/unit/test_ledger.py','checks/deep/test_amount.py']:
            self.put(path,'import unittest\nclass Amount(unittest.TestCase):\n def test_amount(self): self.assertEqual(105,100)\n')
        checks=task_router.project(self.root)['checks']
        self.assertEqual({c['argv'][-2] for c in checks},{'tests/unit','checks/deep'})
        for check in checks:
            result=subprocess.run(check['argv'],cwd=self.root,capture_output=True,text=True)
            self.assertEqual(result.returncode,1);self.assertIn('Ran 1 test',result.stderr)
    def test_importable_nested_tests_keep_existing_start(self):
        self.put('tests/unit/__init__.py','')
        self.put('tests/unit/test_value.py','import unittest\nclass Value(unittest.TestCase):\n def test_value(self): self.assertTrue(True)\n')
        checks=task_router.project(self.root)['checks']
        self.assertEqual(len(checks),1);self.assertEqual(checks[0]['argv'][-2],'tests')
        result=subprocess.run(checks[0]['argv'],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0);self.assertIn('Ran 1 test',result.stderr)
    def test_runtime_dependencies_and_symlinks_are_excluded(self):
        for path in ['venv/code.py','.venv/code.py','runtime/code.py','node_modules/code.py','build/code.py']:
            self.put(path)
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside)/'test_external.py').write_text('value=1')
            (self.root/'external').symlink_to(outside,target_is_directory=True)
            self.assertFalse(task_router.project(self.root)['source'])
    def test_cmake_and_node_markers_keep_priority(self):
        self.put('src/script.py');self.put('CMakeLists.txt','project(example)\n')
        self.assertEqual(task_router.project(self.root)['kind'],'native')
        self.put('package.json','{"scripts":{"test":"node test.js"}}')
        self.assertEqual(task_router.project(self.root)['kind'],'node')

if __name__=='__main__':unittest.main()
