import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import model_catalog_sync as sync
import opencode_bridge as bridge

class GoSessionTests(unittest.TestCase):
 def test_public_rates_use_go_table_and_ignore_non_price_tables(self):
  body='''<tr><td>DeepSeek V4 Pro (Peak)</td><td>$1.32</td><td>$3.96</td><td>$0.044</td><td>-</td><td>$15</td></tr>
  <tr><td>DeepSeek V4 Pro (Off-Peak)</td><td>$0.66</td><td>$1.98</td><td>$0.022</td><td>-</td><td>$15</td></tr>
  <tr><td>DeepSeek V4 Pro (Peak)</td><td>$1.32</td><td>$3.96</td><td>$0.044</td><td>-</td><td>$60</td></tr>'''
  prices=sync.published_prices(body)
  self.assertEqual(prices['DeepSeek V4 Pro (Peak)'],{'input':1.32,'output':3.96})
  self.assertEqual(prices['DeepSeek V4 Pro (Off-Peak)']['input'],.66)
 def test_existing_chat_does_not_rediscover_or_move_project(self):
  import source_lookup
  calls=[]
  def call(path,method='GET',body=None,directory=None):
   calls.append((path,method,body,directory))
   return {'directory':'/project/existing'} if path=='/session/existing' else {'accepted':True}
  with patch.object(bridge,'call',side_effect=call),patch.object(bridge,'get',return_value={'providers':[{'models':[{'id':'model'}]}]}),patch.object(source_lookup,'project_for_path',side_effect=lambda p:p),patch.object(source_lookup,'acquire') as discover:
   result=bridge.post({'action':'run','session':'existing','model':'opencode-go/model','objective':'Now fix the other app too'})
  discover.assert_not_called()
  self.assertEqual(result['directory'],'/project/existing')
  self.assertEqual(calls[-1][3],'/project/existing')
 def test_published_go_price_and_schedules_survive_catalog_merge(self):
  row={'id':'deepseek-v4-pro','name':'DeepSeek V4 Pro','pricing_schedule':'deepseek','pricing':{'peak':{'input':1.32,'output':3.96},'offpeak':{'input':.66,'output':1.98}}}
  result=sync.catalog({'connected':['opencode-go'],'all':[{'id':'opencode-go','models':{row['id']:{'id':row['id'],'cost':{'input':9,'output':9}}}}]}, {'go_models':[row]})
  model=result['providers'][0]['models'][0]
  self.assertTrue(model['available']);self.assertEqual(model['pricing'],row['pricing'])
