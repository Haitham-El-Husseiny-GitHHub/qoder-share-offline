# Qoder Share Offline: architecture and execution contract

This specification corrects the original design. Sections marked implemented
refer to the repository, not a guarantee that every optional adapter or APK
works on every Android release. Acceptance requires observed device evidence.

## Defects found and disposition

| Defect | Correction / implementation boundary |
| --- | --- |
| Installed app intent lost when unrelated project tests exist | Explicit installed-app intent takes the device route; explicit source filenames retain the source route. Implemented with regression tests. |
| Typo treated as executable | Device workflow exposes package/logcat tools and instructs package discovery before action. Bounded local source/package discovery and prompt guidance implemented; deterministic fuzzy label-to-package resolution remains future work. |
| Green reproduction card without reproduction | Baseline card reports failure unless a non-prerequisite failing check was observed. Implemented. A failing test alone may still be unrelated to the requested bug; inspect its diagnostics. |
| Rejected command repeated indefinitely | Two identical failures at the same source revision stop the job as blocked. Implemented. Semantic detection of differently phrased repetitions remains future work. |
| Old successful check reused after later failure | Only the latest identical command at the current revision can be reused. Implemented. |
| Timeout/missing executable counted as reproduction | Exit codes 124/126/127 and explicit timeout/missing-prerequisite results excluded. Implemented. |
| Signature inferred from installation alone | Certificate verification evidence required for signature completion. Implemented. |
| Every source edit forced UI automation | UI selected only when requested by the source objective; affected project tests remain required. Implemented. |
| Huge source snapshot for app diagnosis | Source recovery created for mutation or required project checks, not ordinary device diagnosis. Implemented. |
| Check logs lost in persisted state | Bounded output, error, timeout, diagnostics and prerequisites retained per check. Implemented. |
| Executable presence implies availability | Inventory exposes needs_user/unavailable plus verified connection operations. Other operation probes remain explicit; presence never proves compatibility. |
| Offline claim based only on prompts | Managed command fetch guards, offline package-manager environment and loopback-only HTTP with redirect checks implemented. Arbitrary scripts/plugins are not isolated by an OS network sandbox. |
| Version numbers hardcoded into architecture | Architecture is version independent; release manifest supplies exact component identity, size and checksum. Original editor remains build 79; companion is 83; installer 84 is source only without the original installer signing key. |
| Repair workflow reproduces after patching | Observe relevant failure before editing, then run the same check after editing. |
| Every workflow requires every listed tool | Required outcomes govern completion; choose alternatives and smallest toolset, distinguish optional tools from blockers. |
| APK decompilation assumed compilable Java | JADX output supports analysis; smali/resources or original source are the actual rebuild inputs. |
| Native/security desktop tools assumed local Android | Ghidra, Semgrep, CodeQL, MobSF are excluded from the current Android scope. Report unsupported; no automatic substitute scan claims. |
| Logcat or successful launch proves functionality | Crash diagnosis and functional acceptance are separate. Current functional gate supports explicit instrumentation; manual observed acceptance needs a dedicated evidence interface. |
| Resume can blindly repeat external action | Persist interrupted operation and inspect state before retry. Installed package operations need idempotency/reconciliation; process termination cannot roll back device actions. |

## Three layers

1. Android UI: original signed com.qoder.mobile.share build 79. Small UI client
   showing task/project, session/model, progress, Stop, saved jobs and results.
   It does not contain the Termux toolchain. Existing APK identity is retained.
2. Installer/bridge: com.qoder.share.tools. RUN_COMMAND launches a bounded
   Termux setup command; authenticated loopback transport supplies verified
   archives. Preserve package identity and original certificate for APK updates.
   Android permission grant and Shizuku authorization are distinct prerequisites.
3. Termux: official ARM64 com.termux, backend ~/qoder-selfhost, projects and
   worktrees in Termux private storage. Local model inference uses loopback.
   Privileged Android operations use authorized ADB or Rish. Shell is not root;
   Shizuku does not grant unrestricted private app data or Frida attach access.

