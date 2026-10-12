import sys,tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import bridge,bridge_watchdog as monitor

class RecoveryTests(unittest.TestCase):
 def test_only_authorized_loopback_devices(self):
  self.assertEqual(monitor.local_adb('List of devices attached\n127.0.0.1:5555 device\n127.0.0.1:7777 unauthorized\n192.168.1.4:5555 device\nemulator-5554 device'),['127.0.0.1:5555'])
 def test_no_local_authorization_does_not_start(self):
  with patch.object(monitor,'command',return_value=(0,'192.168.1.4:5555 device')) as call:
   result=monitor.restart_shizuku()
   self.assertFalse(result['attempted']);self.assertEqual(call.call_count,1)
 def test_invalid_apk_path_does_not_execute(self):
  with patch.object(monitor,'command',side_effect=[(0,'127.0.0.1:5555 device'),(0,'package:/sdcard/base.apk')]) as call:
   self.assertFalse(monitor.restart_shizuku()['attempted']);self.assertEqual(call.call_count,2)
 def test_installed_starter_invocation(self):
  apk='/data/app/~~token/moe.shizuku-token/base.apk'
  with patch.object(monitor,'command',side_effect=[(0,'127.0.0.1:5555 device'),(0,'package:'+apk),(0,'started')]) as call:
   self.assertTrue(monitor.restart_shizuku()['attempted'])
   self.assertEqual(call.call_args.args[0],['adb','-s','127.0.0.1:5555','shell','/data/app/~~token/moe.shizuku-token/lib/arm64/libshizuku.so','--apk='+apk])
 def test_healthy_connection_records_without_restart(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(monitor,'ROOT',Path(folder)),patch.object(bridge,'status',return_value={'termux':True,'rish_connected':True,'access_level':'shell'}),patch.object(monitor,'restart_shizuku') as restart:
   result=monitor.check();restart.assert_not_called()
   self.assertEqual(json.loads((Path(folder)/'runtime/bridge-recovery.json').read_text()),result)
   self.assertEqual(list((Path(folder)/'runtime').glob('*.tmp')),[])
