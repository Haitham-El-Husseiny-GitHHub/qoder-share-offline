package com.qoder.share.tools;

/** Generates the bounded, offline Termux handoff used by Installer84. */
public final class SetupScript {
    private SetupScript() {}

    public static String build(String baseUrl, boolean installBundle, String companionSha256,
                                long companionBytes, String bundleSha256, long bundleBytes) {
        if (!baseUrl.matches("http://127\\.0\\.0\\.1:[0-9]{1,5}/[0-9a-f]{32}") ||
                !companionSha256.matches("[0-9a-f]{64}") ||
                !bundleSha256.matches("[0-9a-f]{64}") || companionBytes < 1 || bundleBytes < 1) {
            throw new IllegalArgumentException("Invalid installer transfer address or checksum.");
        }
        StringBuilder s = new StringBuilder();
        s.append("set -euo pipefail\numask 077\n");
        s.append("export TMPDIR=\"$PREFIX/tmp\" ANDROID_DATA=/data ANDROID_ROOT=/system\n");
        s.append("qoder_status_url='").append(baseUrl).append("/status'\n");
        s.append("qoder_task_dir=\"$HOME/.cache/qoder-tools-installer-84\"\n");
        s.append("mkdir -p \"$qoder_task_dir\"\n: >\"$qoder_task_dir/install.log\"\n");
        s.append("post() { curl --fail --silent --show-error --max-time 5 ");
        s.append("--data-urlencode \"phase=$1\" --data-urlencode \"message=$2\" ");
        s.append("--data-urlencode \"exit_code=${3:--1}\" \"$qoder_status_url\" >/dev/null 2>&1 || true; }\n");
        s.append("finish() { qoder_rc=$?; trap - EXIT; set +e; ");
        s.append("if [ \"$qoder_rc\" -eq 0 ]; then post completed ");
        s.append("'Offline tools installed and verified. Open Qoder Share to continue.' 0; ");
        s.append("else [ ! -x \"$HOME/qoder-selfhost/bridge-start.sh\" ] || ");
        s.append("sh \"$HOME/qoder-selfhost/bridge-start.sh\" >/dev/null 2>&1; ");
        s.append("qoder_note=$(tail -c 1500 \"$qoder_task_dir/install.log\" 2>/dev/null); ");
        s.append("post failed \"Setup stopped (exit $qoder_rc). Check Termux. $qoder_note\" ");
        s.append("\"$qoder_rc\"; fi; printf '\\nQoder tools setup exit: %s\\n' \"$qoder_rc\"; ");
        s.append("exit \"$qoder_rc\"; }\ntrap finish EXIT\n");
        s.append("require_cmd() { command -v \"$1\" >/dev/null 2>&1 || { ");
        s.append("printf 'Missing offline prerequisite: %s\\n' \"$1\" >&2; return 127; }; }\n");
        s.append("require_cmd curl\nrequire_cmd python3\n");
        s.append("verify_file() { python3 - \"$1\" \"$2\" \"$3\" <<'QODER_VERIFY_FILE'\n");
        s.append("import hashlib,sys\nfrom pathlib import Path\n");
        s.append("p=Path(sys.argv[1]);expected_size=int(sys.argv[2]);expected_hash=sys.argv[3]\n");
        s.append("if not p.is_file() or p.stat().st_size != expected_size: raise SystemExit('Unexpected archive size: '+str(p))\n");
        s.append("h=hashlib.sha256()\nwith p.open('rb') as f:\n while True:\n  b=f.read(8*1024*1024)\n  if not b: break\n  h.update(b)\n");
        s.append("if h.hexdigest() != expected_hash: raise SystemExit('Archive checksum mismatch: '+str(p))\n");
        s.append("QODER_VERIFY_FILE\n}\n");
        s.append("download() { qoder_url=$1; qoder_file=$2; qoder_hash=$3; qoder_size=$4; ");
        s.append("if [ -f \"$qoder_file\" ] && verify_file \"$qoder_file\" \"$qoder_size\" \"$qoder_hash\"; then return; fi; ");
        s.append("if [ -s \"$qoder_file.partial\" ]; then ");
        s.append("curl --fail --silent --show-error --connect-timeout 5 --max-time 14400 -C - ");
        s.append("\"$qoder_url\" -o \"$qoder_file.partial\"; else rm -f \"$qoder_file.partial\"; ");
        s.append("curl --fail --silent --show-error --connect-timeout 5 --max-time 14400 ");
        s.append("\"$qoder_url\" -o \"$qoder_file.partial\"; fi; ");
        s.append("verify_file \"$qoder_file.partial\" \"$qoder_size\" \"$qoder_hash\"; ");
        s.append("mv -f \"$qoder_file.partial\" \"$qoder_file\"; }\n");
        s.append("post downloading 'Reading the signed companion from this APK.'\n");
        s.append("download '").append(baseUrl).append("/companion.zip' ");
        s.append("\"$qoder_task_dir/companion.zip\" '").append(companionSha256).append("' ").append(companionBytes).append("\n");
        s.append("qoder_extract_dir=$(mktemp -d \"$qoder_task_dir/package.XXXXXXXX\")\n");
        s.append("qoder_bundle_dir=''\n");
        s.append("python3 - \"$qoder_task_dir/companion.zip\" \"$qoder_extract_dir\" <<'QODER_EXTRACT_COMPANION'\n");
        s.append("import os,sys,zipfile\nfrom pathlib import Path\n");
        s.append("p=Path(sys.argv[1]);out=Path(sys.argv[2]).resolve()\n");
        s.append("with zipfile.ZipFile(p) as z:\n infos=z.infolist()\n");
        s.append(" if len(infos)>200 or sum(i.file_size for i in infos)>5000000: raise SystemExit('Companion archive exceeds limits.')\n");
        s.append(" for i in infos:\n  name=Path(i.filename);target=(out/name).resolve()\n");
        s.append("  if name.is_absolute() or '..' in name.parts or (i.external_attr>>16)&0o170000==0o120000 or os.path.commonpath((str(out),str(target))) != str(out): raise SystemExit('Unsafe companion archive path.')\n");
        s.append("  if i.is_dir(): target.mkdir(parents=True,exist_ok=True); continue\n");
        s.append("  target.parent.mkdir(parents=True,exist_ok=True)\n  with z.open(i) as src,target.open('wb') as dst:\n");
        s.append("   while True:\n    b=src.read(1024*1024)\n    if not b: break\n    dst.write(b)\n");
        s.append("  if i.external_attr>>16&0o111: target.chmod(0o700)\n");
        s.append("root=out/'Qoder-Share-Tools-83'\n");
        s.append("if not (root/'package.json').is_file() or not (root/'install.py').is_file(): raise SystemExit('Companion 83 root is missing.')\n");
        s.append("QODER_EXTRACT_COMPANION\n");
        s.append("qoder_companion_root=\"$qoder_extract_dir/Qoder-Share-Tools-83\"\n");
        s.append("python3 - \"$qoder_companion_root/package.json\" \"$HOME/qoder-selfhost/.qoder-companion-stamp.json\" <<'QODER_VERSION_GUARD'\n");
        s.append("import json,sys\nfrom pathlib import Path\n");
        s.append("incoming=json.loads(Path(sys.argv[1]).read_text())\n");
        s.append("if not isinstance(incoming.get('build'),int): raise SystemExit('Companion manifest has no build number.')\n");
        s.append("stamp=Path(sys.argv[2])\nif stamp.exists():\n current=json.loads(stamp.read_text()).get('companion_build')\n");
        s.append(" if not isinstance(current,int): raise SystemExit('Existing companion stamp is invalid.')\n");
        s.append(" if current>incoming['build']: raise SystemExit('Refusing to overwrite a newer companion build.')\n");
        s.append("QODER_VERSION_GUARD\n");
        s.append("cd \"$qoder_companion_root\"\npython3 install.py --check\n");
        s.append("post installing '");
        s.append(installBundle ? "Installing the signed ARM64 offline bundle. No remote package repository is used."
                                : "Installing the companion update. Existing tools are retained.");
        s.append("'\n");
        if (installBundle) {
            s.append("qoder_free_kb=$(df -Pk \"$HOME\" | awk 'NR==2 {print $4}')\n");
            s.append("[ \"${qoder_free_kb:-0}\" -ge 4000000 ] || { ");
            s.append("printf '%s\\n' 'At least 4 GB of free Termux storage is required for the full offline bundle.' >&2; exit 1; }\n");
            s.append("post downloading 'Downloading the verified Android tools bundle; this can take a while and can resume.'\n");
            s.append("download '").append(baseUrl).append("/android-tools.zip' ");
            s.append("\"$qoder_task_dir/android-tools.zip\" '").append(bundleSha256).append("' ");
            s.append(bundleBytes).append("\n");
            s.append("qoder_bundle_dir=$(mktemp -d \"$qoder_task_dir/bundle.XXXXXXXX\")\n");
            s.append("python3 - \"$qoder_task_dir/android-tools.zip\" \"$qoder_bundle_dir\" <<'QODER_EXTRACT_BUNDLE'\n");
            s.append("import os,sys,zipfile\nfrom pathlib import Path\n");
            s.append("p=Path(sys.argv[1]);out=Path(sys.argv[2]).resolve()\n");
            s.append("with zipfile.ZipFile(p) as z:\n infos=z.infolist()\n");
            s.append(" if len(infos)>1000 or sum(i.file_size for i in infos)>5000000000: raise SystemExit('Android tools archive exceeds limits.')\n");
            s.append(" for i in infos:\n  name=Path(i.filename);target=(out/name).resolve()\n");
            s.append("  if name.is_absolute() or '..' in name.parts or (i.external_attr>>16)&0o170000==0o120000 or os.path.commonpath((str(out),str(target))) != str(out): raise SystemExit('Unsafe Android tools archive path.')\n");
            s.append("  if i.is_dir(): target.mkdir(parents=True,exist_ok=True); continue\n");
            s.append("  target.parent.mkdir(parents=True,exist_ok=True)\n  with z.open(i) as src,target.open('wb') as dst:\n");
            s.append("   while True:\n    b=src.read(8*1024*1024)\n    if not b: break\n    dst.write(b)\n");
            s.append("  if i.external_attr>>16&0o111: target.chmod(0o700)\n");
            s.append("root=out/'Qoder-Android-Tools-83'\n");
            s.append("if not (root/'inventory.json').is_file() or not (root/'install_offline_tools.py').is_file(): raise SystemExit('Android tools bundle root is missing.')\n");
            s.append("QODER_EXTRACT_BUNDLE\n");
            s.append("qoder_bundle_root=\"$qoder_bundle_dir/Qoder-Android-Tools-83\"\n");
            s.append("post installing 'Installing local Termux packages and configuring adapters. SDK license text will be shown in Termux.'\n");
            s.append("python3 -u \"$qoder_companion_root/install_offline_tools.py\" --companion \"$qoder_companion_root\" --cache \"$qoder_bundle_root\" --android-sdk --bundle-sha256 '");
            s.append(bundleSha256).append("' 2>&1 | tee \"$qoder_task_dir/install.log\"\n");
        } else {
            s.append("python3 -u install.py --update --no-model --offline 2>&1 | tee \"$qoder_task_dir/install.log\"\n");
        }
        s.append("post verifying 'Checking the installed companion stamp and backend files.'\n");
        s.append("python3 - \"$HOME/qoder-selfhost\" \"$qoder_companion_root/package.json\" <<'QODER_VERIFY'\n");
        s.append("import hashlib,json,sys\nfrom pathlib import Path\n");
        s.append("target=Path(sys.argv[1]);manifest=json.loads(Path(sys.argv[2]).read_text())\n");
        s.append("for name,expected in manifest['sha256'].items():\n if name.startswith('backend/'):\n  p=target/name[8:]\n  if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected: raise SystemExit('Installed file mismatch: '+name)\n");
        s.append("stamp=json.loads((target/'.qoder-companion-stamp.json').read_text())\n");
        s.append("if stamp.get('companion_build') != manifest.get('build'): raise SystemExit('Installed companion stamp does not match build 83.')\n");
        s.append("if stamp.get('state') not in ('companion-installed','offline-ready'): raise SystemExit('Installed companion is not promoted.')\n");
        s.append("print('Installed companion files and stamp verified.')\nQODER_VERIFY\n");
        s.append("python3 \"$HOME/qoder-selfhost/tools_cli.py\" >\"$qoder_task_dir/tool-availability.json\"\n");
        s.append("rm -rf -- \"$qoder_extract_dir\"; [ -z \"$qoder_bundle_dir\" ] || rm -rf -- \"$qoder_bundle_dir\"\n");
        return s.toString();
    }
}
