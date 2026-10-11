import json, os, sys, tempfile, unittest
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'backend'))
import source_lookup as lookup

class SourceLookupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.calls=[]
    def tearDown(self):self.temp.cleanup()
    def run_cmd(self, argv, timeout):
        self.calls.append(argv)
        if argv[:3]==['gh','repo','list']:
            return {'exit_code':0,'output':json.dumps([{'name':'prettyup','url':'https://github.com/me/prettyup','description':'mine'}])}
        if argv[:3]==['gh','search','repos']:
            return {'exit_code':0,'output':json.dumps([
                {'fullName':'me/prettyup','url':'https://github.com/me/prettyup','description':'mine'},
                {'fullName':'other/prettyup','url':'https://github.com/other/prettyup','description':'public'}])}
        return {'exit_code':0,'output':'[]'}
    def test_phone_project_wins_without_clone(self):
        work=self.root/'empty';work.mkdir();app=work/'prettyup';app.mkdir();(app/'package.json').write_text('{"name":"prettyup"}\n')
        cloned=[]
        report=lookup.acquire('the installed app prettyup crashes on opening', work, device=lambda argv:{'output':'package:com.studio.prettyup\n'}, config={'source_roots':[]}, run=self.run_cmd, clone=lambda url,dest:cloned.append(url) or {'ok':False}, http_get=lambda *a: {})
        self.assertEqual(Path(report['root']).resolve(), app.resolve())
        self.assertEqual(report['package'],'com.studio.prettyup')
        self.assertEqual(cloned,[])
        self.assertEqual(report['chosen']['where'],'phone')
    def test_github_named_place_clones_the_owned_repo(self):
        dest_holder={}
        def clone(url, dest):
            dest_holder['url']=url;dest.mkdir(parents=True);(dest/'package.json').write_text('{}\n');return {'ok':True}
        report=lookup.acquire('prettyup app is on github, fix the crash', self.root/'work', device=None, config={'offline':False}, run=self.run_cmd, clone=clone, http_get=lambda *a: {})
        (self.root/'work').mkdir()
        self.assertEqual(dest_holder['url'],'https://github.com/me/prettyup')
        self.assertEqual(report['chosen']['where'],'github')
        self.assertTrue(report['root'])
    def test_cloudflare_clone_follows_connected_repo(self):
        token=self.root/'cf.token';token.write_text('super-secret-token\n');token.chmod(0o600)
        def http_get(url, secret):
            self.assertEqual(secret,'super-secret-token')
            if 'pages/projects' not in url:return {'result':[]}
            return {'result':[{'name':'prettyup','source':{'config':{'owner':'me','repo_name':'prettyup'}}}]}
        def clone(url, dest):
            dest.mkdir(parents=True);(dest/'gradlew').write_text('#!/bin/sh\n');return {'ok':True,'url':url}
        report=lookup.acquire('prettyup app is on cloudflare and crashes', self.root/'work', device=None, config={'offline':False,'cloudflare':{'account_id':'a'*32,'api_token_file':str(token)}}, run=lambda *a,**k:{'exit_code':0,'output':'[]'}, clone=clone, http_get=http_get)
        self.assertEqual(report['chosen']['where'],'cloudflare')
        self.assertNotIn('super-secret-token', json.dumps(lookup.public(report)))
    def test_ambiguous_github_is_not_cloned(self):
        def run(argv, timeout):
            if argv[:3]==['gh','repo','list']:return {'exit_code':0,'output':'[]'}
            return {'exit_code':0,'output':json.dumps([
                {'fullName':'a/prettyup','url':'https://github.com/a/prettyup'},
                {'fullName':'b/prettyup','url':'https://github.com/b/prettyup'}])}
        cloned=[]
        report=lookup.acquire('app prettyup crashes', self.root/'work', device=lambda argv:(_ for _ in ()).throw(ValueError('Rish is offline')), config={'offline':False}, run=run, clone=lambda url,dest:cloned.append(url), http_get=lambda *a:{})
        self.assertIsNone(report['root']);self.assertEqual(cloned,[])
        self.assertEqual(report['chosen']['where'],'none')
        self.assertIn('a/prettyup', report['places'][2]['repos'])

if __name__=='__main__':unittest.main()
