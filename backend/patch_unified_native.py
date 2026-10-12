"""Compile and package the native offline task screen into the personal APK."""
from pathlib import Path
import os, re, subprocess, zipfile

HOME = Path('/data/data/com.termux/files/home')
SOURCE = Path(__file__).resolve().parent
ROOT = HOME / 'qoder-native-share/decoded-selfhost'
BUILD = HOME / 'qoder-native-share/unified-91'
SDK = HOME / 'android-sdk'
JAR = SDK / 'platforms/android-36/android.jar'
BUILD.mkdir(exist_ok=True)
(BUILD/'classes').mkdir(exist_ok=True)
(BUILD/'dex').mkdir(exist_ok=True)
def run(args):
    print('Running '+str(args[0]),flush=True)
    subprocess.run([str(a) for a in args],check=True,env={**os.environ,'TMPDIR':'/data/data/com.termux/files/usr/tmp'})

# Install one lifecycle bridge for every activity, including original cloud sessions.
original_app=ROOT/'smali/com/qoder/mobile/QoderApplication.smali'
app=ROOT/'smali_classes5/com/qoder/mobile/QoderApplication.smali'
# The original primary dex is full. Keep the Application startup hook in a new dex.
if original_app.exists():
    app.parent.mkdir(parents=True,exist_ok=True)
    original_app.replace(app)
code=app.read_text()
anchor='.method public final onCreate()V\n    .locals 14'
if 'Lcom/qoder/share/StartupBridge;->install' not in code:
    if anchor not in code:raise ValueError('Application startup method changed; inspect before patching.')
    code=code.replace(anchor,anchor+'\n\n    invoke-static {p0}, Lcom/qoder/share/StartupBridge;->install(Landroid/app/Application;)V')
app.write_text(code)

manifest=ROOT/'AndroidManifest.xml'
s=manifest.read_text()
s=s.replace('android:name="com.qoder.share.LocalCodingActivity"','android:name="com.qoder.share.UnifiedCodingActivity"')
assert 'android:name="com.qoder.share.UnifiedCodingActivity"' in s
if 'moe.shizuku.privileged.api' not in s:s=s.replace('</queries>','<package android:name="moe.shizuku.privileged.api"/></queries>')
if 'com.qoder.share.OpenCodeActivity' not in s:s=s.replace('</application>','<activity android:name="com.qoder.share.OpenCodeActivity" android:exported="false" android:windowSoftInputMode="adjustResize"/></application>')
if 'com.qoder.share.CloudCatalogActivity' not in s:s=s.replace('</application>','<activity android:name="com.qoder.share.CloudCatalogActivity" android:exported="false" android:windowSoftInputMode="adjustResize"/></application>')
manifest.write_text(s)
# Extend the original session model lists, preserving model IDs and permissions.
for relative, methods in [('smali/U7/l.smali', ['.method public static l(Ljava/util/List;)Ljava/util/ArrayList;']),
                          ('smali/M7/O.smali', ['.method public final j()Ljava/util/List;', '.method public final k()Ljava/util/List;'])]:
    path=ROOT/relative
    body=path.read_text()
    for signature in methods:
        start=body.index(signature);end=body.index('.end method',start)
        section=body[start:end]
        if 'Lcom/qoder/share/QoderEnhancements;->augment' not in section:
            section=re.sub(r'    return-object (v\d+)',lambda m:'    invoke-static {'+m[1]+'}, Lcom/qoder/share/QoderEnhancements;->augment(Ljava/util/List;)Ljava/util/ArrayList;\n    move-result-object '+m[1]+'\n\n'+m[0],section)
            body=body[:start]+section+body[end:]
    path.write_text(body)
# The local button in the optional cloud screen must return to this native
# workspace rather than opening a browser or Custom Tab.
p=ROOT/'smali/com/qoder/share/SelfHostedChat.smali'
s=p.read_text();start=s.index('.method public onClick(');end=s.index('.end method',start)+len('.end method')
s=s[:start]+'''.method public onClick(Landroid/view/View;)V
    .locals 3
    iget-object v0, p0, Lcom/qoder/share/SelfHostedChat;->activity:Landroid/app/Activity;
    new-instance v1, Landroid/content/Intent;
    invoke-direct {v1}, Landroid/content/Intent;-><init>()V
    const-string v2, "com.qoder.share.UnifiedCodingActivity"
    invoke-virtual {v1, v0, v2}, Landroid/content/Intent;->setClassName(Landroid/content/Context;Ljava/lang/String;)Landroid/content/Intent;
    invoke-virtual {v0, v1}, Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V
    return-void
.end method'''+s[end:]
p.write_text(s)
p=ROOT/'apktool.yml'
s=p.read_text();s=re.sub(r'versionCode: .*','versionCode: 91',s);s=re.sub(r'versionName: .*','versionName: 0.3.13-restart',s);p.write_text(s)
run(['javac','-source','8','-target','8','-classpath',JAR,'-d',BUILD/'classes',*sorted((SOURCE/'native').glob('*.java'))])
classes=list((BUILD/'classes').rglob('*.class'))
run(['java','-cp',SDK/'build-tools/36.0.0/lib/d8.jar','com.android.tools.r8.D8','--lib',JAR,'--min-api','30','--output',BUILD/'dex',*classes])
run(['apktool','b',ROOT,'-o',BUILD/'base.apk'])
with zipfile.ZipFile(BUILD/'base.apk') as original,zipfile.ZipFile(BUILD/'unsigned.apk','w') as out:
    for info in original.infolist():
        if info.filename!='classes4.dex':out.writestr(info,original.read(info.filename))
    out.write(BUILD/'dex/classes.dex','classes4.dex',compress_type=zipfile.ZIP_STORED)
run(['zipalign','-f','-p','4',BUILD/'unsigned.apk',BUILD/'aligned.apk'])
apk=Path('/sdcard/Download/Qoder-Share-Sessions-91.apk')
run(['apksigner','sign','--ks',HOME/'qoder-native-share/share.keystore','--ks-key-alias','qoder-share','--ks-pass','file:'+str(HOME/'qoder-native-share/signing.pass'),'--out',apk,BUILD/'aligned.apk'])
run(['apksigner','verify','--print-certs',apk])
print('BUILT '+str(apk),flush=True)

