# Qoder Share offline companion 83: Termux installation repair

Use official ARM64 Termux. Keep the original signed Qoder Share build 79 editor
(com.qoder.mobile.share). This package updates the backend and tools, preserving
models, sessions, jobs, the inference key and user tool configuration.

Download Qoder-Android-Tools-83.zip, Qoder-Share-Tools-83-release.zip,
and Qoder-Offline-83-SHA256SUMS.txt from
https://github.com/haithamelhusseinycv-cyber/qoder-share-offline/releases/tag/offline-83.
Chrome downloads normally appear in /storage/emulated/0/Download.
Allow Termux storage access with termux-setup-storage if needed.

The terminal installer requires python3 and curl in Termux. If the base lacks
them, extract the archive with Android's file manager and use the included
bootstrap-termux.sh against its local package cache. No remote package repository
is required after downloading the release.

In Termux, stop active coding jobs, then run:

    cd ~/storage/downloads
    sha256sum -c Qoder-Offline-83-SHA256SUMS.txt
    mkdir -p ~/.cache/qoder-install-83
    python3 -m zipfile -e Qoder-Android-Tools-83.zip ~/.cache/qoder-install-83
    python3 -m zipfile -e Qoder-Share-Tools-83-release.zip ~/.cache/qoder-install-83
    cd ~/.cache/qoder-install-83/Qoder-Android-Tools-83
    python3 ../Qoder-Share-Tools-83/install_offline_tools.py --cache . \
      --companion ../Qoder-Share-Tools-83 --android-sdk

Read and accept the SDK license when prompted. Leave Termux running while
Rust and Python extensions compile. Do not run an older installer afterward.
A successful installation has an offline-ready companion 83 stamp at
~/qoder-selfhost/.qoder-companion-stamp.json and no core probe failures in
~/qoder-selfhost/offline-tools-result.json.

Build 83 fixes APKEditor's version-query exit status, zipalign's invalid help
probe, the missing vcs-versioning wheel, ast-grep's deprecated sg shim, and
TypeScript language-server launchers that depended on /usr/bin/env.
Readiness is recorded only after the actual core tool probes pass.
The repository also contains Android Installer84 source, which uses the
explicit verified companion rather than a script from the tools cache.
An APK update must be signed with the existing installer private key; that
private key is not distributed with the release.

Shizuku/Rish requires user authorization. ADB pairing, Frida target access,
project-specific Gradle/npm dependencies, mitmproxy compatibility and ZAP
scans still require their own checks. Success on this phone does not guarantee
every Android version or project will install without errors.

The current small companion includes the Shizuku bridge fix: Rish identity
output can arrive on stderr, so both streams are checked. Always extract and
use the separate verified companion above; the full tools cache is retained
without a large re-download for this backend hotfix.

The current small companion also repairs installed-app routing, repeat-failure
handling, baseline reporting, stale verification reuse, signature evidence,
and offline fetch guards. WORKBENCH-DESIGN.md describes the corrected workflow
and remaining implementation gaps. Offline source discovery stays on the phone;
GitHub/Cloudflare discovery requires explicitly online configuration.
