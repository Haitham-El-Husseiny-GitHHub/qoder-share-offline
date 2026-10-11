import json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import model_catalog_sync as sync
import qoder_cloud as cloud
class CatalogTests(unittest.TestCase):
 def test_endpoint_tables_parse_zen_and_go_without_region_filters(self):
  body='<table><tr><td>Regional Model</td><td>regional</td><td>https://opencode.ai/zen/go/v1/messages</td><td>@ai-sdk/anthropic</td></tr></table>'
  self.assertEqual(sync.published_rows(body)[0]['id'],'regional')
 def test_unconnected_providers_and_paid_models_remain_listed(self):
  runtime={'connected':['opencode'],'all':[{'id':'opencode','models':{'free':{'id':'free','name':'Free'}}},{'id':'other','models':{'paid':{'id':'paid','name':'Paid'}}}]}
  cache={'models':[{'id':'paid','name':'Paid','served':True,'coding_compatible':True}]}
  result=sync.catalog(runtime,cache)
  self.assertEqual({m['id'] for m in result['providers'][0]['models']},{'free','paid'})
  self.assertEqual(result['providers'][1]['models'][0]['id'],'paid')
 def test_go_website_models_not_hidden_when_runtime_omits_them(self):
  result=sync.catalog({'connected':[],'all':[{'id':'opencode-go','models':{}}]}, {'go_models':[{'id':'regional','name':'Regional'}]})
  self.assertEqual(result['providers'][0]['models'][0]['id'],'regional')
 def test_temporary_network_failure_retains_catalog(self):
  with tempfile.TemporaryDirectory() as t:
   cache=Path(t)/'cache.json';cache.write_text(json.dumps({'updated_at':0,'models':[{'id':'keep'}]}))
   with patch.object(sync,'CACHE',cache),patch.object(sync,'fetch',side_effect=ValueError('offline')):
    result=sync.refresh(lambda *a:None,True)
   self.assertEqual(result['models'][0]['id'],'keep');self.assertIn('refresh_error',result)
 def test_qoder_published_models_are_not_limited_to_account_list(self):
  with tempfile.TemporaryDirectory() as t,patch.object(cloud,'ROOT',Path(t)),patch.object(cloud,'fetch',side_effect=ValueError('offline')):
   (Path(t)/'runtime').mkdir();models=cloud.catalog()['models']
  self.assertIn('GLM-5.2',{m['name'] for m in models});self.assertIn('Kimi-K2.7-Code',{m['name'] for m in models})
 def test_qoder_reserves_before_worker_and_can_stop_pending_task(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'pyproject.toml').write_text('[project]')
   with patch.object(cloud,'FOLDER',root/'jobs'),patch.object(cloud,'catalog',return_value={'models':[{'id':'paid'}]}),patch.object(cloud.threading,'Thread') as thread:
    record=cloud.run({'model':'paid','directory':str(root),'objective':'Inspect files'})
    self.assertTrue(cloud.stop(record['id'])['stopping'])
    with self.assertRaises(ValueError):cloud.run({'model':'paid','directory':str(root),'objective':'Inspect files'})
    self.assertTrue(cloud.ACTIVE[record['id']]['record']['cancel_requested']);cloud.ACTIVE.clear()
if __name__=='__main__':unittest.main()
