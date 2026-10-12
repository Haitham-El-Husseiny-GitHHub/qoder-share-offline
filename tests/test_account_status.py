import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
import account_status

class AccountStatusTests(unittest.TestCase):
 def test_exhausted_quota_is_zero_not_missing(self):
  result=account_status.normalize({'userId':'private-id','userQuota':{'total':2000,'used':2000,'remaining':0},'addOnQuota':{'total':3500,'used':3500,'remaining':0},'isQuotaExceeded':True},123)
  self.assertEqual(result['remaining'],0)
  self.assertTrue(result['available']);self.assertTrue(result['quota_exceeded'])
  self.assertNotIn('userId',result);self.assertEqual(result['checked_at'],123)
 def test_shared_organization_pool_stays_separate(self):
  result=account_status.normalize({'userQuota':{'total':100,'used':20},'orgResourcePackage':{'remaining':500}})
  self.assertEqual(result['remaining'],80);self.assertEqual(result['parts'][1]['remaining'],500)
 def test_no_quota_does_not_become_zero(self):
  with self.assertRaises(ValueError):account_status.normalize({'userId':'private-id'})
 def test_refresh_failure_preserves_last_verified_value_as_stale(self):
  previous=account_status.normalize({'userQuota':{'remaining':17}},1)
  with patch.object(account_status,'CACHE',previous),patch.object(account_status,'install_reader',side_effect=ValueError('Reader changed')):
   result=account_status.qoder(True)
  self.assertTrue(result['stale']);self.assertEqual(result['remaining'],17);self.assertEqual(result['checked_at'],1)
 def test_go_connection_is_not_a_balance(self):
  with patch('opencode_bridge.call',return_value={'connected':['opencode-go']}):result=account_status.go()
  self.assertTrue(result['connected']);self.assertFalse(result['available']);self.assertNotIn('remaining',result)
