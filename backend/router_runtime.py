"""Worker integration: a small tool surface backed by a durable job router."""
import json
import re
from pathlib import Path

import task_router
import tool_adapters
from tool_catalog import CATALOG, public_capabilities

INPUT_HINTS = {
    'language_server': 'path,line,column (one-based)', 'ast_grep': 'path,pattern,language,replacement',
    'gradle': 'tasks:string[]', 'node': 'script (declared in package.json)',
    'cmake':'build_dir,path',
    'adb': 'package,path,lines', 'rish': 'package,path,lines', 'jadx': 'path,output', 'apktool': 'path,output',
    'apkeditor': 'path,output', 'smali': 'path,output', 'baksmali': 'path,output', 'zipalign': 'path,output',
    'apksigner': 'path,output (signing config stays private)', 'bundletool': 'path,output,device_spec,package',
    'frida': 'package or native pid,script,expected_text', 'ghidra': 'path,output', 'semgrep': 'path,rules,output',
    'codeql': 'path,language,queries,build_argv,output', 'mobsf': 'path,output', 'zap': 'url,output',
    'mitmproxy': 'path,output,port', 'http': 'url,method,body,headers,expected_status,expected_text',
    'libfuzzer': 'path,corpus,output', 'debugger': 'path,argv', 'ui': 'framework; instrumentation:runner,access; other runners:path'
}


def tools(base_tools, plan, readonly=False):
    from coding_runner import tool
    role=plan['workflow']
    names={
        'source_fix':{'read_file','list_files','code_search','edit_patch','run_argv','diagnose','git_diff'},
        'source_build':{'read_file','list_files','code_search','write_file','edit_patch','run_argv','diagnose','git_diff'},
        'text_edit':{'read_file','edit_patch'},
        'device':{'bridge_status','device_argv','import_apk'},
        'apk_inspect':{'import_apk','bridge_status','read_file'},
        'apk_modify':{'import_apk','bridge_status','read_file','list_files','code_search','edit_patch','apk_tools'},
        'api':set(), 'security':{'read_file','code_search'},
        'native':{'read_file','code_search'},
        'inspect':{'read_file','code_search','git_diff'},
    }[role]
    if readonly:names-= {'write_file','edit_patch','run_argv','diagnose','device_argv','import_apk'}
    chosen = [t for t in base_tools if t['name'] in names]
    selected = plan['adapters']
    descriptions = '; '.join(n + ': ' + '/'.join(CATALOG[n]['operations']) + ', inputs ' + INPUT_HINTS[n] for n in selected)
    input_fields = {key: {'type': 'string'} for key in ('path', 'output', 'pattern', 'language', 'replacement', 'script', 'package', 'device_spec', 'rules', 'queries', 'url', 'method', 'body', 'expected_text', 'corpus', 'framework','build_dir','runner','access')}
    input_fields.update({key: {'type': 'integer'} for key in ('line', 'column', 'lines', 'port', 'expected_status','pid')})
    input_fields.update({key: {'type': 'array', 'items': {'type': 'string'}} for key in ('tasks', 'argv', 'build_argv','paths')})
    input_fields['headers'] = {'type': 'object', 'additionalProperties': {'type': 'string'}}
    if selected:chosen.append(tool('tool_adapter', 'Execute a selected adapter and inspect structured results. ' + descriptions,
                      {'tool': {'type': 'string', 'enum': selected}, 'operation': {'type': 'string'},
                       'inputs': {'type': 'object', 'properties': input_fields, 'additionalProperties': False},
                       'timeout': {'type': 'integer'}}, ['tool', 'operation', 'inputs']))
    if role!='inspect':chosen.append(tool('tool_capabilities', 'Inspect observed tools, access and prerequisites for this workflow.', {}, []))
    if not readonly and role in {'source_fix','source_build','apk_modify'}:
        chosen.append(tool('unified_patch', 'Preview/apply a unified diff. Existing paths require their observed SHA-256 map.',
                          {'patch': {'type': 'string'}, 'expected_sha256': {'type': 'object', 'additionalProperties': {'type': 'string'}},
                           'preview': {'type': 'boolean'}}, ['patch', 'expected_sha256']))
    return chosen