The current full tools cache is Qoder-Android-Tools-83.zip. Its embedded
companion predates backend hotfixes: the separate current small companion is
mandatory. See INSTALLATION-BUILD-83.md. Never select a script solely because
it happens to exist inside a cache. Source-backed installer 84 must embed the
matching new companion and be signed with the original installer certificate
before it can update an installed APK.

## Adapter interface

All adapters should implement this contract. Existing engineering adapters
use tool_adapters.invoke; built-in file/Git/command tools are still separate
Workspace methods and are not yet one fully uniform schema registry.

```json
{
  "tool": "rish",
  "group": "device_diagnostics",
  "operation": "package",
  "capabilities": ["installed_package_metadata"],
  "prerequisites": ["Shizuku running", "Termux authorized"],
  "input_schema": {"type":"object", "required":["package"],
    "properties":{"package":{"type":"string"}}, "additionalProperties":false},
  "timeout_seconds": 30,
  "cancellation": "terminate process group; inspect external state before retry",
  "verification_operation": "package",
  "availability_state": "needs_user",
  "verified_operations": [],
  "probe": {"checked_at":null, "target":null, "version":null}
}
```

```json
{
  "tool":"rish", "operation":"package", "location":"local",
  "success":true, "exit_code":0, "timeout":false,
  "output":"bounded observed output", "diagnostics":[], "artifacts":[],
  "missing_prerequisite":false,
  "evidence":{"target":"com.example.app", "operation":"package", "checked_at":0}
}
```

Use verified only for an observed operation, version, target and access context.
needs_user means installed/configured but permission, setup or compatibility
still needs validation. failed_probe means an actual probe failed. unavailable
means no compatible executable/service. A source directory is not installation.
A probe does not establish future success after permissions or versions change.
The current inventory reports presence separately from operation evidence;
full timestamped per-operation probe caching is a remaining implementation gap.

Groups: code intelligence (ripgrep, LSP, ast-grep); file editing (reads, atomic
writes, checksum patches); version control (Git diff, recovery/worktrees);
command execution (argv, captured output, process-group cancellation); Android
build (JDK, cached Gradle Wrapper/SDK, zipalign, apksigner, bundletool); web/PWA
(Node and lockfile-selected manager); device diagnostics (ADB/Rish/logcat);
APK analysis (JADX/Apktool/APKEditor/smali); runtime (compatible Frida/debugger);
network (HTTP/compatible proxy); security (supported local scanners only);
verification (affected tests, builds, type checks, explicit instrumentation,
compatible fuzz harness). Tools in a group need not all be installed.

Current tool_adapter input schema is a shared union, not a complete strict
per-operation schema. Unsupported/malformed inputs fail before useful work;
per-operation required fields should move into the registry in a future change.

## Durable job state

Current journal schema 1 includes id, target, workspace, objective, profile,
route, plan, capabilities, recovery, steps, patches, artifacts, checks, revision,
file_hashes, status, messages, pending_step and interrupted_operation. Extend
compatibly rather than discarding existing sessions. A normalized contract is:

```json
{
  "schema":1, "id":"32 hex characters", "objective":"requested outcome",
  "target":"original project or explicit package",
  "workspace":"isolated working path", "revision":0,
  "plan":{"workflow":"source_fix", "adapters":[], "checks":[],
    "required":["reproduction","change","tests"], "prerequisites":{}},
  "recovery":{"mode":"git_worktree", "target":"original", "snapshot":"commit"},
  "steps":[], "patches":[], "artifacts":[], "checks":[], "file_hashes":{},
  "pending_step":null, "interrupted_operation":null,
  "status":"running", "messages":[], "verification":{},
  "resumed_from":null, "started_at":0, "updated_at":0
}
```

Statuses: running, completed, needs_verification, blocked, stopped, failed,
interrupted. Completion requires current evidence. Each check records command,
revision, exit code, bounded output/error/diagnostics, timestamp, test-input
hashes where applicable, timeout and missing prerequisite. Artifacts record
relative path, existence, SHA-256 and size. Preserve exported diff and originals.
Current source edits are saved in an isolated workspace: the original project
is not automatically updated. The UI/result must show the verified workspace
and patch; an explicit reviewed apply/export operation is still needed.

