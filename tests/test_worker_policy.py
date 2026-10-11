import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import coding_runner as runner
from router_runtime import tools


class WorkerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'ledger.py').write_text('return 105\n')
        self.ws=runner.Workspace(self.root,False)
        self.plan={'workflow':'source_fix','checks':[{'argv':['python3','-m','unittest','discover']}],'adapters':[]}
        self.guard=runner.WorkerGuard(self.ws,self.plan)
    def tearDown(self):self.temp.cleanup()
    def test_read_exact_text_and_hash_before_patch(self):
        args={'path':'ledger.py','old_text':'return 105','new_text':'return 1.05'}
        with self.assertRaises(ValueError):self.guard.validate('edit_patch',args)
        result=self.ws.invoke('read_file',{'path':'ledger.py'});self.guard.observe('read_file',result)
        self.guard.validate('edit_patch',args)
        with self.assertRaises(ValueError):self.guard.validate('edit_patch',{**args,'expected_sha256':'invented'})
        self.guard.validate('edit_patch',{**args,'expected_sha256':result['sha256']})
    def test_existing_write_and_undeclared_check_blocked(self):
        with self.assertRaises(ValueError):self.guard.validate('write_file',{'path':'ledger.py'})
        with self.assertRaises(ValueError):self.guard.validate('diagnose',{'argv':['python3','other.py']})
        self.guard.validate('diagnose',{'argv':self.plan['checks'][0]['argv']})
    def test_second_call_must_read_observed_file(self):
        self.guard.observe('code_search',{'matches':[{'file':'ledger.py'}]})
        self.guard.validate('read_file',{'path':'ledger.py'},1)
        for name,args in [('read_file',{'path':'other.py'}),('edit_patch',{'path':'ledger.py'})]:
            with self.assertRaises(ValueError):self.guard.validate(name,args,1)
    def test_inspect_surface_and_runner_verification(self):
        plan={**self.plan,'workflow':'inspect'}
        self.assertEqual({t['name'] for t in tools(runner.TOOLS,plan,True)},{'read_file','code_search','git_diff'})
        with self.assertRaises(ValueError):runner.WorkerGuard(self.ws,plan).validate('verify_goal',{})
    def test_stop_conditions_and_one_shot_capabilities(self):
        for result in [{'error':'No such file or directory'},{'error':'Permission denied'},{'error':'Unknown tool'},{'rish_connected':False}]:self.assertTrue(self.guard.blocker(result))
        self.guard.validate('bridge_status',{})
        with self.assertRaises(ValueError):self.guard.validate('bridge_status',{})
    def test_two_identical_check_failures_across_edits_stop(self):
        check={'argv':['python3','-m','unittest'],'success':False,'exit_code':1,'output':'same defect'}
        self.assertEqual(self.guard.repeated_check_failure([{**check,'revision':0},{**check,'revision':1}]),'same defect')
        self.assertIsNone(self.guard.repeated_check_failure([check,{**check,'output':'new trace'}]))
        self.assertIsNone(self.guard.repeated_check_failure([check,{**check,'success':True}]))
    def test_full_prompt_is_preserved_and_content_suppressed(self):
        captured=[]
        def stream(payload,**kw):
            captured.append(payload)
            return json.dumps({'tool_calls':[{'name':'read_file','arguments':{'path':'ledger.py'}}],'content':'Here is my plan'})
        def lookup(path):return [{'n_ctx':32768}] if path=='/slots' else {'data':[{'id':'test'}]}
        with patch.object(runner,'request',side_effect=lookup),patch.object(runner,'fit_messages',side_effect=lambda messages,context:messages),patch.object(runner,'stream_completion',side_effect=stream):
            answer=runner.complete([{'role':'system','content':runner.WORKER_POLICY}],runner.TOOLS,'test')
        self.assertEqual(answer['content'],'')
        self.assertIn(runner.WORKER_POLICY,captured[0]['messages'][0]['content'])
        self.assertIn('Tools:',captured[0]['messages'][0]['content'])

if __name__=='__main__':unittest.main()
