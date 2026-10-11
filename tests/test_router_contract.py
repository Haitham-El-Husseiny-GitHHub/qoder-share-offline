import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import task_router
import tool_catalog
import coding_runner
from router_runtime import tools, Runtime
from job_journal import Journal

class RouterContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config={'execution_platform':'android'};self.inventory=tool_catalog.discover(self.config,device=False)
    def tearDown(self):self.temp.cleanup()
    def route(self,text,profile='BUILD',**options):return task_router.select(self.root,text,profile,self.inventory,{**self.config,**options})
    def test_five_fields_only_and_deterministic(self):
        a=self.route('Diagnose installed app crash');b=self.route('Diagnose installed app crash')
        self.assertEqual(a,b);self.assertEqual(set(a),{'workflow','adapters','required','checks','reason'})
        self.assertEqual(json.loads(json.dumps(a)),a)
    def test_first_match_priorities(self):
        for text,expected in [('Patch APK spelling','apk_modify'),('README security spelling','text_edit'),('security API crash','security'),('native backtrace API request','native'),('HTTP endpoint app crashes','device'),('Inspect APK','apk_inspect'),('Inspect files','inspect')]:
            with self.subTest(text=text):self.assertEqual(self.route(text)['workflow'],expected)
    def test_open_project_crash_and_api_do_not_override_source(self):
        (self.root/'test_code.py').write_text('import unittest\n')
        for text in ['Fix app crash at API endpoint','Repair installed app','Fix bug']:self.assertEqual(self.route(text)['workflow'],'source_fix')
        p=self.route('Build existing project');self.assertEqual(p['workflow'],'source_build');self.assertNotIn('change',p['required'])
    def test_builders_only_from_marker(self):
        (self.root/'test_code.py').write_text('import unittest\n')
        p=self.route('Fix Android Java bug');self.assertNotIn('gradle',p['adapters']);self.assertEqual(p['adapters'],['language_server','ast_grep'])
        (self.root/'gradlew').write_text('#!/bin/sh\n');self.assertIn('gradle',self.route('Fix bug')['adapters'])
    def test_ambiguous_source(self):
        p=self.route('Fix app crash',ambiguous_source=True);self.assertEqual(p['workflow'],'device');self.assertEqual(p['reason'],'ambiguous source')
    def test_signature_only_when_requested(self):
        self.assertEqual(self.route('Modify APK')['required'],['apk_rebuild'])
        self.assertIn('apk_signature',self.route('Modify and sign APK')['required'])
        self.assertNotIn('installation',self.route('Modify and sign APK')['required'])
    def test_model_has_no_verification_or_unrelated_edit_tools(self):
        for text in ['installed app crash','Inspect APK','Investigate API','security review','Inspect files','README typo']:
            p=self.route(text);names={t['name'] for t in tools(coding_runner.TOOLS,p,readonly=p['workflow']=='inspect')}
            self.assertNotIn('verify_goal',names);self.assertNotIn('write_file',names);self.assertNotIn('unified_patch',names)
            if p['workflow'] in {'device','api','inspect','apk_inspect','security'}:self.assertNotIn('edit_patch',names)
    def test_security_is_scan_not_fix(self):
        p=self.route('Review vulnerabilities','AUDIT');self.assertEqual(p['adapters'],['ast_grep']);self.assertEqual(p['required'],['security_scan'])
    def test_python_and_gradle_checks_are_explicit(self):
        (self.root/'pyproject.toml').write_text('[tool.pytest.ini_options]\n')
        self.assertEqual(self.route('Fix bug')['checks'][0]['argv'][:4],['python3','-m','unittest','discover'])
        (self.root/'gradlew').write_text('#!/bin/sh\n')
        self.assertEqual([c['argv'] for c in self.route('Fix bug')['checks']],[['./gradlew','--offline','assembleDebug'],['./gradlew','--offline','testDebugUnitTest']])
    def test_apk_inspection_requires_existing_decoded_artifact(self):
        p=task_router.execution_plan(self.root,'Inspect APK','BUILD',self.inventory,self.config)
        ws=coding_runner.Workspace(self.root,False);j=Journal(self.root/'jobs',{'id':'a'*32,'workspace':str(self.root),'objective':'Inspect APK','profile':'BUILD'})
        rt=Runtime(ws,j,p,self.inventory,self.config)
        rt.observe('read_file',{}, {'path':'x','sha256':'a'*64})
        self.assertFalse(task_router.evidence(j)['verified'])
        out=self.root/'decoded';out.mkdir()
        rt.observe('tool_adapter',{'tool':'apktool','operation':'decode'},{'success':True,'exit_code':0,'artifacts':[{'path':'decoded','exists':True}]})
        self.assertTrue(task_router.evidence(j)['verified'])

class RouterExecutionTests(unittest.TestCase):
    def test_structural_scan_report_is_not_a_repair(self):
        import tool_adapters
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);(root/'x.py').write_text('eval(input())\n')
            config={'execution_platform':'android','commands':{'ast_grep':[sys.executable,'fake.py']}}
            inv=tool_catalog.discover(config,device=False)
            plan=task_router.execution_plan(root,'security review','AUDIT',inv,config)
            ws=coding_runner.Workspace(root,True)
            j=Journal(root/'jobs',{'id':'a'*32,'workspace':str(root),'objective':'security review','profile':'AUDIT'})
            rt=Runtime(ws,j,plan,inv,config);ws.runtime=rt;ws.journal=j
            result={'success':True,'exit_code':0,'output':'[{"text":"eval(input())"}]'}
            with patch.object(tool_adapters,'run',return_value=result):
                observed=ws.invoke('tool_adapter',{'tool':'ast_grep','operation':'search','inputs':{'path':'x.py','pattern':'eval($X)','language':'python'}})
            self.assertTrue(task_router.evidence(j)['verified'])
            self.assertTrue((root/observed['artifacts'][0]['path']).is_file())
            self.assertEqual(j.data['patches'],[]);self.assertNotIn('security_validation',task_router.evidence(j)['passed'])
    def test_source_build_can_complete_without_edit(self):
        import test_backend
        fixture=test_backend.WorkerTests(methodName='test_generation_stop_retains_journal');fixture.setUp()
        try:
            (fixture.project/'total.py').write_text('def total(a,b):\n    return a+b\n')
            with patch.object(coding_runner,'complete',return_value={'tool_calls':[],'content':'Tests passed'}):
                state=coding_runner.run(test_backend.job(fixture.project,objective='Build the open project',profile='BUILD'))
            self.assertEqual(state['status'],'completed');self.assertEqual(state['patches'],[]);self.assertNotIn('change',state['required_verification'])
        finally:fixture.tearDown()

if __name__=='__main__':unittest.main()