Stop terminates running subprocesses; completed changes remain saved. Resume
checks recorded file/artifact hashes and target/task/profile identity. A broken
connection does not imply a worker stopped. Never launch a duplicate worker
without reconciling its PID and pending step. Resume does not undo Android actions.

## Internal routing and execution

Inspect target intent and project markers before selecting tools. Explicit APK
modification, installed-app diagnostics and explicit source-file edits must not
be overridden by unrelated files. Source is preferred only when it belongs to
the requested target. Bounded discovery searches named local project subdirectories; confirmed matching
source can select source repair. Explicit target identity/disambiguation remains
limited. Unrelated source must not override an installed-app task.

For an app label with a typo, discover installed package candidates, inspect
metadata, and resolve one package; request clarification if ambiguous. Never
execute the app label as a shell command. A prompt instruction is not a
substitute for a deterministic resolver; that resolver is not implemented yet.

Choose the smallest sufficient tools and outcomes, then:

1. Discover architecture/tool/device access and required caches. Probe actual
   optional operation compatibility. Unknown state stays unknown.
2. Create recovery before source mutation. Do not copy unrelated projects for
   device diagnosis. Keep originals before APK modification.
3. For repairs, run a relevant baseline. Missing dependencies/timeouts are
   blockers, not proof of the reported bug. Inspect traceback/assertion relevance.
4. Run one adapter operation, inspect its structured result, persist it, update UI.
5. Revise strategy from evidence; stop after two identical failures or a hard
   prerequisite blocker. No repeated unsupported executable guessing.
6. After an edit, automatically run planned checks; stop immediately when the
   requested outcome is verified at the current revision. Do not equate a
   command's zero exit code with the product goal.
7. Export artifacts/diff and report missing evidence accurately.

Source discovery contacts GitHub/Cloudflare only when explicitly online; offline
jobs search local projects and installed packages. Remote execution is disabled
in the current Android-only scope. An explicitly
configured remote worker would be a separate online mode and requires transfer,
privacy, architecture and artifact-integrity contracts; this is not implemented
as a route for offline phone jobs.

## Offline boundary

Offline is default for managed adapter jobs. No apt/pkg/sdkmanager, Git remote
fetches, curl/wget bootstrap, online pip, or package-manager installs without
explicit offline flags. Gradle/Cargo require --offline. Package-manager
subprocess environment disables supported network resolution. All dependencies,
Gradle distributions, SDK components, query packs, rules and model files must
already be cached. Hash verification proves integrity, not Android compatibility.

HTTP in offline mode uses loopback only and rejects redirects off loopback.
An external API investigation is necessarily an online job or a replay against a
local fixture. mitmproxy capture of external traffic is also online. Setting
network mode requires a future per-job UI/contract; current tools.json offline
false enables explicitly online adapter access.

These guards are not an OS sandbox: arbitrary Python/Node/Gradle/CMake scripts,
plugins, native programs or configured wrappers can open sockets independently.
To guarantee zero egress, enforce Android per-UID network denial or an equivalent
verified sandbox and test it. That enforcement is not supplied by this change.
Do not advertise a stronger guarantee.

## Installation and update protocol

1. Trusted release metadata pins package, build, certificate, exact bytes and
   SHA-256 of every downloaded artifact. Checksums from the same untrusted
   download do not by themselves establish publisher authenticity.
2. Validate outer archives before extraction; reject traversal, symlinks and
   oversized payloads. Verify inner manifest before execution. Select the
   explicit current companion even when an old cache remains present.
3. Refuse companion downgrade. Same-build hotfixes require a different trusted
   content receipt; build number alone cannot distinguish them. Future releases
   should have a monotonic component revision and immutable asset manifest.
4. Check active jobs and update lock before stopping backend or removing
   readiness. Preserve models, sessions/jobs, projects, inference credential,
   user configuration, and signing keys. Report managed source replacements.
5. Provision local cache, compile ARM64 native extensions as needed, probe real
   tools. Write offline-ready only after core probes pass. Optional readiness is
   separate from core readiness; project dependencies need their own verification.
6. Restart service, probe health/inference/bridge and compare preserved state.
   Retain diagnostics. Refuse signing-key/package mismatch for APK updates.

