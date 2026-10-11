import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE));sys.path.insert(0,str(BASE/'backend'))
import install_offline_tools as offline
import task_router
import tool_adapters as adapters
import tool_catalog
from coding_runner import Workspace


class AndroidAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.ws=Workspace(self.root,False)
    def tearDown(self):self.temp.cleanup()
    def test_instrumentation_checks_nonempty_pass_and_embedded_failures(self):
        inputs={'framework':'instrumentation','runner':'com.example.test/androidx.test.runner.AndroidJUnitRunner'}
        for output,expected in [('OK (3 tests)',True),('OK (0 tests)',False),('FAILURES!!!\nOK (1 test)',False),('INSTRUMENTATION_FAILED: denied',False),('INSTRUMENTATION_STATUS_CODE: -1\nOK (1 test)',False)]:
            with self.subTest(output=output),patch.object(adapters,'android_shell',return_value={'exit_code':0,'output':output}):
                result=adapters.invoke(self.ws,'ui','test',inputs,config={'schema':1})
                self.assertEqual(result['success'],expected)
    def test_instrumentation_requires_authorized_device(self):
        config={'commands':{'adb':[sys.executable,'fake_adb.py']}}
        with patch.object(adapters,'run',return_value={'exit_code':0,'output':'List of devices attached\nx\tunauthorized\n'}):
            with self.assertRaisesRegex(ValueError,'authorized'):adapters.android_shell(self.ws,'adb',['am','instrument'],10,config)
    def test_android_ui_defaults_to_native_instrumentation(self):
        inputs={'runner':'com.example.test/androidx.test.runner.AndroidJUnitRunner'}
        with patch.object(adapters,'android_shell',return_value={'exit_code':0,'output':'OK (1 test)'}) as shell:
            result=adapters.invoke(self.ws,'ui','test',inputs,config={'execution_platform':'android'})
            self.assertTrue(result['success']);self.assertEqual(shell.call_args[0][2][:3],['am','instrument','-w'])
    def test_native_frida_requires_pid_and_actual_observation(self):
        (self.root/'observe.js').write_text('console.log("observed target");')
        config={'commands':{'frida':[sys.executable,'native-frida.py']},'frida':{'mode':'inject'}}
        with self.assertRaisesRegex(ValueError,'positive pid'):adapters.invoke(self.ws,'frida','instrument',{'script':'observe.js','pid':0},config=config)
        with patch.object(adapters,'run',return_value={'exit_code':1,'success':False,'output':'Permission denied'}) as call:
            result=adapters.invoke(self.ws,'frida','instrument',{'script':'observe.js','pid':123,'expected_text':'observed target'},config=config)
            self.assertFalse(result['success']);self.assertFalse(result['observation_matched']);self.assertIn('123',call.call_args[0][1])
    def test_headless_zap_requires_successful_report(self):
        config={'commands':{'zap':[sys.executable,'fake-zap.py']},'zap':{'mode':'headless'}}
        def command(ws,argv,timeout,env=None):
            plan=Path(argv[argv.index('-autorun')+1]);data=json.loads(plan.read_text())
            self.assertNotIn('activeScan',[job['type'] for job in data['jobs']])
            (plan.parent/'report.json').write_text('{"site":[{"alerts":[{"name":"missing-header"}]}]}')
            return {'exit_code':0,'success':True,'output':'plan completed'}
        with patch.object(adapters,'run',side_effect=command):
            result=adapters.invoke(self.ws,'zap','scan',{'url':'http://127.0.0.1:9000'},config=config)
            self.assertTrue(result['success']);self.assertEqual(result['finding_count'],1)
        with patch.object(adapters,'run',return_value={'exit_code':0,'success':True,'output':'no report'}):
            result=adapters.invoke(self.ws,'zap','scan',{'url':'http://127.0.0.1:9000'},config=config)
            # No security report means a scan cannot establish verification.
            self.assertFalse(result['success'])
    def test_android_router_excludes_desktop_analyzers(self):
        config={'execution_platform':'android','commands':{}}
        inventory=tool_catalog.discover(config,device=False)
        for goal in ['Analyse native crash','Review APK security','Review web service security']:
            plan=task_router.execution_plan(self.root,goal,'AUDIT' if 'security' in goal else 'BUILD',inventory,config)
            self.assertFalse(set(plan['adapters'])&{'ghidra','semgrep','codeql','mobsf'})
    def test_tool_environment_preserves_termux_path(self):
        result=self.ws.command([sys.executable,'-c','import os; print(bool(os.environ.get("PATH")), os.environ["QODER_TOOL_PROBE"])'],env={'QODER_TOOL_PROBE':'present'})
        self.assertEqual(result['exit_code'],0);self.assertEqual(result['output'].strip(),'True present')
    def test_android_scope_keeps_configured_remote_adapters_local(self):
        config={'execution_platform':'android','remote':{'enabled':True,'tools':['zap'],'prefer':['zap']},'commands':{'zap':[sys.executable,'local-zap.py']}}
        with patch.object(adapters,'_local',return_value={'exit_code':1,'success':False}) as local:
            result=adapters.invoke(self.ws,'zap','scan',{'url':'http://127.0.0.1'},config=config)
            self.assertEqual(result['location'],'local');local.assert_called_once()
    def test_termux_enforces_scope_for_old_configuration(self):
        config={'schema':1,'commands':{},'remote':{'enabled':True,'tools':['codeql']}}
        with patch.dict('os.environ',{'PREFIX':'/data/data/com.termux/files/usr'}):
            inventory=tool_catalog.discover(config,device=False)
            self.assertNotIn('codeql',inventory['tools']);self.assertEqual(inventory['access']['remote'],'disabled_android_scope')
            result=adapters.invoke(self.ws,'codeql','database',{'language':'javascript'},config=config)
            self.assertFalse(result['success']);self.assertTrue(result['unsupported_platform'])
            plan=task_router.execution_plan(self.root,'Review web service security','AUDIT',inventory,config)
            self.assertEqual(plan['adapters'],['ast_grep'])
    def test_all_requested_adapter_groups_are_exposed(self):
        inventory=tool_catalog.public_capabilities(tool_catalog.discover({'execution_platform':'android'},device=False))
        self.assertEqual(set(inventory['adapter_groups']),{'code_intelligence','file_editing','version_control','command_execution','android_build','web_pwa_build','device_diagnostics','apk_analysis_editing','runtime_inspection','network_inspection','security_testing','verification'})
        self.assertIn('unified_patch',inventory['adapter_groups']['file_editing'])
        self.assertIn('libfuzzer',inventory['adapter_groups']['verification'])


class OfflinePackageTests(unittest.TestCase):
    def test_language_cache_rejects_foreign_native_dependency(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);lock={'packages':{'':{'dependencies':{'typescript':'5.9.3'}}}}
            (root/'package-lock.json').write_text(json.dumps(lock));offline.check_npm_bundle(root)
            lock['packages']['node_modules/native-tool']={'os':['linux'],'cpu':['x64'],'optional':True}
            (root/'package-lock.json').write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError,'platform dependency'):offline.check_npm_bundle(root)
    def test_download_verification_rejects_tampered_file(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);file=root/'package';file.write_bytes(b'good')
            (root/'inventory.json').write_text(json.dumps({'files':[{'path':'package','bytes':4,'sha256':offline.sha256(file)}]}))
            offline.verify(root);file.write_bytes(b'evil')
            with self.assertRaisesRegex(ValueError,'checksum'):offline.verify(root)
    def test_existing_commands_are_skipped(self):
        with patch.object(offline.shutil,'which',return_value='/existing/tool'):self.assertEqual(offline.missing_packages(),[])

if __name__=='__main__':unittest.main()
