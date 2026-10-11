# Qoder Share build 85
Installed APK: /sdcard/Download/Qoder-Share-OpenCode-85.apk
Version: 0.3.7-opencode, versionCode 85.
OpenCode runtime: 1.19.0, authenticated loopback port 4096, supervised by the opencode Termux service.

## Changed behavior
- Offline and parallel session APIs accept any existing accessible source folder or source file.
- App-source discovery runs for named apps even when the default starting directory contains other code.
- Discovery searches Termux home, configured roots and readable shared storage; package metadata and deep folder trees are supported.
- Selected source files resolve to their nearest project.
- Coding edits the actual project in place, with per-file backups and locks on the discovered project.
- Attachments work with selected accessible project locations.
- Native navigation exposes Offline, Cloud and OpenCode.
- OpenCode screen supports source discovery, model selection, custom API provider connection, Build/Plan agents, task output, stop, session continuation and diffs.
- API/server passwords stay on the phone; APK contains no embedded credentials.

## Verification
The full 160-test source suite passes, including eight source-location regression tests. Five installed session tests and three bridge tests pass.
OpenCode live acceptance edited calc.py in ~/qoder-source-location-acceptance, outside ~/projects and ~/coding-workspace, and passed its unit test.
OpenCode Termux MCP reports connected. Shizuku reports UID 2000 shell access.
Signed APK installation verified as versionCode 85; all three buttons and connected OpenCode interface verified through Android UI hierarchy.

## Reproduce
Update companion with the package installer, preserving models and sessions.
Run python setup_opencode.py on a compatible phone with grun already installed.
Run backend/patch_unified_native.py on the existing personal APK build environment to rebuild the app.
Aider is not yet installed or integrated in this build.
