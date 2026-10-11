# Installing Qoder Share Offline — Build 82

This is the installation procedure for the retained Build 82 release.

## What must be installed

Build 82 is an Android installer and an offline Termux tool cache. It is not a standalone editor APK.

You need:

1. An ARM64 Android phone with at least 4 GB free in Termux storage. 6–8 GB free is recommended for the archive, extraction, and installed tools.
2. The original signed Qoder Share APK (package `com.qoder.mobile.share`) already installed. Installer82 updates its backend; it does not replace this editor APK.
3. Official ARM64 Termux from [F-Droid](https://f-droid.org/packages/com.termux/) or the [Termux GitHub releases](https://github.com/termux/termux-app/releases). Play Store Termux is not supported.
4. [Qoder-Tools-Installer-82.apk](https://github.com/haithamelhusseinycv-cyber/qoder-share-offline/releases/download/offline-82/Qoder-Tools-Installer-82.apk).
5. [Qoder-Android-Tools-82.zip](https://github.com/haithamelhusseinycv-cyber/qoder-share-offline/releases/download/offline-82/Qoder-Android-Tools-82.zip), size 1,706,792,466 bytes.

The small companion ZIP is embedded in Installer82. It is useful for inspection or recovery, but it is not installed separately during the normal flow.

## Normal installation

1. Install official Termux and open it once.
2. Grant shared-storage access:

   ```sh
   termux-setup-storage
   ```

3. If Termux has network access and is missing the installer prerequisites, install them:

   ```sh
   pkg install -y curl python
   ```

4. Download the installer APK and full tools ZIP from the [Build 82 release](https://github.com/haithamelhusseinycv-cyber/qoder-share-offline/releases/tag/offline-82). Allow Android to install APKs from the browser or file manager when prompted.
5. Install and open `Qoder-Tools-Installer-82.apk`.
6. Grant the installer's **Termux RUN_COMMAND** permission.
7. Leave **Install the full offline ARM64 tools bundle** enabled. Tap **Select Android tools ZIP**, choose `Qoder-Android-Tools-82.zip`, and tap **Install update**.
8. Follow the progress in Termux. Accept the Android SDK license if Android displays it. Do not stop Termux while the archive is being verified or extracted.
9. When setup reports success, open the original Qoder Share app.

The installer verifies the archive size and SHA-256 before extraction. The expected archive SHA-256 is:

```
2f9287b1b9222bd305d734b549121c5d1df758c793f244eaedb4716884fe0ee7
```

The installed companion is under `~/qoder-selfhost`. The large ZIP remains in shared storage so it can be reused for recovery or updates.

## If RUN_COMMAND is refused

In Termux, run:

```sh
mkdir -p ~/.termux
echo 'allow-external-apps = true' >> ~/.termux/termux.properties
termux-reload-settings
```

Return to Installer82 and retry **Install update**.

## Fresh offline Termux

If a fresh Termux image does not have `curl` or Python and cannot install them from the network:

1. Extract `Qoder-Android-Tools-82.zip` with the Android file manager into a path without spaces, for example `Download/Qoder-Android-Tools-82`.
2. Open Termux and run:

   ```sh
   termux-setup-storage
   cd ~/storage/downloads/Qoder-Android-Tools-82
   bash bootstrap-termux.sh --android-sdk
   ```

This uses the cache's local Termux repository and then installs the offline tools. Install Installer82 afterward for the Android update UI and future updates.

## If the full ZIP is too large

Use the [split-download index](https://github.com/haithamelhusseinycv-cyber/qoder-share-offline/releases/download/offline-82/Qoder-Android-Tools-82-parts-index.md) and download all 41 parts, the manifest, and the assembler.

Place the parts in a directory named `Qoder-Android-Tools-82-parts`, rename `Qoder-Android-Tools-82-parts-manifest.json` to `manifest.json` inside that directory, then run:

```sh
python3 Qoder-Android-Tools-82-assemble.py Qoder-Android-Tools-82-parts Qoder-Android-Tools-82.zip
```

The assembler verifies every part and the final archive. Select the resulting ZIP in Installer82; an individual part cannot be selected.

## Shizuku and Rish

Shizuku is needed only for device operations such as package inspection, installation, instrumentation, and logcat. Install [Shizuku](https://github.com/RikkaApps/Shizuku/releases), start it using wireless debugging or root, and authorize Termux.

Export `rish_shizuku.dex` from Shizuku, then run:

```sh
sh ~/qoder-selfhost/setup-rish.sh ~/storage/downloads/rish/rish_shizuku.dex
rish -c id
```

A working shell identity is normally UID 2000. This is not root.

## Verify the installation

In Termux, inspect the companion stamp and tool inventory:

```sh
cat ~/qoder-selfhost/.qoder-companion-stamp.json
python3 ~/qoder-selfhost/tools_cli.py
```

The stamp should show companion build 82 and an offline-ready state after the full bundle probes pass. Some capabilities still depend on the phone and project: Frida may require root or Gadget, UI automation requires a test runner, and mitmproxy/ZAP need Android compatibility testing.

## Updates

Keep the original Qoder APK, models, projects, and Termux data. For a later release, install a higher Installer APK, select its matching verified tools ZIP, and rerun the full update. Do not use an older updater against companion82. Keep the previous ZIP until the new probes pass.
