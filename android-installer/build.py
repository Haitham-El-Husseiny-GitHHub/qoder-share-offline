#!/usr/bin/env python3
"""Compile a small native Android installer using verified Android tooling."""
import argparse,hashlib,json,os,subprocess,shutil,zipfile
from pathlib import Path

BASE=Path(__file__).resolve().parent
def run(argv):subprocess.run([str(a) for a in argv],check=True)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--android-jar',required=True);parser.add_argument('--ecj');parser.add_argument('--build-tools',required=True);parser.add_argument('--keystore',required=True);parser.add_argument('--password-file',required=True);parser.add_argument('--alias',default='qoder-updater');parser.add_argument('--output',required=True);parser.add_argument('--bundle-sha256',required=True);parser.add_argument('--bundle-bytes',type=int,required=True);args=parser.parse_args()
    android=Path(args.android_jar).resolve();ecj=Path(args.ecj).resolve() if args.ecj else None;tools=Path(args.build_tools).resolve();out=Path(args.output).resolve();password=Path(args.password_file).resolve()
    if password.stat().st_mode&0o077:raise SystemExit('Signing password file must be mode 600.')
    if out.exists():raise SystemExit('Choose a new output APK filename.')
    build=BASE/'build'
    if build.exists():shutil.rmtree(build)
    for name in ('classes','dex','host'): (build/name).mkdir(parents=True)
    payload=BASE/'assets/companion.zip';sha=digest(payload)
    if len(args.bundle_sha256)!=64 or any(c not in '0123456789abcdef' for c in args.bundle_sha256) or args.bundle_bytes<1:
        raise SystemExit('Invalid full bundle checksum or size.')
    (build/'BuildConfig.java').write_text('package com.qoder.share.tools; public final class BuildConfig { public static final String COMPANION_SHA256="'+sha+'"; public static final long COMPANION_BYTES='+str(payload.stat().st_size)+'L; public static final String BUNDLE_SHA256="'+args.bundle_sha256+'"; public static final long BUNDLE_BYTES='+str(args.bundle_bytes)+'L; }\n')
    compiler=['java','-jar',ecj,'-1.8'] if ecj else ['javac','-source','8','-target','8']
    sources=sorted((BASE/'src').rglob('*.java'))+[build/'BuildConfig.java']
    run([*compiler,'-bootclasspath',android,'-classpath',android,'-d',build/'classes',*sources])
    # Run pure Java network and shell checks independently of Android.
    run([*compiler,'-d',build/'host',BASE/'src/com/qoder/share/tools/PayloadServer.java',BASE/'src/com/qoder/share/tools/SetupScript.java',BASE/'tests/InstallerProtocolTest.java'])
    run(['java','-cp',build/'host','InstallerProtocolTest',build/'minimal-setup.sh'])
    run(['java','-cp',tools/'lib/d8.jar','com.android.tools.r8.D8','--lib',android,'--min-api','28','--output',build/'dex',*sorted((build/'classes').rglob('*.class'))])
    run([tools/'aapt2','compile','--dir',BASE/'res','-o',build/'resources.zip'])
    run([tools/'aapt2','link','-o',build/'unsigned.apk','-I',android,'--manifest',BASE/'AndroidManifest.xml',build/'resources.zip'])
    with zipfile.ZipFile(build/'unsigned.apk','a',zipfile.ZIP_DEFLATED) as z:
        for p in sorted((build/'dex').glob('*.dex')):z.write(p,p.name)
        for p in sorted((BASE/'assets').rglob('*')):
            if p.is_file():z.write(p,'assets/'+str(p.relative_to(BASE/'assets')))
    run([tools/'zipalign','-P','16','4',build/'unsigned.apk',build/'aligned.apk'])
    run([tools/'zipalign','-c','-P','16','4',build/'aligned.apk'])
    out.parent.mkdir(parents=True,exist_ok=True)
    run(['java','-jar',tools/'lib/apksigner.jar','sign','--ks',Path(args.keystore).resolve(),'--ks-key-alias',args.alias,'--ks-pass','file:'+str(password),'--out',out,build/'aligned.apk'])
    run(['java','-jar',tools/'lib/apksigner.jar','verify','--verbose','--print-certs',out])
    run([tools/'zipalign','-c','-P','16','4',out])
    result={'apk':out.name,'bytes':out.stat().st_size,'sha256':digest(out),'companion_sha256':sha,'bundle_sha256':args.bundle_sha256,'bundle_bytes':args.bundle_bytes,'installer_protocol_checks':22,'android_sdk':35,'min_sdk':28,'on_device_tested':False,'termux_and_shizuku_tested':False}
    (out.parent/(out.name+'.sha256')).write_text(result['sha256']+'  '+out.name+'\n')
    (out.parent/(out.stem+'-verification.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
