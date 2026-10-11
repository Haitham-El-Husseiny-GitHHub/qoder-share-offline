import json, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import install_offline_tools as offline

class InstallerRegressionTests(unittest.TestCase):
    def test_apkeditor_known_version_exit_only(self):
        for argv,code,text,expected in [(['java','-jar','x.jar','-v'],2,'APKEditor version 1.4.9, ARSCLib version 1.3.9',True),(['java','-jar','x.jar','-v'],2,'Unable to load jar',False),(['java','-jar','x.jar','info'],2,'APKEditor version 1.4.9, ARSCLib version 1.3.9',False),(['java','-jar','x.jar','-v'],1,'APKEditor version 1.4.9, ARSCLib version 1.3.9',False)]:
            with self.subTest(argv=argv,code=code,text=text),patch.object(offline.subprocess,'run',return_value=subprocess.CompletedProcess(argv,code,text,'')):
                self.assertEqual(offline.probe(argv,tool='apkeditor')['passed'],expected)
    def test_zipalign_checks_actual_archive_and_does_not_ignore_failure(self):
        def align(argv):
            self.assertNotIn('-h',argv)
            with zipfile.ZipFile(argv[-2] if '-f' in argv else argv[-1]) as z:self.assertEqual(z.read('assets/probe.bin'),b'Qoder alignment probe')
            if '-f' in argv:Path(argv[-1]).write_bytes(Path(argv[-2]).read_bytes())
            return {'passed':True}
        with patch.object(offline,'probe',side_effect=align) as call:
            self.assertTrue(offline.zipalign_probe()['passed']);self.assertEqual(call.call_count,2)
        with patch.object(offline,'probe',return_value={'passed':False}) as call:
            self.assertFalse(offline.zipalign_probe()['passed']);self.assertEqual(call.call_count,1)
    def test_node_launcher_resolves_npm_symlink_without_shebang(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);script=root/'cli.mjs';script.write_text('#!/usr/bin/env node');link=root/'typescript-language-server';link.symlink_to(script)
            with patch.object(offline.shutil,'which',return_value='/termux/bin/node'):
                self.assertEqual(offline.node_command(link,'--stdio'),['/termux/bin/node',str(script),'--stdio'])
    def test_explicit_companion_is_used_for_version_guard(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);bundle=root/'android/qoder-companion';bundle.mkdir(parents=True);new=root/'verified-companion';new.mkdir()
            (bundle/'package.json').write_text('{"build":79}');(new/'package.json').write_text('{"build":83}')
            self.assertEqual(offline.companion_manifest(root,new)['build'],83)
    def test_cli_accepts_pinned_companion_and_bundle_arguments(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'inventory.json').write_text('{"files":[]}')
            r=subprocess.run([sys.executable,offline.__file__,'--check','--cache',str(root),'--companion',str(root),'--bundle-sha256','a'*64],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)

if __name__=='__main__':unittest.main()
