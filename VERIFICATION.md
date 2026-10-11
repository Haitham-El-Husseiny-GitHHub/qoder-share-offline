# Verification of companion update 82

Host verification date: 2026-10-10. Baseline: public `offline-79` setup ZIP.
The companion changes are delivered as source; the original signed APK is
unchanged and is not included in this update.

## Automated checks

72 tests passed using `python3 -m unittest discover -s tests -v`.
They cover actual file/search/patch operations, recovery snapshots and dirty
Git worktrees, checksums, cancellation/timeouts, repeated failures, completion
gates, real Python and Node failure/repair/test cycles, APK signing order and
certificate-mismatch blocking, real HTTP request replay, framed LSP messages,
installer/download checks and the remote worker protocol.

The added Android checks reject empty/failed instrumentation runs, require an
authorized ADB target, propagate native Frida permission errors, require a ZAP
report, preserve the Termux environment and reject tampered package caches.
Android device processes are fixtures in these tests; no phone was connected.
Added checks cover Android scope with an old configuration, direct-call rejection
of desktop tools, the 12 exposed adapter groups and rejection of native npm
dependencies in the portable language-server bundle.

The Android package download contains 136 ARM64/all Termux packages. Their
SHA-256 values match the repository index, whose hashes match the signed
InRelease. The InRelease signature was checked against the Termux repository
public key. Additional downloads record their URLs, versions and SHA-256 values;
upstream checksums were checked where published. Integrity checks are not a
claim that every package has been executed on Android.

Model replies are deterministic fixtures in worker-loop tests, not a live
language-model performance measurement. LSP protocol tests use a stdio fixture;
remote transport tests simulate SSH/rsync while separately invoking the real
remote-worker CLI. Signing/device mismatch tests use command fixtures.

## Real-tool smoke checks

- TypeScript 5.9.3 and language server 6.0.2 installed from a fresh offline npm
  cache. Actual LSP requests returned a definition, references and a type-error
  diagnostic for a TypeScript fixture. The lockfile has no native/platform-specific
  dependencies. This replaces TypeScript 7, whose native dependency was incorrectly
  included in bundle 81. The correction is not a phone execution claim.

- Downloaded Smali/Baksmali 3.0.10 standalone JARs assembled a method returning
  42 into DEX, then disassembled it with the instruction intact.
- ZAP 2.17.0 cross-platform Java distribution executed a headless Automation
  Framework passive scan against a local HTTP test server. It exited 0 and
  generated a JSON security report with four provisional findings. The adapter
  uses Bash; the distribution script is not POSIX sh compatible.

- Native ast-grep 0.50.0 searched and rewrote JavaScript through the checksum
  patch editor, changing two structural matches.
- APKEditor 1.4.9 decoded the supplied build 79 APK, including all four DEX files.
- An edited manifest value survived rebuilding with `-t xml -no-cache`.
  Stale signature files/blocks are stripped before alignment. The resulting APK
  was unsigned: no APK signing block or v1 signature files remained, and signature
  verification failed as expected before signing.
- Android build-tools 35 zipalign aligned the rebuilt copy and verified alignment.
- apksigner signed that aligned copy with a temporary host test key, then verified
  the new signature. No test APK, private key or password is delivered.
- apksigner verified the original APK's certificate SHA-256:
  `bb7e569be3a0843c88ed789cc44f6953c2d1161d0c2a73106ffa616f7dad3158`.
- A real dependency-free Node project reproduced a failed test, applied a checked
  repair, built web output and passed the same test. Repeated verification retained
  the current output hashes without rerunning successful checks.

The original native task-screen code was inspected for its dynamic operation
titles/status fields. Live operation responses retain the existing interface
contract. Added workflow, recovery, artifact and verification fields are optional
extensions.

## Limits

This environment has no connection to the phone, Shizuku/Rish, Android device or
local inference model. Phone installation, live app-screen behavior and the
Termux ARM64 setup need on-device verification. Ghidra, Frida, CodeQL, Semgrep,
MobSF, ZAP, mitmproxy, Smali/bundletool provisioning and a real SSH builder were
not live-tested here. Their adapters report actual missing prerequisites and do
not mark unfinished work complete. Full Android source builds need a suitable
SDK, JDK, cached original Gradle Wrapper and project dependencies.

## Reproduce package checks

```sh
python install.py --check
python -m compileall -q backend tests setup_tools.py install.py
python -m unittest discover -s tests -v
```

The package manifest verifies each selected source file. Compare the ZIP with
the supplied SHA-256 file before installing. This verifies integrity of this
delivered update; it is not an assertion that the repository owner published it.
