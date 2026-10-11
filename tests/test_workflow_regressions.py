import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import coding_runner as runner
import task_router
import tool_catalog
import tool_adapters
from router_runtime import Runtime
from job_journal import Journal
from offline_policy import command, local_url, LocalRedirects
import test_backend
from test_backend import job, inventory


class RoutingRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'test_ledger.py').write_text('import unittest\n')
    def tearDown(self):self.temp.cleanup()
    def test_installed_app_with_typo_beats_unrelated_source(self):
        for text in ['prettup app installed but not opening up. shuts down as soon as it runs up','PrettyUp app crashes','Diagnose an installed app']:
            p=task_router.select(self.root,text,'BUILD',inventory(),{})
            self.assertEqual(p['workflow'],'device');self.assertFalse(p['mutating']);self.assertFalse(p['source_preferred']);self.assertEqual(p['checks'],[])
    def test_unrelated_broken_project_does_not_block_device(self):
        (self.root/'package.json').write_text('{broken')
        p=task_router.select(self.root,'Prettyup app installed with typo in name; crashes','BUILD',inventory(),{})
        self.assertEqual(p['workflow'],'device')
    def test_explicit_source_target_remains_source_repair(self):
        p=task_router.select(self.root,'Fix typo in ledger.py only; unittest is failing','BUILD',inventory(),{})
        self.assertEqual(p['workflow'],'source_fix');self.assertNotIn('ui',p['adapters'])
    def test_prerequisite_failure_is_not_bug_reproduction(self):
        for code in [124,126,127]:
            j=Journal(self.root/str(code),job(self.root));j.data['plan']={'required':['reproduction','tests']}
            j.check('tests',{'exit_code':code},['python3','-m','unittest']);j.data['revision']=1
            j.check('tests',{'exit_code':0},['python3','-m','unittest'])
            self.assertIn('reproduction',task_router.evidence(j)['missing'])
    def test_verification_retries_after_latest_failure(self):
        ws=runner.Workspace(self.root,False);j=Journal(self.root/'jobs',job(self.root))
        argv=['python3','-m','unittest'];p={'checks':[{'kind':'tests','argv':argv}],'required':['tests'],'workflow':'source_fix','adapters':[],'custom_checks':True}
        rt=Runtime(ws,j,p,inventory(),{});ws.runtime=rt;ws.journal=j
        j.check('tests',{'exit_code':0},argv);j.check('tests',{'exit_code':1,'output':'AssertionError'},argv)
        with patch.object(ws,'invoke',return_value={'exit_code':0,'output':'Ran 1 test\nOK'}) as invoke:rt.verify(True)
        invoke.assert_called_once();self.assertEqual(j.data['checks'][-1]['output'],'AssertionError')
    def test_signature_evidence_requires_certificate(self):
        ws=runner.Workspace(self.root,False);j=Journal(self.root/'jobs',job(self.root));p={'required':['apk_signature'],'checks':[],'adapters':['apksigner','bundletool'],'workflow':'apk_modify'}
        rt=Runtime(ws,j,p,inventory(),{})
        for tool,op in [('apksigner','verify'),('bundletool','install')]:rt.observe('tool_adapter',{'tool':tool,'operation':op},{'success':True,'exit_code':0})
        self.assertIn('apk_signature',task_router.evidence(j)['missing'])
        rt.observe('tool_adapter',{'tool':'apksigner','operation':'verify'},{'success':True,'exit_code':0,'certificates_sha256':['a'*64]})
        self.assertTrue(task_router.evidence(j)['verified'])
    def test_nested_signing_and_install_certificate_is_recorded(self):
        ws=runner.Workspace(self.root,False);j=Journal(self.root/'jobs',job(self.root));p={'required':['apk_signature'],'checks':[],'adapters':['apksigner','bundletool'],'workflow':'apk_modify'}
        rt=Runtime(ws,j,p,inventory(),{})
        result={'success':True,'exit_code':0,'signature_verification':{'success':True,'certificates_sha256':['a'*64]}}
        rt.observe('tool_adapter',{'tool':'apksigner','operation':'sign'},result)
        self.assertTrue(task_router.evidence(j)['verified'])


