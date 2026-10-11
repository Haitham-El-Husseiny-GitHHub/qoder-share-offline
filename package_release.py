#!/usr/bin/env python3
"""Build a checksum-checked companion update, excluding all phone state."""
import argparse
import ast
import hashlib
import json
import zipfile
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT_FILES=['WORKBENCH-DESIGN.md','README.md','ENGINEERING_TOOLS.md','VERIFICATION.md','ANDROID_TOOLS.md','install.py','install_offline_tools.py','bootstrap-termux.sh','fetch_model.py','models.json','setup-rish.sh','setup_tools.py','tools.lock.json','package_release.py','package_offline_bundle.py','INSTALLATION-BUILD-83.md']
EXTENSIONS={'.py','.json','.md','.sh','.js','.html','.java','.yaml','.yml'}
ROOT_FILES.append('Project/QODER-WORKER-POLICY.md')
ROOT_FILES.append('Project/ATTACHMENTS.md')


def sync_worker_policy():
    source=BASE/'backend/coding_runner.py'
    tree=ast.parse(source.read_text())
    policy=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='WORKER_POLICY' for target in node.targets))
    path=BASE/'Project/QODER-WORKER-POLICY.md'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('# Qoder worker policy\n\n'
                    'Implemented in [backend/coding_runner.py](../backend/coding_runner.py) as `WORKER_POLICY`.\n'
                    'The execution guards are in the same file; router tool filtering is in '
                    '[backend/router_runtime.py](../backend/router_runtime.py).\n\n'
                    'This document is regenerated from the hardcoded policy by `python3 package_release.py`. '
                    'Update the implementation first, then regenerate the package manifest so the policy '
                    'document and checksums stay synchronized.\n\n```text\n'+policy+'\n```\n')


def files():
    selected=[BASE/name for name in ROOT_FILES]
    for directory in ('backend','tests'):
        selected.extend(p for p in (BASE/directory).rglob('*') if p.is_file() and p.suffix in EXTENSIONS and
                        not any(v in {'__pycache__','runtime','sessions','jobs','models','tools','.git'} for v in p.relative_to(BASE).parts) and p.name!='tools.json')
    return sorted(selected)


def manifest():
    sync_worker_policy()
    hashes={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files()}
    data={'build':83,'apk_build':79,'attachments_apk_build':84,'kind':'companion-update','baseline_release':'offline-79','sha256':hashes}
    (BASE/'package.json').write_text(json.dumps(data,indent=2)+'\n')
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    data=manifest()
    if args.output:
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists():raise SystemExit('Output already exists; choose a new package filename.')
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            for p in files()+[BASE/'package.json']:z.write(p,'Qoder-Share-Tools-83/'+str(p.relative_to(BASE)))
        print(json.dumps({'file':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bytes':output.stat().st_size,'files':len(data['sha256'])},indent=2))
    else:print('Updated package.json:',len(data['sha256']),'files')
