import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import model_catalog_sync as sync

class ProviderGroupTests(unittest.TestCase):
 def test_persistent_registration_retains_settings_and_distinct_models(self):
  import json,tempfile
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'opencode.json';path.write_text(json.dumps({'mcp':{'existing':{'enabled':True}},'provider':{'opencode-go':{'options':{'baseURL':'existing'},'models':{'old':{'name':'Same name'}}}}}))
   sync.persist_models('opencode-go',{'new':{'name':'Same name'}},path)
   saved=json.loads(path.read_text());self.assertTrue(saved['mcp']['existing']['enabled']);self.assertEqual(saved['provider']['opencode-go']['options']['baseURL'],'existing');self.assertEqual(set(saved['provider']['opencode-go']['models']),{'old','new'})
 def test_go_developers_share_one_credential_route(self):
  runtime={'connected':['opencode-go'],'all':[{'id':'opencode-go','name':'OpenCode Go','models':{'a':{'id':'gpt-6','name':'GPT'},'b':{'id':'claude-haiku','name':'Claude'}}}]}
  result=sync.catalog(runtime,{})['providers'][0]['models']
  self.assertEqual([m['developer'] for m in result],['Anthropic','OpenAI'])
  self.assertTrue(all(m['credential_provider']=='opencode-go' for m in result))
 def test_models_sort_by_name_before_account_availability(self):
  data=sync.catalog({'connected':[],'all':[{'id':'opencode-go','models':{'z':{'id':'z','name':'Zulu'},'a':{'id':'a','name':'Alpha'}}}]},{})
  self.assertEqual([m['name'] for m in data['providers'][0]['models']],['Alpha','Zulu'])
 def test_duplicate_display_names_with_distinct_ids_keep_their_costs(self):
  data=sync.catalog({'all':[{'id':'opencode-go','models':{'one':{'id':'one','name':'Same model','cost':{'input':1}},'two':{'id':'two','name':'Same model','cost':{'input':2}}}}]}, {})
  rows=data['providers'][0]['models'];self.assertEqual(len(rows),2);self.assertEqual([m['cost']['input'] for m in rows],[1,2])
 def test_independent_api_providers_are_separate_connections(self):
  data=sync.catalog({'connected':['opencode-go'],'all':[{'id':'anthropic','models':{'x':{'id':'claude-x'}}},{'id':'opencode-go','models':{}}]}, {})
  independent=next(p for p in data['providers'] if p['id']=='anthropic');self.assertFalse(independent['connected'])