Current updates copy managed files into the backend in place; all-or-nothing
staging/swap with crash rollback is not yet implemented. A failed copy/probe
must remain unready and report recovery instructions. Automatic rollback and
reporting a complete overwritten-managed-file diff are remaining work. No new
signed installer APK can be produced without the original installer private key.

## Verification strategy and UI

Distinguish operation success, reproduction, build, test, signature,
installation and functional acceptance. For source repair require an observed
failure before a source revision and the same check passing afterward, with
original test inputs preserved. Reject zero tests. A relevant assertion/log is
needed; success of unrelated tests proves nothing about the user's objective.
A test-file edit may be legitimate but requires review; it cannot fake the
before/after proof by weakening the existing failing test.

APK: actual rebuilt output, alignment, certificate verification, signature
compatibility with installed base/splits, installation, and explicit functional
check. Do not clear data or uninstall to evade signing conflicts. Frida/root/UI
access need distinct probes. Read-only static native findings must be reported
as static; runtime confirmation is required only when requested/available, and
missing runtime support must not be silently treated as confirmed findings.

Security: validate scanner report, scope and rule coverage; zero findings means
no findings under that scan, not absence of vulnerabilities. Retest a repaired
finding. Existing Android scope cannot claim desktop scanner execution.

UI should show operation name and command/tool, observed duration/output,
prerequisites and permissions, diagnostics, artifact links/hashes, missing and
passed evidence, source recovery path, and resumable status. Use step progress,
not invented percentages. A green operation card means that operation passed,
not that the whole requested outcome passed. New APK-side rendering features
are outside this backend hotfix and require original-key signed UI updates.

## Representative end-to-end workflows

| Task | Minimal route and acceptance |
| --- | --- |
| format_egp in ledger.py: 105 -> 1.05; 100 -> 1.00 | Select exact project -> recovery -> run supplied unittest and observe failure -> read ledger.py -> patch only remainder to :02d -> same unittest passes -> export diff and workspace. No LSP/UI needed. |
| Create/extend app | Inspect actual root/lockfile -> recovery -> relevant code search/LSP as useful -> atomic patch -> cached Gradle/Node build -> affected tests/type checks -> functional checks when requested -> artifacts. |
| PrettyUp app closes on launch | Resolve installed package despite label typo -> Rish/ADB metadata + bounded logs -> reproduce launch once if needed -> identify exception -> report/apply data-preserving fix -> explicitly repeat original action with functional evidence. No source patch until an actual source/APK target is chosen. |
| Modify installed APK | Preserve base/split APKs -> package/certificate/ABI inspection -> original source preferred or JADX analysis + Apktool/smali/resources -> rebuild -> 16 KB-compatible zipalign -> sign with compatible key -> verify certificate -> install if compatible -> functional check. |
| Native analysis | Local readelf/strings/compatible debugger or Frida -> static report -> runtime observation when supported. Ghidra requires a separately supported configured environment, not the offline Android route. |
| API investigation | Local HTTP fixture or saved flow -> expectation-based failing replay -> repair source/config -> same replay passes. External endpoint requires explicitly online access. |
| Security review | Probe supported scanner + local rules -> save scoped findings -> source/APK repair -> retest finding. Unsupported CodeQL/MobSF/Semgrep do not become successful scans through fallback inspection. |
| Multi-file refactor | Recovery -> references/AST search where available -> checksum patches -> diff -> cached build/type checks -> affected tests -> exported patch. |

## Acceptance and remaining gaps

Automated regressions cover installed-app/source routing, truthful baseline,
repeat-failure stop, stale-check retry, missing-tool reproduction exclusion,
signature evidence, journal preservation, and managed offline fetch/HTTP guards.
Existing tests also cover actual repair/recovery, empty tests, changed-test
proof rejection, APK signing compatibility, installer/cache checks and protocols.
Live phone readiness and source synchronization must be checked after idle update.

Remaining gaps are stated above, particularly deterministic typo/package lookup,
full per-operation schemas/probes, source apply/export UI, manual functional
evidence, true zero-egress enforcement, atomic update rollback and original-key
signed installer/UI binaries. Do not present these as completed implementation.
