# Android installer 84 source

Build 84 executes the checksum-pinned companion 83 installer explicitly with
`--companion`. It cannot accidentally run stale code in the tool cache.
The companion must be packaged at assets/companion.zip before building.
Supply the bundle checksum and size from the new release receipt.
No signing keys or passwords belong in this repository.

Build with Java 21 (javac by default, optional --ecj), Android platform 35
and build-tools 35:

    python build.py --android-jar /path/android.jar \
      --build-tools /path/build-tools --keystore /private/updater.jks \
      --password-file /private/password --alias qoder-updater \
      --bundle-sha256 <receipt-sha256> --bundle-bytes <receipt-bytes> \
      --output /path/Qoder-Tools-Installer-84.apk

The private key must match the installed com.qoder.share.tools certificate
to permit an Android package update. A newly generated key cannot update it.
The release includes this source; the terminal installer works independently
of an Android installer APK. The original Qoder Share editor remains build 79.
