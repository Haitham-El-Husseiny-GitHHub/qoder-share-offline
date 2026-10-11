# Qoder Share offline

The current installation source is companion **83**, repaired after testing
on ARM64 Android with Termux and Shizuku/Rish. Continue using the original signed
Qoder Share editor build 79.

See [installation instructions](INSTALLATION-BUILD-83.md) and
[release downloads](https://github.com/haithamelhusseinycv-cyber/qoder-share-offline/releases/tag/offline-83).

The repository now contains the complete current backend, offline installer,
tool provisioning, tests, bundle builder, and Android installer source.
Private keys, model files, sessions and personal device state are excluded.
The Shizuku bridge hotfix checks identity output from both captured streams.
For installation, use both the full tools ZIP and the current small companion ZIP.

Run source checks with:

    python package_release.py
    python install.py --check
    python -m unittest discover -s tests -v

Build the companion ZIP with:

    python package_release.py --output Qoder-Share-Tools-83-release.zip

Rebuild the full offline tools ZIP with the verified ARM64 cache and extra wheel:

    python package_offline_bundle.py --cache /path/verified-cache \
      --vcs-wheel /path/vcs_versioning-2.6.0-py3-none-any.whl \
      --vcs-sha256 <verified-wheel-sha256> --output Qoder-Android-Tools-83.zip

Android Installer84 source is in android-installer. Its signing key must match
the installed installer certificate to support an APK update.
The terminal installer is independent of the Android installer APK.

# Project policy

The current [Qoder worker policy](Project/QODER-WORKER-POLICY.md) is saved in
the Project folder and regenerated from the implementation when packaging.
