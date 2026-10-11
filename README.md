# Qoder Share Offline — Build 82 with Installer83 hotfix

This repository retains the Build 82 Android tools installer and offline companion release. The original Installer82 and first full ZIP had a script/argument mismatch; Installer83 and the replacement ZIP are the corrected pair.

## Downloads

Open the [Build 82 corrected release](https://github.com/haithamelhusseinycv-cyber/qoder-share-offline/releases/tag/offline-82).

- **Qoder-Share-unified-0.3.5-79.apk** — original signed Qoder Share UI APK required by the installer.
- **Qoder-Tools-Installer-83.apk** — signed Android installer and Termux bridge. It updates an installed Installer82 using the same package and signing key.
- **Qoder-Tools-Installer-83-source.zip** — installer source and build files without private signing material.
- **Qoder-Share-Tools-82-release.zip** — companion package.
- **Qoder-Android-Tools-82.zip** — corrected complete ARM64 Termux tools bundle, 1,706,494,607 bytes.
- **Qoder-Android-Tools-82-parts-index.md** — 41 direct 40 MiB split downloads for clients that cannot fetch the full archive in one request.
- **[INSTALLATION-BUILD-82.md](INSTALLATION-BUILD-82.md)** — complete installation procedure, split-archive recovery, Shizuku/Rish setup, verification, and update instructions.
- **Qoder-Installer-82-Technical-Guide.md** — package layout, storage, updates, and edited-APK behavior.
- **Qoder-Share-Offline-Build-82-SHA256SUMS.txt** — checksums for the complete current package.
- **Qoder-Android-Tools-82-README.md**, status, receipt, and verification JSON — package inventory records.

Full archive SHA-256:

`f1d1eae62830f41f57ae3fa64c0363c785a65a6c37a01cb4ec776cfad92211c8`

Installer83 APK SHA-256:

`97549c0bac84e2093185e0b2d59581ff5f95d2fb5e08038ba8b1ff3790a30896`

The installer keeps the large toolchain in the Termux prefix. Termux is required for the coding and build tools; Shizuku/Rish is required for device operations such as package inspection, installation, and logcat. The complete installation and limitations are documented in [INSTALLATION-BUILD-82.md](INSTALLATION-BUILD-82.md).

Delete an older downloaded tools ZIP before selecting the replacement. Installer83 checks the replacement’s exact size and SHA-256 before extraction.

Build 79 was removed as a separate release, but its signed UI APK is included here because Installer83 requires it. Build 82 with the Installer83 compatibility fix is the only published release.