class Runtime:
    def __init__(self, ws, journal, plan, inventory, config):
        self.ws, self.journal, self.plan, self.inventory, self.config = ws, journal, plan, inventory, config
        self.verification_argv=None
        journal.data['plan'] = plan
        journal.data['capabilities'] = public_capabilities(inventory)
        journal.save()

    def invoke(self, name, args):
        if name == 'tool_capabilities':
            public = public_capabilities(self.inventory)
            public['tools'] = {n: {**public['tools'][n], 'input_fields': INPUT_HINTS[n]} for n in self.plan['adapters']}
            public['workflow'] = self.plan['workflow']
            return public
        if name == 'tool_adapter':
            if args['tool'] not in self.plan['adapters']:
                raise ValueError('Use an adapter selected for this workflow. Inspect tool_capabilities.')
            if self.plan['workflow']=='apk_inspect' and args['operation'] not in {'decode','decompile','disassemble'}:raise ValueError('APK inspection permits decode/decompile/disassemble only.')
            if self.plan['workflow']=='security' and args['operation']!='search':raise ValueError('Security review runs searches; findings are not repairs.')
            if self.plan['workflow']=='device' and args['operation']=='install':raise ValueError('Device diagnosis does not install APKs; request APK modification explicitly.')
            result = tool_adapters.invoke(self.ws, args['tool'], args['operation'], args.get('inputs', {}), args.get('timeout', CATALOG[args['tool']]['timeout_seconds']), self.config)
            return result
        if name == 'verify_goal':
            return self.verify(args.get('run_checks', True))
        raise ValueError('Unknown router tool.')

    def verify(self, run_checks=True):
        self.journal.check_files()
        outer=self.journal.data.pop('pending_step',None)
        if not self.plan['checks'] and self.plan['workflow'] in {'source_fix','source_build'}:
            detected=task_router.project(self.ws.root)
            self.plan['checks']=detected['checks']
            if any(c['kind']=='build' for c in detected['checks']) and 'build' not in self.plan['required']:self.plan['required'].append('build')
        if run_checks:
            for check in self.plan['checks']:
                kind = check['kind']
                if kind not in self.plan['required'] and kind!='configure':continue
                if self.ws.readonly and kind not in {'tests','security_validation'}:continue
                # A current successful check needs no repeat.
                prior=[c for c in self.journal.data['checks'] if c['kind']==kind and c['revision']==self.journal.data['revision'] and c['argv']==check['argv']]
                if prior and prior[-1]['success']:
                    continue
                if self.ws.cancel:
                    self.ws.cancel()
                adapter=None;operation=None;inputs={}
                if not self.plan.get('custom_checks'):
                    detected=task_router.project(self.ws.root)
                    if detected['kind'] in {'android','gradle'} and kind in {'build','tests'}:
                        adapter='gradle';operation='test' if kind=='tests' else 'build';inputs={'tasks':[check['argv'][-1]]}
                    elif detected['kind']=='node' and kind in {'build','tests','typecheck'}:
                        adapter='node';operation='test' if kind=='tests' else kind;inputs={'script':check['argv'][-1]}
                    elif detected['kind']=='native' and kind in {'configure','build','tests'}:
                        adapter='cmake';operation='test' if kind=='tests' else kind;inputs={'build_dir':'qoder-build'}
                tool='tool_adapter' if adapter else 'diagnose'
                if adapter and adapter not in self.plan['adapters']:self.plan['adapters'].append(adapter)
                args={'tool':adapter,'operation':operation,'inputs':inputs,'timeout':600} if adapter else {'argv':check['argv']}
                self.journal.begin(tool,args)
                self.verification_argv=check['argv']
                try:
                    result = self.ws.invoke(tool,args)
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    result = {'success': False, 'error': str(exc)}
                    self.journal.check(kind,result,check['argv'])
                finally:self.verification_argv=None
                self.journal.finish(result)
        if outer:self.journal.data['pending_step']=outer
        self.journal.save()
        return task_router.evidence(self.journal)

    def observe(self, name, args, result):
        if not isinstance(result, dict):
            if name == 'list_files' and result:
                self.journal.check('inspection', {'success': True, 'exit_code': 0})
            return result
        okay = not result.get('error') and result.get('success', result.get('exit_code', 0) == 0)
        if name in {'read_file', 'code_search', 'git_diff'} and okay:
            self.journal.check('inspection', {'success': True, 'exit_code': 0})
            if name=='read_file':
                self.journal.data['file_hashes'][result['path']]=result['sha256'];self.journal.save()
                if self.plan['workflow']=='text_edit' and any(p['path']==result['path'] and p.get('after_sha256')==result['sha256'] and p.get('before_sha256')!=p.get('after_sha256') for p in self.journal.data['patches']):
                    self.journal.check('text_validation',{'success':True,'exit_code':0})
        if name == 'apk_tools' and args.get('action') in {'decode','decompile'} and okay and result.get('output_path') and self.ws.file(result['output_path']).exists():
            self.journal.check('apk_inspection',result)
        if name == 'apk_tools' and args.get('action') in {'info', 'decode', 'decompile'} and okay:
            self.journal.check('inspection', {'success': True, 'exit_code': 0})
        if name == 'apk_tools' and args.get('action') == 'rebuild' and okay and result.get('artifact_exists'):
            self.journal.check('apk_rebuild', result)
        if name in {'run_argv', 'diagnose'} and 'exit_code' in result:
            kind = task_router.check_kind(result['argv'], self.plan)
            if kind in {'tests', 'functional', 'security_validation'}:
                result = task_router.test_result(result)
            self.journal.check(kind, result, result['argv'])
        if name == 'device_argv' and okay:
            argv = args.get('argv', [])
            if argv and argv[0] in {'logcat', 'dumpsys', 'pm'}:
                self.journal.check('device_inspection', result, argv)
            if re.search(r'OK \([1-9][0-9]* tests?\)', result.get('output', '')):
                self.journal.check('functional', result, argv)
        if name != 'tool_adapter':
            return result
        adapter, operation = args['tool'], args['operation']
        if adapter in {'node', 'gradle','cmake'} and operation in {'test', 'build', 'typecheck','configure'}:
            kind = {'test': 'tests', 'build': 'build', 'typecheck': 'typecheck','configure':'configure'}[operation]
            argv = self.verification_argv or result.get('argv', [])
            self.journal.check(kind, result, argv)
        if adapter == 'apktool' and operation == 'rebuild' and okay:
            self.journal.check('apk_rebuild', result)
        if adapter in {'jadx', 'apktool', 'apkeditor', 'baksmali'} and operation in {'decompile', 'decode', 'disassemble', 'merge'} and okay:
            self.journal.check('inspection', result)
        if adapter in {'jadx','apktool','apkeditor','baksmali'} and operation in {'decode','decompile','disassemble'} and okay and any(a.get('path') and self.ws.file(a['path']).exists() for a in result.get('artifacts',[])):
            self.journal.check('apk_inspection',result)
        if adapter=='ast_grep' and operation=='search' and self.plan['workflow']=='security' and okay and result.get('artifacts'):
            self.journal.check('security_scan',result)
        if adapter=='debugger' and operation=='backtrace' and okay and re.search(r'(?m)^#\d+\s',result.get('output','')):
            self.journal.check('runtime_observation',result,result.get('argv'))
        signature=result.get('signature_verification',result)
        signature_verified=bool(signature.get('success') and signature.get('certificates_sha256'))
        if adapter == 'apksigner' and okay and operation in {'sign','verify'} and signature_verified:
            self.journal.check('apk_signature', result)
        if adapter=='apkeditor' and operation in {'rebuild','merge'} and okay:self.journal.check('apk_rebuild',result)
        if adapter=='bundletool' and operation=='install' and okay:
            if signature_verified:self.journal.check('apk_signature',result)
            self.journal.check('installation',result)
        if adapter in {'adb', 'rish'} and okay:
            kind = 'installation' if operation == 'install' else 'device_inspection'
            self.journal.check(kind, result)
        if adapter == 'ui':
            self.journal.check('functional', result, result.get('argv'))
            self.journal.check('tests', result, result.get('argv'))
        if adapter == 'ghidra' and okay:
            self.journal.check('native_analysis', result)
        if adapter == 'libfuzzer' and operation == 'run':
            self.journal.check('runtime_observation', result, result.get('argv'))
            if result.get('artifacts'):
                self.journal.check('native_analysis', {'success': True, 'exit_code': 0})
        if adapter in {'frida', 'debugger'} and okay and result.get('observation_matched'):
            self.journal.check('runtime_observation', result, result.get('argv'))
        if adapter in {'semgrep', 'codeql', 'mobsf', 'zap'} and operation in {'scan', 'analyze'} and okay:
            self.journal.check('security_scan', result)
            if result.get('finding_count') == 0:
                self.journal.check('security_validation', result)
        if adapter == 'http' and result.get('expectation_checked'):
            fingerprint = result['request_fingerprint']
            previous_failure = any(c['kind'] == 'api_response' and c['name'] == fingerprint and not c['success'] for c in self.journal.data['checks'])
            self.journal.check('api_response', result, name=fingerprint)
            if okay and previous_failure:
                self.journal.check('api_reproduction', result)
        return result

    def prompt(self):
        compact = {k: self.plan[k] for k in ('workflow', 'adapters', 'required', 'checks', 'manager')}
        return '\nPlan JSON: '+json.dumps(compact)+'\nRecovery workspace: '+str(self.ws.root)+'.'
