# Build 87: shared automatic bridge

APK: Qoder-Share-AutoBridge-87.apk, version 0.3.9-auto-bridge.

Offline, Qoder Cloud and OpenCode share the gateway on localhost:8767, one application lifecycle startup helper, one idempotent Termux startup script and one Rish recovery monitor. The OpenCode engine remains on localhost:4096 behind the gateway.

Startup requests the existing Termux RUN_COMMAND permission. While an app screen is visible, the shared helper retries every 15 seconds. Termux services supervise the gateway, OpenCode engine and shared monitor. The monitor checks Rish every 20 seconds and can restart Shizuku only through an already authorized loopback ADB connection.

Android must permit Termux background operation. If Shizuku stops and authorized local ADB is unavailable, the app reports disconnected until Shizuku is started using Android's permitted method. Shizuku shell access is not root and cannot open every app's private data.

The unfiltered advertised catalogs from build 86 are retained. Provider execution still depends on credentials and provider access.

The shared monitor checks official model catalogs at startup and every 60 seconds (network latency can extend the check). Visible Cloud/OpenCode pages refresh every 15 seconds and on resume. All models.dev providers are merged without account or geography filtering; failed fetches retain the last saved catalog. There is no upstream push subscription, so updates are not instantaneous.
