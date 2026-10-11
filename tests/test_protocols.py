import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE));sys.path.insert(0,str(BASE/'backend'))
import setup_tools
import tool_adapters
import tool_catalog
import task_router
import remote_tools
from coding_runner import Workspace
from job_journal import Journal,fingerprint
from router_runtime import Runtime
from session_store import SessionStore


class LanguageProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'code.py').write_text('x = 1\n')
        self.ws=Workspace(self.root,False);self.config={'language_servers':{'python':[sys.executable,str(BASE/'tests/fixtures/lsp_server.py')]}}
    def tearDown(self):self.temp.cleanup()
    def test_definition_and_reference_frames(self):
        for operation in ('definition','references'):
            result=tool_adapters.invoke(self.ws,'language_server',operation,{'path':'code.py','line':2,'column':3},config=self.config)
            self.assertTrue(result['success']);self.assertEqual(result['locations'][0]['range']['start'],{'line':1,'character':2})
    def test_diagnostics_and_unverified_timeout(self):
        result=tool_adapters.invoke(self.ws,'language_server','diagnostics',{'path':'code.py'},config=self.config)
        self.assertEqual(result['diagnostics'][0]['message'],'observed diagnostic')
        (self.root/'code.py').write_text('no-diagnostics\n')
        with self.assertRaises(TimeoutError):tool_adapters.invoke(self.ws,'language_server','diagnostics',{'path':'code.py'},timeout=1,config=self.config)
    def test_missing_language_server(self):
        with self.assertRaises(ValueError):tool_adapters.invoke(self.ws,'language_server','definition',{'path':'code.py'},config={})


class ProvisioningTests(unittest.TestCase):
    def test_configured_language_servers_are_not_reinstalled(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);target=root/'backend';target.mkdir();calls=[]
            config={'schema':1,'commands':{},'language_servers':{'typescript':['/custom/ts','--stdio'],'javascript':['/custom/ts','--stdio'],'python':['/custom/python-lsp']}}
            (target/'tools.json').write_text(json.dumps(config))
            with patch.object(setup_tools.shutil,'which',side_effect=lambda n:None if n in {'pylsp','typescript-language-server'} else '/available/'+n):
                setup_tools.install_tools(target,['lsp'],lambda *a:calls.append(a),root/'prefix')
            self.assertEqual(calls,[]);self.assertEqual(json.loads((target/'tools.json').read_text())['language_servers'],config['language_servers'])
    def test_existing_commands_are_skipped(self):
        calls=[]
        with patch.object(setup_tools.shutil,'which',return_value='/working/tool'):
            self.assertEqual(setup_tools.ensure_packages(['git','ripgrep','openjdk-21'],lambda *a:calls.append(a)),[])
        self.assertEqual(calls,[])
    def test_only_missing_packages_are_installed(self):
        calls=[]
        with patch.object(setup_tools.shutil,'which',side_effect=lambda n:None if n in {'rg','javac'} else '/working/'+n):
            installed=setup_tools.ensure_packages(['git','ripgrep','openjdk-21','ripgrep'],lambda *a:calls.append(a))
        self.assertEqual(installed,['ripgrep','openjdk-21']);self.assertEqual(calls,[('pkg','install','-y','ripgrep','openjdk-21')])
    def test_archive_checksum_and_cached_download(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'tool.jar';p.write_bytes(b'trusted');entry={'file':p.name,'size':7,'sha256':fingerprint(p),'url':'https://unused.example/tool'}
            with patch.object(setup_tools.urllib.request,'urlopen') as network:self.assertEqual(setup_tools.download(entry,root),p);network.assert_not_called()
            p.write_bytes(b'tampered')
            with self.assertRaises(ValueError):setup_tools.download(entry,root)
    def test_zip_traversal_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);archive=root/'unsafe.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape','bad')
            with self.assertRaises(ValueError):setup_tools.extract(archive,root/'output')
            with zipfile.ZipFile(archive,'w') as z:
                entry=zipfile.ZipInfo('link');entry.external_attr=0o120777<<16;z.writestr(entry,'../outside')
            with self.assertRaises(ValueError):setup_tools.extract(archive,root/'output')
    def test_existing_private_configuration_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);target=root/'backend';target.mkdir();config={'schema':1,'commands':{},'signing':{'alias':'existing'},'remote':{'enabled':False}}
            (target/'tools.json').write_text(json.dumps(config))
            setup_tools.install_tools(target,[],lambda *a:None,root/'prefix')
            self.assertEqual(json.loads((target/'tools.json').read_text())['signing']['alias'],'existing')