class WorkerRegressionTests(unittest.TestCase):
    setUp=test_backend.WorkerTests.setUp
    tearDown=test_backend.WorkerTests.tearDown
    def test_repeated_rejected_command_stops_after_two(self):
        answer={'tool_calls':[{'name':'run_argv','arguments':{'argv':['prettup','app','open']}}],'content':''}
        with patch.object(runner,'complete',return_value=answer) as model:state=runner.run(job(self.project))
        self.assertEqual(state['status'],'blocked');self.assertEqual(model.call_count,2)
    def test_absent_baseline_not_shown_as_reproduced(self):
        (self.project/'total.py').write_text('def total(a,b):\n    return a+b\n')
        with patch.object(runner,'complete',return_value={'tool_calls':[],'content':'Done'}):state=runner.run(job(self.project))
        baseline=[a for a in state['activity'] if a['title']=='Checking the failure baseline']
        self.assertEqual(baseline[0]['status'],'failed');self.assertNotEqual(state['status'],'completed')
    def test_device_job_does_not_snapshot_unrelated_source(self):
        with patch.object(runner,'complete',return_value={'tool_calls':[],'content':'Unable to verify'}),patch.object(runner,'recovery_workspace',create=True):
            state=runner.run(job(self.project,objective='prettup app installed but not opening up',profile='BUILD'))
        self.assertEqual(state['workflow'],'device');self.assertEqual(state['workspace'],str(self.project));self.assertEqual(state['recovery']['mode'],'read_only')


class OfflineGuardTests(unittest.TestCase):
    def test_fetches_rejected(self):
        for argv in [['git','fetch'],['git','clone','https://example.com/x'],['cargo','build'],['./gradlew','test'],['sh','./gradlew','test'],['npm','ci'],['python3','-m','pip','install','x'],['sdkmanager','x'],['curl','https://example.com']]:
            with self.subTest(argv=argv),self.assertRaisesRegex(ValueError,'Offline'):command(argv)
    def test_cached_commands_allowed(self):
        for argv in [['git','diff'],['cargo','build','--offline'],['sh','./gradlew','--offline','test'],['npm','ci','--offline'],['python3','-m','unittest','discover'],['python3','-m','pip','install','--no-index','--find-links','cache','x']]:command(argv)
    def test_only_loopback_urls(self):
        for url in ['http://127.0.0.1:8000','http://[::1]:8000','http://localhost']:self.assertTrue(local_url(url))
        for url in ['https://example.com','http://192.168.8.1','http://localhost.evil.test']:self.assertFalse(local_url(url))
    def test_redirect_cannot_escape_offline(self):
        with self.assertRaisesRegex(ValueError,'redirect'):LocalRedirects().redirect_request(None,None,302,'',{},'https://example.com')
    def test_runtime_refuses_network_before_subprocess(self):
        with tempfile.TemporaryDirectory() as root:
            ws=runner.Workspace(root,False);ws.runtime=type('Config',(),{'config':{'offline':True}})()
            with patch.object(runner.subprocess,'Popen') as spawn,self.assertRaisesRegex(ValueError,'Offline'):
                ws.command(['git','fetch'])
            spawn.assert_not_called()
    def test_source_discovery_does_not_contact_remote_services_offline(self):
        import source_lookup
        with tempfile.TemporaryDirectory() as root,patch.object(source_lookup,'github_repos') as github,patch.object(source_lookup,'cloudflare_projects') as cloud:
            source_lookup.acquire('prettup app installed but crashes',root,config={'offline':True},device=None)
            github.assert_not_called();cloud.assert_not_called()
    def test_remote_http_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as root:
            ws=runner.Workspace(root,False)
            with patch.object(tool_adapters,'_local') as local,self.assertRaisesRegex(ValueError,'Offline'):
                tool_adapters.invoke(ws,'http','request',{'url':'https://example.com'},config={'schema':1,'offline':True})
            local.assert_not_called()

if __name__=='__main__':unittest.main()
