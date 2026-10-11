import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'backend'))
import coding_runner as runner
import engineering_tools
import source_lookup
import tool_adapters
import tool_catalog
import task_router
from job_journal import Journal,recovery_workspace,fingerprint
from router_runtime import Runtime,tools
from session_store import SessionStore


def inventory():return tool_catalog.discover({'schema':1,'commands':{},'remote':{'enabled':False}},device=False)
def job(root,identifier='a'*32,objective='Repair the total bug',profile='FIX'):
    return {'id':identifier,'workspace':str(root),'objective':objective,'profile':profile,'route':'phone-code'}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.ws=runner.Workspace(self.root,False)
    def tearDown(self):self.temp.cleanup()
    def test_escape_and_private_files(self):
        for name in ['../outside','/tmp/outside','.git/config','.env','key.pem','runtime/inference.key']:
            with self.subTest(name=name),self.assertRaises(ValueError):self.ws.file(name)
        (self.root/'link').symlink_to('/tmp')
        with self.assertRaises(ValueError):self.ws.file('link/elsewhere')
    def test_search_lines_and_no_matches(self):
        (self.root/'a.py').write_text('first\nneedle()\n')
        result=self.ws.invoke('code_search',{'pattern':'needle'})
        self.assertEqual(result['matches'][0]['line'],2)
        self.assertEqual(self.ws.invoke('code_search',{'pattern':'absent'})['exit_code'],0)
    def test_checksum_and_ambiguous_patch(self):
        path=self.root/'source.py';path.write_text('return 1\nreturn 1\n')
        with self.assertRaises(ValueError):self.ws.invoke('edit_patch',{'path':'source.py','old_text':'return 1','new_text':'return 2'})
        path.write_text('return 1\n');path.chmod(0o755)
        with self.assertRaises(ValueError):self.ws.invoke('edit_patch',{'path':'source.py','old_text':'return 1','new_text':'return 2','expected_sha256':'0'*64})
        result=self.ws.invoke('edit_patch',{'path':'source.py','old_text':'return 1','new_text':'return 2','expected_sha256':fingerprint(path)})
        self.assertIn('+return 2',result['diff']);self.assertEqual(path.stat().st_mode&0o777,0o755)
    def test_unified_patch_preview_apply_and_stale(self):
        p=self.root/'a.txt';p.write_text('before\n')
        args={'patch':'--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-before\n+after\n','expected_sha256':{'a.txt':fingerprint(p)},'preview':True}
        self.assertEqual(self.ws.invoke('unified_patch',args)['exit_code'],0);self.assertEqual(p.read_text(),'before\n')
        args['preview']=False;self.assertEqual(self.ws.invoke('unified_patch',args)['exit_code'],0)
        with self.assertRaises(ValueError):self.ws.invoke('unified_patch',args)
    def test_unified_patch_rejects_escaping_extra_header(self):
        with self.assertRaises(ValueError):self.ws.invoke('unified_patch',{'patch':'--- a/../outside\n+++ b/../outside\n@@ -0,0 +1 @@\n+bad\n','expected_sha256':{}})
    def test_atomic_write_and_backup(self):
        p=self.root/'a.py';p.write_text('old\n');journal=Journal(self.root/'jobs',job(self.root));self.ws.journal=journal
        self.ws.invoke('write_file',{'path':'a.py','content':'new\n'})
        self.assertEqual(Path(journal.data['patches'][0]['backup']).read_text(),'old\n')
        self.assertEqual(journal.data['revision'],1)
        self.ws.invoke('write_file',{'path':'a.py','content':'new\n'});self.assertEqual(journal.data['revision'],1)
    def test_readonly_changes_blocked(self):
        ws=runner.Workspace(self.root,True);(self.root/'a').write_text('old')
        with self.assertRaises(ValueError):ws.invoke('edit_patch',{'path':'a','old_text':'old','new_text':'new'})
        with self.assertRaises(ValueError):ws.invoke('write_file',{'path':'a','content':'new'})
    def test_command_validation(self):
        for argv in [['bash','-c','echo bad'],['git','reset','--hard'],['python3','../outside.py'],['sh','/tmp/outside'],['node','--eval','1'],['python3','bad\0path']]:
            with self.subTest(argv=argv),self.assertRaises(ValueError):self.ws.invoke('run_argv',{'argv':argv})
    def test_timeout_and_output_capture(self):
        (self.root/'wait.py').write_text('import time\nprint("started",flush=True)\ntime.sleep(30)\n')
        result=self.ws.command([sys.executable,'wait.py'],timeout=1)
        self.assertEqual(result['exit_code'],124);self.assertIn('started',result['output'])
    def test_cancel_command_group(self):
        (self.root/'wait.py').write_text('import subprocess,time\nsubprocess.Popen(["sleep","30"])\ntime.sleep(30)\n')
        calls=0
        def cancel():
            nonlocal calls;calls+=1
            if calls>3:raise runner.Cancelled()
        self.ws.cancel=cancel
        started=time.monotonic()
        with self.assertRaises(runner.Cancelled):self.ws.command([sys.executable,'wait.py'])
        self.assertLess(time.monotonic()-started,2)
    def test_diagnostics_real_syntax_error(self):
        (self.root/'bad.py').write_text('def broken(:\n')
        result=self.ws.invoke('diagnose',{'argv':['python3','-m','py_compile','bad.py']})
        self.assertNotEqual(result['exit_code'],0);self.assertTrue(result['diagnostics'])


class RouterTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.caps=inventory()
    def tearDown(self):self.temp.cleanup()
    def plan(self,text,profile='BUILD'):return task_router.select(self.root,text,profile,self.caps,{})
    def test_source_preferred_over_incidental_apk(self):
        (self.root/'package.json').write_text(json.dumps({'scripts':{'test':'node --test','build':'node build.js'}}))
        p=self.plan('Repair a source bug affecting APK export')
        self.assertEqual(p['workflow'],'source_fix');self.assertIn('node',p['adapters'])
    def test_explicit_apk_modification_needs_install_and_function(self):
        p=self.plan('Modify an existing APK');self.assertEqual(p['workflow'],'apk_modify')
        self.assertEqual(p['required'],['apk_rebuild','apk_signature','installation','functional'])
    def test_unsigned_scope_and_inspection(self):
        self.assertEqual(self.plan('Rebuild the APK unsigned')['required'],['apk_rebuild'])
        self.assertEqual(self.plan('Inspect this APK')['workflow'],'apk_inspect')
    def test_device_api_native_security_routes(self):
        for objective,route in [('Diagnose an installed app','device'),('Investigate an API request','api'),('Analyse native library','native'),('Review security','security')]:
            with self.subTest(objective=objective):self.assertEqual(self.plan(objective)['workflow'],route)
    def test_conflicting_locks_and_declared_manager(self):
        p=self.root/'package.json';p.write_text('{}');(self.root/'yarn.lock').touch();(self.root/'pnpm-lock.yaml').touch()
        with self.assertRaises(ValueError):task_router.project(self.root)
        p.write_text('{"packageManager":"pnpm@10.0.0"}');self.assertEqual(task_router.project(self.root)['manager'],'pnpm')
    def test_empty_tests_not_verification(self):
        for output in ['Ran 0 tests in 0.001s\nOK','no tests ran','Running 0 tests','> Task :app:testDebugUnitTest NO-SOURCE']:
            self.assertFalse(task_router.test_result({'exit_code':0,'output':output})['success'])
    def test_failed_check_invalidates_prior_pass(self):
        journal=Journal(self.root/'jobs',job(self.root));journal.data['plan']={'required':['tests']}
        journal.check('tests',{'exit_code':0},['python3','-m','unittest'])
        journal.check('tests',{'exit_code':1},['python3','-m','unittest'])
        self.assertFalse(task_router.evidence(journal)['verified'])
    def test_reproduction_requires_same_check_after_change(self):
        j=Journal(self.root/'jobs',job(self.root));j.data['plan']={'required':['tests','reproduction']}
        j.check('tests',{'exit_code':1},['pytest','test_bug.py']);j.data['revision']=1
        j.check('tests',{'exit_code':0},['pytest','test_other.py']);self.assertFalse(task_router.evidence(j)['verified'])
        j.check('tests',{'exit_code':0},['pytest','test_bug.py']);self.assertTrue(task_router.evidence(j)['verified'])
    def test_launch_without_source_is_device_not_fake_source_fix(self):
        text='i have an app prettyup, it does not load. crashes upon opening. i want to fix it. built from opensource'
        p=self.plan(text)
        self.assertEqual(p['workflow'],'device')
        self.assertEqual(p['required'],['device_inspection','functional'])
        self.assertNotIn('tests',p['required']);self.assertNotIn('change',p['required']);self.assertNotIn('reproduction',p['required'])
    def test_launch_with_source_stays_source_fix(self):
        (self.root/'package.json').write_text(json.dumps({'scripts':{'test':'node --test'}}))
        p=task_router.select(self.root,'the prettyup app crashes upon opening. fix it','BUILD',self.caps,{'target_source_confirmed':True})
        self.assertEqual(p['workflow'],'source_fix');self.assertIn('reproduction',p['required']);self.assertIn('tests',p['required'])
    def test_locate_named_nested_app(self):
        app=self.root/'prettyup';app.mkdir();(app/'package.json').write_text(json.dumps({'scripts':{'test':'node --test'}}))
        other=self.root/'other';other.mkdir();(other/'package.json').write_text(json.dumps({'scripts':{'test':'node --test'}}))
        self.assertEqual(task_router.locate_project(self.root,'i have an app prettyup, it crashes upon opening'),app)
    def test_failure_brief_loads_cited_source_not_the_test(self):
        (self.root/'total.py').write_text('def total(a,b):\n    return a+b+1\n')
        (self.root/'tests').mkdir();(self.root/'tests'/'test_total.py').write_text('def test_total():\n    assert False\n')
        output='File "%s", line 2, in total\nFile "%s", line 2, in test_total\n'%(self.root/'total.py',self.root/'tests'/'test_total.py')
        brief=task_router.failure_brief(self.root, output)
        self.assertIn('total.py',brief);self.assertIn('return a+b+1',brief);self.assertNotIn('assert False',brief)
    def test_small_tool_surface(self):
        selected=tools(runner.TOOLS,self.plan('Create a Python app'))
        names={x['name'] for x in selected}
        self.assertNotIn('device_argv',names);self.assertNotIn('apk_tools',names);self.assertIn('verify_goal',names)


class JournalTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.project=self.root/'project';self.project.mkdir()
    def tearDown(self):self.temp.cleanup()
    def test_snapshot_retains_original_and_recovery_checksum(self):
        p=self.project/'code.py';p.write_text('old\n');ws=runner.Workspace(self.project,False);j=Journal(self.root/'jobs',job(self.project))
        recovery_workspace(ws,j,{});self.assertNotEqual(ws.root,self.project)
        ws.journal=j;ws.invoke('write_file',{'path':'code.py','content':'new\n'})
        self.assertEqual(p.read_text(),'old\n');j.data['status']='interrupted';j.save()
        resumed=Journal(self.root/'jobs',job(self.project,'b'*32),resume='a'*32)
        self.assertEqual(resumed.data['revision'],1)
        (ws.root/'code.py').write_text('external\n')
        with self.assertRaises(ValueError):Journal(self.root/'jobs',job(self.project,'c'*32),resume='a'*32)
    def test_git_worktree_keeps_dirty_and_untracked_files(self):
        subprocess.run(['git','init','-q',str(self.project)],check=True)
        p=self.project/'code.py';p.write_text('committed\n')
        subprocess.run(['git','-C',str(self.project),'add','code.py'],check=True)
        subprocess.run(['git','-C',str(self.project),'-c','user.name=Test','-c','user.email=test@local','commit','-qm','initial'],check=True)
        p.write_text('dirty\n');(self.project/'untracked.py').write_text('untracked\n')
        ws=runner.Workspace(self.project,False);j=Journal(self.root/'jobs',job(self.project));recovery=recovery_workspace(ws,j,{})
        self.assertEqual(recovery['mode'],'git_worktree');self.assertEqual((ws.root/'code.py').read_text(),'dirty\n')
        self.assertEqual((ws.root/'untracked.py').read_text(),'untracked\n');self.assertEqual(p.read_text(),'dirty\n')
        ws.journal=j;ws.invoke('write_file',{'path':'code.py','content':'repaired\n'});item=j.export_patch(ws)
        checked=subprocess.run(['git','apply','--check',str(ws.root/item['path'])],cwd=self.project,capture_output=True)
        self.assertEqual(checked.returncode,0,checked.stderr)
    def test_repeated_failures_and_pending_step(self):
        j=Journal(self.root/'jobs',job(self.project));args={'path':'missing'}
        for _ in range(2):j.begin('read_file',args);j.finish({'error':'missing'})
        self.assertEqual(j.repeated_failures('read_file',args),2)
        j.begin('edit_patch',args);j.data['status']='interrupted';j.save()
        resumed=Journal(self.root/'jobs',job(self.project,'b'*32),resume='a'*32)
        self.assertEqual(resumed.data['interrupted_operation']['tool'],'edit_patch')


class AdapterTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'project';self.root.mkdir();self.ws=runner.Workspace(self.root,False)
    def tearDown(self):self.temp.cleanup()
    def test_missing_tool_is_structured(self):
        with patch.object(tool_adapters,'command_for',return_value=None):r=tool_adapters.invoke(self.ws,'ghidra','analyze',{'path':'native.so'})
        self.assertEqual(r['exit_code'],127);self.assertTrue(r['missing_prerequisite']);self.assertFalse(r['success'])
    def test_system_sg_is_not_ast_grep(self):
        with patch.object(tool_catalog.shutil,'which',side_effect=lambda n:'/usr/bin/sg' if n=='sg' else None),patch.object(tool_catalog.subprocess,'run',return_value=argparse.Namespace(returncode=0,stdout='usage: sg group command')):
            self.assertIsNone(tool_catalog.command_for('ast_grep',{}))
    def test_alignment_before_signing_and_signature_verified(self):
        source=self.root/'input.apk';source.write_bytes(b'APK');key=self.root.parent/'private.keystore';key.write_bytes(b'key');password=self.root.parent/'password';password.write_text('test-passphrase-unique');password.chmod(0o600)
        calls=[]
        def command(argv,**kwargs):
            calls.append(argv)
            if 'sign' in argv:(self.root/argv[argv.index('--out')+1]).write_bytes(b'signed')
            output='Signer #1 certificate SHA-256 digest: '+'a'*64 if 'verify' in argv else ''
            return {'exit_code':0,'output':output,'argv':argv}
        config={'signing':{'keystore':str(key),'password_file':str(password),'alias':'personal'}}
        with patch.object(tool_adapters,'command_for',side_effect=lambda n,c:['zipalign'] if n=='zipalign' else ['apksigner']),patch.object(self.ws,'command',side_effect=command):
            result=tool_adapters.invoke(self.ws,'apksigner','sign',{'path':'input.apk','output':'signed.apk'},config=config)
        self.assertTrue(result['success']);self.assertIn('-c',calls[0]);self.assertIn('sign',calls[1]);self.assertIn('verify',calls[2]);self.assertNotIn('test-passphrase-unique',' '.join(calls[1]))
    def test_unaligned_apk_never_signed(self):
        (self.root/'input.apk').write_bytes(b'APK')
        with patch.object(tool_adapters,'command_for',side_effect=lambda n,c:[n]),patch.object(self.ws,'command',return_value={'exit_code':1,'output':'unaligned','argv':['zipalign']}) as command:
            with self.assertRaises(ValueError):tool_adapters.invoke(self.ws,'apksigner','sign',{'path':'input.apk'},config={})
            self.assertEqual(command.call_count,1)
    def test_http_replay_real_server(self):
        class Handler(BaseHTTPRequestHandler):
            status=500
            def log_message(self,*a):pass
            def do_GET(self):self.send_response(type(self).status);self.end_headers();self.wfile.write(b'observed')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            args={'url':'http://127.0.0.1:'+str(server.server_port)+'/test','expected_status':200,'expected_text':'observed'}
            first=tool_adapters.invoke(self.ws,'http','request',args);self.assertFalse(first['success']);self.assertEqual(first['status_code'],500)
            Handler.status=200;second=tool_adapters.invoke(self.ws,'http','request',args);self.assertTrue(second['success'])
            self.assertEqual(first['request_fingerprint'],second['request_fingerprint'])
        finally:server.shutdown();server.server_close();thread.join()
    def test_security_scan_parses_artifact_and_findings(self):
        (self.root/'rules.yml').write_text('rules: []\n')
        def command(argv,**kwargs):
            (self.root/argv[argv.index('--output')+1]).write_text(json.dumps({'results':[{'check_id':'test','path':'source.py'}],'errors':[]}))
            return {'exit_code':1,'output':'finding','argv':argv}
        with patch.object(tool_adapters,'command_for',return_value=['semgrep']),patch.object(self.ws,'command',side_effect=command):
            result=tool_adapters.invoke(self.ws,'semgrep','scan',{'rules':'rules.yml'},config={})
        self.assertTrue(result['success']);self.assertEqual(result['finding_count'],1);self.assertTrue(result['artifacts'][0]['sha256'])
    def test_unsupported_operation_is_rejected(self):
        with self.assertRaises(ValueError):tool_adapters.invoke(self.ws,'ghidra','install',{})


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.project=self.root/'project';self.project.mkdir();(self.project/'tests').mkdir()
        (self.project/'total.py').write_text('def total(a,b):\n    return a+b+1\n')
        (self.project/'tests/test_total.py').write_text('import unittest\nfrom total import total\nclass TestTotal(unittest.TestCase):\n    def test_total(self):self.assertEqual(total(2,3),5)\n')
        self.runtime=self.root/'runtime';self.runtime.mkdir()
        caps=inventory()
        self.patches=[patch.object(runner,'JOBS',self.root/'jobs'),patch.object(runner,'RUNTIME',self.runtime),patch.object(runner,'ensure',return_value=None),patch.object(tool_catalog,'discover',return_value=caps),patch.object(source_lookup,'github_repos',return_value={'available':False,'repos':[]})]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def edit(self):return {'tool_calls':[{'name':'edit_patch','arguments':{'path':'total.py','old_text':'return a+b+1','new_text':'return a+b','expected_sha256':fingerprint(self.project/'total.py')}}],'content':''}
    def test_real_failure_patch_test_and_original_retained(self):
        with patch.object(runner,'complete',side_effect=[self.edit(),{'tool_calls':[],'content':'Repaired total.'}]):state=runner.run(job(self.project))
        self.assertEqual(state['status'],'completed',state.get('error'));self.assertEqual(state['verification'],'GOAL_VERIFIED')
        self.assertIn('a+b+1',(self.project/'total.py').read_text());self.assertIn('return a+b\n',(Path(state['workspace'])/'total.py').read_text())
        checks=state['verification_results']['checks'];self.assertTrue(any(c['exit_code']==1 for c in checks));self.assertTrue(any(c['exit_code']==0 and c['revision']==1 for c in checks))
        self.assertTrue(any(a['kind']=='unified_patch' for a in state['artifacts']))
    def test_model_completion_without_verification_blocked(self):
        with patch.object(runner,'complete',return_value={'tool_calls':[],'content':'Everything is fixed.'}):state=runner.run(job(self.project))
        self.assertEqual(state['status'],'needs_verification');self.assertNotEqual(state['verification'],'GOAL_VERIFIED')
    def test_stop_resume_does_not_repeat_patch(self):
        calls={'n':0}
        original=runner.Workspace.command
        def command(self, argv, **kwargs):
            if argv[:3]==['python3','-m','unittest']:
                calls['n']+=1
                if calls['n']==2:raise runner.Cancelled('disconnect')
            return original(self, argv, **kwargs)
        with patch.object(runner.Workspace,'command',command),patch.object(runner,'complete',return_value=self.edit()):stopped=runner.run(job(self.project))
        self.assertEqual(stopped['status'],'stopped',stopped.get('error'))
        next_job=job(self.project,'b'*32);next_job['resume_from']='a'*32
        with patch.object(runner,'complete',return_value={'tool_calls':[],'content':'Recovered and verified.'}):state=runner.run(next_job)
        self.assertEqual(state['status'],'completed',state.get('error'));self.assertEqual(len(state['patches']),1)
        journal=json.loads((self.root/'jobs'/('b'*32+'.journal.json')).read_text());self.assertEqual(journal['revision'],1)
    def test_generation_stop_retains_journal(self):
        with patch.object(runner,'complete',side_effect=runner.Cancelled('stopped')):state=runner.run(job(self.project))
        self.assertEqual(state['status'],'stopped');self.assertTrue(Path(state['journal_file']).exists())
    def test_launch_crash_without_project_stays_unverified(self):
        empty=self.root/'empty';empty.mkdir()
        with patch.object(runner,'device_execute',return_value={'exit_code':0,'output':''}),patch.object(runner,'complete',return_value={'tool_calls':[],'content':'Not verified'}):
            state=runner.run(job(empty,objective='prettyup app installed but not opening up',profile='BUILD'))
        self.assertEqual(state['workflow'],'device')
        self.assertEqual(state['status'],'needs_verification')
        self.assertNotEqual(state.get('verification'),'GOAL_VERIFIED')

    def test_nested_named_app_reproduces_its_tests(self):
        parent=self.root/'box';parent.mkdir();app=parent/'prettyup';app.mkdir();(app/'tests').mkdir()
        (app/'total.py').write_text('def total(a,b):\n    return a+b+1\n')
        (app/'tests/test_total.py').write_text('import unittest\nfrom total import total\nclass T(unittest.TestCase):\n    def test_total(self):self.assertEqual(total(2,3),5)\n')
        with patch.object(runner,'complete',return_value={'tool_calls':[],'content':'Everything is fixed.'}):
            state=runner.run(job(parent,objective='i have an app prettyup, it crashes upon opening. fix it',profile='BUILD'))
        self.assertTrue((Path(state['workspace'])/'total.py').is_file())
        self.assertEqual(state['workflow'],'source_fix')
        self.assertEqual(state['status'],'needs_verification')
        repro=next(a for a in state['activity'] if a['title']=='Checking the failure baseline')
        self.assertEqual(repro['status'],'completed')
        self.assertIn('return a+b+1',(parent/'prettyup'/'total.py').read_text())


if __name__=='__main__':unittest.main()