class RemoteProtocolTests(unittest.TestCase):
    def test_remote_worker_capabilities_and_private_workspace(self):
        with tempfile.TemporaryDirectory() as t:
            env={**os.environ,'QODER_REMOTE_ROOT':t};worker=[sys.executable,str(BASE/'backend/remote_worker.py')]
            caps=subprocess.run(worker+['--capabilities'],capture_output=True,text=True,env=env,check=True)
            import tool_catalog
            if tool_catalog.android_scope({}):self.assertNotIn('codeql',json.loads(caps.stdout)['tools'])
            else:self.assertIn('codeql',json.loads(caps.stdout)['tools'])
            identifier='a'*32
            prepared=subprocess.run(worker+['--prepare',identifier],capture_output=True,text=True,env=env,check=True)
            path=Path(json.loads(prepared.stdout)['workspace']);self.assertEqual(path.parent,Path(t))
            self.assertEqual(path.stat().st_mode&0o777,0o700)
            cancelled=subprocess.run(worker+['--cancel',identifier],capture_output=True,text=True,env=env,check=True)
            self.assertTrue(json.loads(cancelled.stdout)['cancel_requested']);self.assertTrue((path/'.cancel').exists())
    def test_remote_paths_and_host_injection_rejected(self):
        with self.assertRaises(ValueError):remote_tools.settings({'remote':{'enabled':True,'host':'host; touch /tmp/bad','worker':['python3','worker.py']}})
        with tempfile.TemporaryDirectory() as t:
            result=subprocess.run([sys.executable,str(BASE/'backend/remote_worker.py'),'--prepare','../escape'],capture_output=True,text=True,env={**os.environ,'QODER_REMOTE_ROOT':t})
            self.assertNotEqual(result.returncode,0);self.assertIn('Invalid',result.stdout)
    def test_remote_artifact_checksum_and_transport(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ws=Workspace(root,False);payload=b'{"observed":true}';digest=hashlib.sha256(payload).hexdigest();calls=[]
            def command(argv,**kwargs):
                calls.append(argv)
                if argv[0]=='rsync':
                    if argv[-2].startswith('builder:'):
                        destination=Path(argv[-1]);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(payload)
                    return {'exit_code':0,'output':''}
                if '--capabilities' in argv[-1]:return {'exit_code':0,'output':json.dumps({'tools':{'semgrep':{'installed':True}},'access':{}})}
                if '--prepare' in argv[-1]:return {'exit_code':0,'output':json.dumps({'workspace':'/srv/jobs/'+'a'*32})}
                return {'exit_code':0,'output':json.dumps({'exit_code':0,'success':True,'artifacts':[{'path':'report.json','exists':True,'sha256':digest}]})}
            config={'remote':{'enabled':True,'host':'builder','worker':['python3','worker.py'],'tools':['semgrep']}}
            with patch.object(remote_tools.shutil,'which',return_value='/working/tool'),patch.object(ws,'command',side_effect=command):r=remote_tools.invoke_remote(ws,'semgrep','scan',{'rules':'rules.yml'},120,config)
            self.assertEqual(r['location'],'remote');self.assertEqual(fingerprint(root/r['artifacts'][0]['path']),digest)
            self.assertIn('StrictHostKeyChecking=yes',calls[0]);self.assertTrue(any('--exclude' in c for c in calls))


class VerificationTests(unittest.TestCase):
    def test_unsigned_rebuild_removes_old_signature_files(self):
        with tempfile.TemporaryDirectory() as t:
            apk=Path(t)/'rebuilt.apk'
            with zipfile.ZipFile(apk,'w') as z:
                z.writestr('classes.dex',b'dex-code');z.writestr('META-INF/OLD.RSA',b'stale-signature');z.writestr('META-INF/OLD.SF',b'stale');z.writestr('META-INF/services/example',b'provider')
            tool_adapters.strip_apk_signatures(apk)
            with zipfile.ZipFile(apk) as z:
                self.assertNotIn('META-INF/OLD.RSA',z.namelist());self.assertNotIn('META-INF/OLD.SF',z.namelist());self.assertEqual(z.read('classes.dex'),b'dex-code');self.assertEqual(z.read('META-INF/services/example'),b'provider')
    @unittest.skipUnless(__import__('shutil').which('node') and __import__('shutil').which('npm'),'Node/npm unavailable')
    def test_real_node_repair_build_and_artifact_refresh(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'package.json').write_text(json.dumps({'type':'module','scripts':{'build':'node build.js','test':'node --test test_total.test.js'}}))
            (root/'total.js').write_text('export const total = (a,b) => a-b;\n')
            (root/'build.js').write_text("import {mkdirSync,writeFileSync} from 'node:fs'; import {total} from './total.js'; mkdirSync('dist',{recursive:true});writeFileSync('dist/index.html',String(total(2,3)));\n")
            (root/'test_total.test.js').write_text("import test from 'node:test';import assert from 'node:assert/strict';import {total} from './total.js';test('sum',()=>assert.equal(total(2,3),5));\n")
            job={'id':'a'*32,'workspace':str(root),'objective':'Repair total bug','profile':'FIX'};j=Journal(root/'jobs',job)
            caps=tool_catalog.discover(device=False);plan=task_router.execution_plan(root,job['objective'],'FIX',caps,{})
            ws=Workspace(root,False);runtime=Runtime(ws,j,plan,caps,{});ws.runtime=runtime;ws.journal=j
            self.assertFalse(runtime.verify()['verified'])
            ws.invoke('edit_patch',{'path':'total.js','old_text':'a-b','new_text':'a+b','expected_sha256':fingerprint(root/'total.js')})
            result=runtime.verify();self.assertTrue(result['verified']);self.assertEqual((root/'dist/index.html').read_text(),'5')
            self.assertTrue(any(a['path']=='dist/index.html' for a in result['artifacts']));j.check_files()
            self.assertTrue(runtime.verify()['verified'])
    def test_install_preserves_original_and_blocks_different_certificate(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'new.apk').write_bytes(b'new');ws=Workspace(root,False);calls=[]
            def run(workspace,argv,timeout,**kwargs):
                calls.append(argv)
                if argv[-1]=='devices':output='List of devices attached\nphone\tdevice\n'
                elif 'badging' in argv:output="package: name='example.app'"
                elif 'path' in argv:output='package:/data/app/example/base.apk\n'
                elif 'pull' in argv:(root/argv[-1]).write_bytes(b'original');output='pulled'
                else:output='Success'
                return {'exit_code':0,'success':True,'output':output,'argv':argv}
            certs=[{'success':True,'certificates_sha256':['a'*64]},{'success':True,'certificates_sha256':['b'*64]}]
            with patch.object(tool_adapters,'run',side_effect=run),patch.object(tool_adapters,'certificate',side_effect=certs):
                with self.assertRaisesRegex(ValueError,'certificates differ'):tool_adapters.device_operation(ws,'adb','install',{'path':'new.apk','package':'example.app'},120,{},['adb'])
            self.assertTrue(any(p.read_bytes()==b'original' for p in root.rglob('*original.apk')))
            self.assertFalse(any('install' in a or 'uninstall' in a for a in calls))
    def test_changed_tests_cannot_fake_reproduction(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'test_total.py').write_text('assert total(2,3)==5\n')
            job={'id':'a'*32,'workspace':str(root),'objective':'Fix total','profile':'FIX'};j=Journal(root/'jobs',job);j.data['plan']={'required':['tests','reproduction']}
            argv=['pytest','test_total.py'];j.check('tests',{'exit_code':1},argv);j.data['revision']=1
            (root/'test_total.py').write_text('assert True\n');j.check('tests',{'exit_code':0},argv)
            self.assertIn('reproduction',task_router.evidence(j)['missing'])
    def test_document_edit_uses_validation_without_project_tests(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'README.md';p.write_text('tyop\n');ws=Workspace(root,False)
            job={'id':'a'*32,'workspace':str(root),'objective':'Fix README typo','profile':'FIX'};j=Journal(root/'jobs',job)
            caps=tool_catalog.discover(device=False);plan=task_router.execution_plan(root,job['objective'],'FIX',caps,{})
            self.assertEqual(plan['required'],['change','text_validation']);runtime=Runtime(ws,j,plan,caps,{});ws.runtime=runtime;ws.journal=j
            ws.invoke('edit_patch',{'path':'README.md','old_text':'tyop','new_text':'typo','expected_sha256':fingerprint(p)})
            self.assertFalse(runtime.verify()['verified'])
            ws.invoke('read_file',{'path':'README.md'})
            self.assertTrue(runtime.verify()['verified'])
    def test_unchanged_and_no_tests_are_not_success(self):
        self.assertFalse(task_router.test_result({'exit_code':0,'output':'# tests 0\n# pass 0'})['success'])
    def test_native_creation_and_source_repair_routes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);caps=tool_catalog.discover(device=False)
            (root/'CMakeLists.txt').write_text('project(sample)\n')
            self.assertEqual(task_router.execution_plan(root,'Create a native Android app','BUILD',caps,{})['workflow'],'source_build')
            (root/'CMakeLists.txt').write_text('project(sample)\n')
            plan=task_router.execution_plan(root,'Fix native parser crash','FIX',caps,{})
            self.assertEqual(plan['workflow'],'source_fix');self.assertIn('cmake',plan['adapters'])
    def test_reserve_recovers_interrupted_job_automatically(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);store=SessionStore(threading.Lock(),root);sid=store.manage({'action':'new'})['id'];project=root/'project';project.mkdir();identifier='a'*32
            previous={'id':identifier,'status':'interrupted','objective':'Repair','workspace':str(project),'profile':'FIX'}
            store.get(sid)['jobs']=[previous];(root/'jobs').mkdir();(root/'jobs'/(identifier+'.journal.json')).write_text('{}')
            store.reserve(sid,{'workspace':str(project),'objective':'Repair','profile':'FIX','route':'phone-code'})
            self.assertEqual(store.active[sid]['resume_from'],identifier)
    def test_restart_retains_finished_worker_result(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);identifier='a'*32;sid='b'*32
            (root/'sessions').mkdir();(root/'jobs').mkdir()
            (root/'sessions'/(sid+'.json')).write_text(json.dumps({'id':sid,'jobs':[],'current':{'id':identifier,'status':'running'}}))
            (root/'jobs'/(identifier+'.json')).write_text(json.dumps({'id':identifier,'status':'completed','verification':'GOAL_VERIFIED','result':'actual result'}))
            store=SessionStore(threading.Lock(),root)
            self.assertEqual(store.get(sid)['jobs'][-1]['status'],'completed');self.assertEqual(store.get(sid)['jobs'][-1]['result'],'actual result')


if __name__=='__main__':unittest.main()
