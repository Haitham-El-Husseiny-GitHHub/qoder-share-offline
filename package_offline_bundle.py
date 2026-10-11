#!/usr/bin/env python3
"""Rebuild an offline cache with current companion source and verified extra wheels."""
import argparse, hashlib, json, shutil, tempfile, zipfile
from pathlib import Path
import package_release
import install_offline_tools

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def build(cache, wheel, wheel_hash, output):
    if output.exists():raise ValueError('Output exists; choose a new release filename.')
    if digest(wheel)!=wheel_hash:raise ValueError('Extra wheel checksum mismatch.')
    install_offline_tools.verify(cache)
    package_release.manifest()
    with tempfile.TemporaryDirectory(prefix='qoder-bundle-build-') as folder:
        root=Path(folder)/'Qoder-Android-Tools-83'
        shutil.copytree(cache,root)
        companion=root/'android/qoder-companion'
        shutil.rmtree(companion)
        companion.mkdir()
        for source in package_release.files()+[package_release.BASE/'package.json']:
            target=companion/source.relative_to(package_release.BASE)
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        shutil.copy2(package_release.BASE/'install_offline_tools.py',root/'install_offline_tools.py')
        shutil.copy2(wheel,root/'android/python-packages'/wheel.name)
        data=json.loads((root/'inventory.json').read_text())
        # Inventory every payload, including new transitive Python dependencies.
        entries=[{'path':str(f.relative_to(root)),'bytes':f.stat().st_size,'sha256':digest(f)}
                 for f in sorted((root/'android').rglob('*')) if f.is_file()]
        data.update(build=83,files=entries,total_bytes=sum(e['bytes'] for e in entries),
                    installed_on_user_phone=False)
        (root/'inventory.json').write_text(json.dumps(data,indent=2)+'\n')
        (root/'SHA256SUMS').write_text(''.join(e['sha256']+'  '+e['path']+'\n' for e in entries))
        (root/'README.md').write_text((package_release.BASE/'INSTALLATION-BUILD-83.md').read_text())
        (root/'TOOL-STATUS.json').unlink(missing_ok=True)
        output.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for f in sorted(root.rglob('*')):
                if f.is_file():
                    compressed=f.suffix in {'.deb','.zip','.gz','.xz','.tgz','.whl','.jar'}
                    archive.write(f,'Qoder-Android-Tools-83/'+str(f.relative_to(root)),compress_type=zipfile.ZIP_STORED if compressed else zipfile.ZIP_DEFLATED)
    receipt={'file':output.name,'bytes':output.stat().st_size,'sha256':digest(output),'companion_build':83}
    output.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--vcs-wheel',type=Path,required=True)
    p.add_argument('--vcs-sha256',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.cache,a.vcs_wheel,a.vcs_sha256,a.output)
