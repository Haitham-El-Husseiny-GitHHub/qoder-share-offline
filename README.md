# Qoder Share Offline — personal build 79

Share this permanent release page:
https://github.com/haithamelhusseinycv-cyber/qoder-share-offline/releases/latest

Download **Qoder-Share-Offline-Setup-79.zip** for a new phone. The APK alone is for a phone whose companion backend is already configured. This personal modified build is not an official Qoder release.

## What is included

- Signed Android APK 0.3.5-local.21 (build 79).
- Independent Termux coding backend with model selector, two sessions, saved histories, live operations and Stop.
- Code search, exact patches, Git diffs, structured diagnostics and APK analysis tools.
- Installer and resumable, SHA-256-verified model downloader.
- Rish setup helper using files exported from the recipient's Shizuku app.

Weights and third-party Android apps are downloaded separately. No accounts, chat logs, GitHub credentials, inference keys, private signing keys or personal phone files are bundled. The installer creates a new private inference key on each phone. One model is loaded at a time; two jobs share it. Inference runs locally at zero Qoder/provider credits. Initial dependency/model downloads require internet. Downloading does not require a GPU rental.

## Requirements

ARM64 Android phone, Android 11 or newer recommended; tested on the connected OnePlus phone. For the default 3B model, 8 GB RAM and at least 5 GB free storage are recommended. Larger models require more RAM/storage and run slower. First-time installation on another physical phone has not been tested.

## Setup on another phone

1. Install **Termux** from https://github.com/termux/termux-app/releases or https://f-droid.org/packages/com.termux/ . Install optional **Termux:Boot** from the same signing source as Termux: https://f-droid.org/packages/com.termux.boot/ . Open Termux:Boot once if you install it.
2. Download the setup ZIP above and extract it with the phone's file manager into Downloads. Its folder is `Qoder-Share-Offline-Setup-79`.
3. Open Termux and run:

```sh
termux-setup-storage
pkg install -y python
cd ~/storage/downloads/Qoder-Share-Offline-Setup-79
python install.py --apk-tools
```

Approve storage access when asked. The installer verifies the bundled files, installs dependencies, downloads the approximately 1.93 GB default Qwen Coder 3B model, verifies its pinned SHA-256, creates the service and CLI, and starts the backend. A interrupted download can be resumed by repeating the command with `--update`. Existing models and sessions are retained. If you already have the verified GGUF, use `python install.py --no-model --apk-tools`, then import it:

```sh
python ~/qoder-selfhost/fetch_model.py coding --import-file /path/to/your/model.gguf
```

4. Open the included `Qoder-Share-unified-0.3.5-79.apk` in the phone's file manager and install it. Grant **Termux RUN_COMMAND** permission when the app requests it. If updating this personal build, Android can preserve its existing data. A differently signed Qoder installation cannot be upgraded in place; keep its data/export before any separate removal.
5. Set Termux, Qoder Share and Shizuku battery usage to **Unrestricted / Allow background activity** in Android settings. Keep Termux's service notification enabled.
6. For installed-app inspection and Android commands, install **Shizuku** from https://github.com/RikkaApps/Shizuku/releases . Start it using its own wireless-debugging/root instructions: https://shizuku.rikka.app/guide/setup/ . In Shizuku, open **Use Shizuku in terminal apps → Export files**. Export `rish_shizuku.dex`, then run in Termux (adjust the export folder):

```sh
sh ~/qoder-selfhost/setup-rish.sh ~/storage/downloads/rish/rish_shizuku.dex
rish -c id
```

Approve Termux in the Shizuku authorization prompt. Shell UID 2000 means a working shell connection; it is not root. Ordinary project coding works without Shizuku. Device operations require it. Android private-data permissions and APK signing still apply. After reboot Shizuku may need restarting; the app cannot silently approve Android permissions on another person's phone.
7. Open Qoder Share, choose Qwen Coder 3B, select your project under `~/coding-workspace` or `~/projects`, enter a task and run it. The screen displays live operations and Stop. The menu offers Save/Open/Clear/Delete/Export. Two jobs need separate non-overlapping project folders.

## Optional models

```sh
python ~/qoder-selfhost/fetch_model.py --list
python ~/qoder-selfhost/fetch_model.py granite
python ~/qoder-selfhost/fetch_model.py qwen35
```

Pinned downloads include coding, granite, dolphin, phi and qwen35; only coding downloads automatically. Granite and Qwen3.5 passed earlier coding trials; the included Dolphin MR and Phi catalog entries load but have not shown reliable repair performance. They are optional experiments. OmniCoder is catalogued but has no downloader entry in this package: supply the exact `OmniCoder-9B-Abliterated-Q4_K_M.gguf` (5,629,109,600 bytes) under `~/qoder-selfhost/models` yourself. No model weights are included in the ZIP.

## Offline CLI and recovery

```sh
~/bin/qoder-local-code --model coding --workspace ~/coding-workspace/my-project --profile BUILD --objective 'Find the bug, patch it, run tests and show the Git diff'
~/qoder-selfhost/bridge-start.sh
```

The service uses loopback ports 8767 and 18082; there is no cloud inference fallback. App startup recovers the existing service. Termux:Boot can start it after boot. Android force-stop, battery restrictions or insufficient RAM can interrupt it. APK rebuild tools create unsigned output copies and never install them automatically.

## Verification

Build 79 APK signature verified. 25 backend checks passed on the host and phone. APK import, metadata inspection, Java decompilation, full resource/all-DEX decoding and unsigned rebuilding passed on copied APKs. A real local-model repair applied the observed-checksum patch and passed its test. The setup package itself is checksum-checked and has installer/downloader simulation checks; a clean second-phone install remains untested.

Verify package files without installing:

```sh
python install.py --check
```

The manifest checks integrity against the published package. For authenticity, also compare the ZIP/APK SHA-256 in the release's SHA256SUMS.txt. The APK personal signing certificate SHA-256 is `bb7e569be3a0843c88ed789cc44f6953c2d1161d0c2a73106ffa616f7dad3158`.

Model sources: https://huggingface.co/bartowski/Qwen2.5-Coder-3B-Instruct-abliterated-GGUF and the pinned repositories/revisions in models.json. Runtime: https://github.com/ggml-org/llama.cpp . Termux packages: https://github.com/termux/termux-packages . Rish: https://github.com/RikkaApps/Shizuku-API/blob/master/rish/README.md . Third-party apps, runtimes and models retain their respective licensing terms.
