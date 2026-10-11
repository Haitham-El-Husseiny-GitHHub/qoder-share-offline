import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import context_policy as policy
import runtime_config

def fixture(path,arch='qwen2',context=32768,interval=None):
    fields={'general.architecture':arch,arch+'.context_length':context,
            arch+'.block_count':32,arch+'.embedding_length':2048,
            arch+'.attention.head_count':16,arch+'.attention.head_count_kv':4}
    if interval:fields[arch+'.full_attention_interval']=interval
    def string(value):data=value.encode();return struct.pack('<Q',len(data))+data
    with path.open('wb') as f:
        f.write(b'GGUF'+struct.pack('<IQQ',3,0,len(fields)))
        for key,value in fields.items():
            f.write(string(key))
            if isinstance(value,str):f.write(struct.pack('<I',8)+string(value))
            else:f.write(struct.pack('<II',4,value))
    return path

class ContextPolicyTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_never_exceeds_trained_context(self):
        path=fixture(self.root/'model.gguf')
        result=policy.plan(path,available_bytes=32*1024**3)
        self.assertEqual(result['context_window'],32768)
    def test_ram_budget_limits_context_and_reserves_memory(self):
        path=fixture(self.root/'model.gguf',context=131072)
        available=4*1024**3;result=policy.plan(path,available_bytes=available)
        self.assertTrue(result['fits']);self.assertLess(result['context_window'],131072)
        self.assertLessEqual(result['estimated_kv_bytes']+policy.RESERVE_BYTES+policy.COMPUTE_BYTES+path.stat().st_size*1.05,available)
    def test_two_slots_cost_more_than_one(self):
        path=fixture(self.root/'model.gguf',context=262144)
        one=policy.plan(path,parallel=1,available_bytes=4*1024**3)
        two=policy.plan(path,parallel=2,available_bytes=4*1024**3)
        self.assertGreater(one['context_window'],two['context_window'])
    def test_hybrid_full_attention_layers_are_counted(self):
        full=fixture(self.root/'full.gguf',context=262144)
        hybrid=fixture(self.root/'hybrid.gguf',arch='qwen35',context=262144,interval=4)
        self.assertGreater(policy.plan(hybrid,available_bytes=4*1024**3)['context_window'],policy.plan(full,available_bytes=4*1024**3)['context_window'])
    def test_insufficient_ram_does_not_claim_a_usable_context(self):
        path=fixture(self.root/'model.gguf')
        self.assertFalse(policy.plan(path,available_bytes=policy.RESERVE_BYTES)['fits'])
    def test_corrupt_header_stops_without_an_invented_limit(self):
        path=self.root/'bad.gguf';path.write_bytes(b'GGUF')
        with self.assertRaises(ValueError):policy.plan(path,available_bytes=4*1024**3)

class PromptBudgetTests(unittest.TestCase):
    def lookup(self,path,body,timeout):
        if path=='/apply-template':return {'prompt':''.join(m['content'] for m in body['messages'])}
        return {'tokens':list(body['content'].encode('utf-8'))}
    def test_old_pairs_removed_but_policy_task_and_latest_evidence_preserved(self):
        messages=[{'role':'system','content':'policy'},{'role':'user','content':'task'},
                  {'role':'assistant','content':'old'*1000},{'role':'user','content':'result'*1000},
                  {'role':'assistant','content':'latest call'},{'role':'user','content':'latest source'}]
        with patch.object(runtime_config,'request',side_effect=self.lookup):
            fitted,count=runtime_config.fit_messages(messages,1024)
        self.assertEqual(fitted,messages[:2]+messages[-2:]);self.assertEqual(len(messages),6)
    def test_larger_context_keeps_complete_history(self):
        messages=[{'role':'system','content':'policy'},{'role':'user','content':'task'},
                  {'role':'assistant','content':'old'*1000},{'role':'user','content':'result'*1000},
                  {'role':'assistant','content':'latest call'},{'role':'user','content':'latest source'}]
        with patch.object(runtime_config,'request',side_effect=self.lookup):
            self.assertEqual(runtime_config.fit_messages(messages,32768)[0],messages)
    def test_long_prompt_timeout_scales_beyond_old_three_minutes(self):
        self.assertGreater(runtime_config.generation_timeout(5631),600)
        self.assertEqual(runtime_config.generation_timeout(2_000_000),14400)
    def test_multibyte_oversized_task_stops_without_truncation(self):
        messages=[{'role':'system','content':'policy'},{'role':'user','content':'أ'*500}]
        with patch.object(runtime_config,'request',side_effect=self.lookup),self.assertRaisesRegex(ValueError,'after reply reserve'):
            runtime_config.fit_messages(messages,1024)
        self.assertEqual(messages[1]['content'],'أ'*500)

if __name__=='__main__':unittest.main()
