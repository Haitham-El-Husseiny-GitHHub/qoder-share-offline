# Qoder Share Offline — Build 82

This repository retains the Build 82 Android tools installer and offline companion release.

## Downloads

Open the [Build 82 release](https://github.com/haithamelhusseinycv-cyber/qoder-share-offline/releases/tag/offline-82).

- **Qoder-Tools-Installer-82.apk** — Android installer and Termux bridge.
- **Qoder-Share-Tools-82-release.zip** — companion package.
- **Qoder-Android-Tools-82.zip** — complete ARM64 Termux tools bundle, 1,706,792,466 bytes.
- **Qoder-Android-Tools-82-parts-index.md** — 41 direct 40 MiB split downloads for clients that cannot fetch the full archive in one request.
- **[INSTALLATION-BUILD-82.md](INSTALLATION-BUILD-82.md)** — complete installation procedure, offline fallback, Shizuku/Rish setup, verification, and update instructions.
- **Qoder-Installer-82-Technical-Guide.md** — package layout, storage, updates, and edited-APK behavior.

Full archive SHA-256:

`2f9287b1b9222bd305d734b549121c5d1df758c793f244eaedb4716884fe0ee7`

Installer APK SHA-256:

`e477ce6357999355d74efce87735642f7ac35f076c464d6665ae5ac3ed04670b`

The installer keeps the large toolchain in the Termux prefix. Termux is required for the coding and build tools; Shizuku/Rish is required for device operations such as package inspection, installation, and logcat. The complete installation and limitations are documented in [INSTALLATION-BUILD-82.md](INSTALLATION-BUILD-82.md).

Build 79 was removed. Build 82 is the only published release.
