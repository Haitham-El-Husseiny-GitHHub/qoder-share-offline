# Android tool downloads and adapters — update 82

The Android bundle contains downloaded packages, not just installation recipes.
It targets official **Termux, ARM64 Android**, alongside the installed Qoder Share
build 79 APK. It contains no model weights or replacement Qoder Share APK.

## Install the downloaded cache

Extract `Qoder-Android-Tools-82.zip` on the phone. Install the included Termux
and Shizuku APKs using Android's installer if they are missing. Preserve existing
installations. Open Termux and grant shared storage access with
`termux-setup-storage`. Stop active Qoder jobs, then run:

```bash
cd ~/storage/downloads/Qoder-Android-Tools-82
bash bootstrap-termux.sh --android-sdk
```

The installer verifies the file inventory, uses a local APT repository, skips
existing commands, updates the companion, configures Java tools and language
servers, builds ast-grep from vendored dependencies and sets up Rish if absent.
The TypeScript cache uses the JavaScript-based compiler 5.9.3 and language server
6.0.2. Its lockfile rejects platform-specific dependencies. The bundled server
passes real definition, reference and diagnostic requests on the build host.
Update 82 repairs the earlier bundled TypeScript 7 installation in its managed
directory while preserving external language-server configurations.

Python is bootstrapped from the cache if necessary. Python LSP's ujson extension
and ast-grep still compile locally; source downloads are not prebuilt executables.
SDK licensing is presented during installation. Signing keys and model/session
data are preserved. Compiler builds may need substantial RAM, time and storage.

The installer performs no online package fetches. An installation error stops
the current step; it does not mark the toolset ready. Inspect the error before
retrying. Keep `inventory.json`, `SHA256SUMS` and the installation output.

## Downloads and invocation paths

| Adapter | Downloads or existing Android capability |
| --- | --- |
| Code intelligence | ripgrep; TypeScript/JavaScript LSP; Python LSP; Clang/clangd; ast-grep 0.50.0 source and 278 locked vendored crates |
| File editing | Existing checksum editor, atomic file writing and unified patch preview/apply adapters |
| Version control | Git package and recovery worktree adapter |
| Command execution | Existing argv runner with timeouts, captured output, cancellation and diagnostics |
| Android build | JDK 21; Gradle package and 8.5 wrapper distribution; SDK 35 Java/platform files with Termux aapt/aapt2/aidl/zipalign/apksigner replacements; bundletool 1.18.3 |
| Web/PWA build | Node/npm; offline TypeScript package cache; pnpm 10.32.1 and Yarn 1.22.22 |
| Device diagnostics | ADB package; Shizuku APK and its actual Rish script/DEX; Android system logcat through authorized ADB/Rish |
| APK analysis/editing | JADX; Apktool; standalone Smali/Baksmali 3.0.10 with dependencies; APKEditor 1.4.9 |
| Runtime inspection | GDB; Android ARM64 Frida 17.23.3 injector/server/Gadget and core development kit |
| Network inspection | Built-in HTTP adapter and curl; mitmproxy 12.2.3 source/dependency candidates |
| Security testing | ZAP 2.17.0 cross-platform Java distribution with Automation and Reports add-ons; headless passive scan adapter |
| Verification | Project build/test adapters; pytest cache; Android instrumentation via ADB/Rish; Clang's Android libFuzzer runtime |

Qoder exposes these 12 adapter groups in its capability inventory:
`code_intelligence`, `file_editing`, `version_control`, `command_execution`,
`android_build`, `web_pwa_build`, `device_diagnostics`, `apk_analysis_editing`,
`runtime_inspection`, `network_inspection`, `security_testing`, `verification`.
Definitions, edits, recovery, execution and verification use the existing
structured worker contract; tools receive prerequisites, bounded execution,
captured diagnostics and artifact results.

The Termux cache includes **136 packages** and the dependency closure for its
selected roots. It is a repository snapshot. Dependency versions already
installed on a phone may still cause an APT conflict; removals are disabled.

## What still requires phone verification

- ADB needs pairing/authorization. Shizuku must be started and Termux authorized.
  The installer places Rish files; it cannot grant Shizuku access itself.
- Frida injection needs an observed PID and target attachment permission, often
  root. Server/Gadget clients need matching versions and an explicitly configured
  connection. A Gadget file is downloaded; the installer does not modify another
  app to inject it. Root is never assumed or granted by this bundle.
- mitmproxy is **staged as sources, not installed or verified on Android**. Native
  extension builds, their build dependencies and local HTTPS/proxy testing remain.
  Configure `commands.mitmproxy` only after a working local `mitmdump` is tested.
- ZAP is configured as `bash zap.sh` in Java headless mode. Its real passive scan
  was tested on the build host; Android Java/add-on compatibility still needs a
  local scan. No Docker baseline script is required for this mode.
- Android UI tests require an installed test APK/runner. Invoke `ui/test` with
  `framework: instrumentation`, `runner: PACKAGE/RUNNER`, `access: adb` or `rish`.
  A zero exit code without a nonempty passing test result is rejected.
- Gradle wrappers and project dependencies are project-specific. Only the
  official Gradle 8.5 distribution is seeded in the wrapper cache. Keep each
  project's original wrapper; other distributions, Maven/npm dependencies,
  test APKs, signing keys and project test data are not universal tool packages.
- libFuzzer needs a compatible source harness and corpus; GDB needs a debuggable
  executable and symbols. Android process restrictions still apply.

Each adapter returns exit status, diagnostics and artifacts, and uses the
existing bounded/cancellable runner. Jobs retain checksums, patches and verified
steps. Downloading a package is not sufficient completion evidence for a job.

The local installer sets `execution_platform: android`. Termux also enforces
Android scope for older configurations, and adapter execution stays local even
if an old remote builder configuration exists. Desktop Ghidra, CodeQL,
Semgrep and MobSF are omitted from Android routes. Source/APK security reviews
use inspection and explicit validation; web security testing uses ZAP and HTTP.
Direct adapter calls to the excluded desktop tools are rejected in Android scope.

Downloaded binaries retain upstream licenses. The supplied SDK archives contain
host files; supported build executables are replaced by Android-native Termux
versions. Unsupported host executables are disabled. This does not promise every
Android Gradle plugin or desktop Node dependency will work on Android.
