# Tool integration and configuration

Each adapter declares capabilities, operations, prerequisites, timeout and
verification. Structured results carry execution location, exit status,
diagnostics and artifacts with SHA-256 for files. Commands use argv arrays,
captured output and cancellable process groups. APK signing and phone-device
operations stay local. Configured heavy adapters can use SSH.

## Private configuration

The installer creates `~/qoder-selfhost/tools.json` from
`backend/tools.example.json` and preserves existing settings on updates.
Merge new settings into that file, retaining discovered paths. Command overrides
are argv arrays:

```json
{
  "schema": 1,
  "commands": {
    "ghidra": ["/opt/ghidra/support/analyzeHeadless"],
    "semgrep": ["/path/to/venv/bin/semgrep"]
  },
  "language_servers": {
    "python": ["/path/to/pylsp"],
    "typescript": ["/path/to/typescript-language-server", "--stdio"],
    "cpp": ["clangd"],
    "java": ["/path/to/java-language-server-wrapper"]
  },
  "remote": {"enabled": false},
  "verification_commands": [],
  "worktrees": true
}
```

Language-server wrappers must speak stdio LSP. Definitions, references and
diagnostics are supported; edits use the checked editor. Missing diagnostic
responses remain unverified. Java/Kotlin needs a compatible separately installed
server. The native installer supplies npm; pnpm/yarn/bun projects need their
matching package manager and cached dependencies. Gradle uses the original
project wrapper and cached distribution/dependencies.

## Signing and device operations

Keep signing credentials outside the project; add these private settings:

```json
"signing": {
  "keystore": "/data/data/com.termux/files/home/.qoder-signing/app.jks",
  "alias": "app",
  "password_file": "/data/data/com.termux/files/home/.qoder-signing/password"
}
```

The password file must be mode 600. Signing reads the password from its file,
checks alignment first, creates a new APK and verifies its signature/certificate.
No original-author signing key is supplied. Before replacement, the adapter
checks package identity, preserves installed APKs and compares certificates.
A mismatch stops replacement without uninstalling or clearing app data.
Signing-key rotation lineages are not supported by this conservative comparison.

Select one authorized ADB device, or configure `"adb_serial": "your-serial"`.
Rish requires running Shizuku and existing Termux authorization. Every selected
split APK must have a valid matching signature. Package/device compatibility
still determines whether split merging and installation work.

## External adapters

| Adapter | Configuration and implemented scope |
| --- | --- |
| Semgrep | Working command and local rules path; returns JSON findings |
| CodeQL | Working command, cached language packs/queries, explicit build argv when needed; database/SARIF |
| MobSF | `"mobsf": {"url": "http://127.0.0.1:8000", "key_file": "/private/mobsf-key"}`; static APK JSON assessment |
| ZAP | Working `zap-baseline.py` command with its configured ZAP host/container; passive baseline scan |
| mitmproxy | Working `mitmdump`; bounded loopback capture and saved-flow replay; HTTPS requires proxy/trust setup |
| Frida | Compatible authorized server/gadget and explicit script; optional `"frida": {"host": "127.0.0.1:27042"}`; otherwise USB |
| Ghidra | Compatible headless installation; exported decompiled functions in JSONL; validate with runtime observation |
| libFuzzer/GDB | Existing harness, compatible sanitizer runtime, corpus/executable and symbols |
| UI automation | Existing Maestro tests or installed project Playwright runner plus available device/browser |

MobSF's API key must be mode 600 and outside the project. Dynamic MobSF analysis
needs its configured device environment and separate checks; this adapter does
not automate that environment. ZAP baseline is passive, not a full active test.
Scanner findings remain provisional until validated. Frida/debugger verification
requires an expected observation. A tool's presence alone never proves access.

For task-specific verification, add declared argv arrays:

```json
"verification_commands": [
  {"kind": "tests", "argv": ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]},
  {"kind": "security_validation", "argv": ["python3", "tests/test_reported_issue.py"]}
]
```

These replace automatic project checks, so include all checks required by the
task. Kinds include `tests`, `build`, `typecheck`, `functional`,
`security_validation` and `runtime_observation`.

## Optional remote builder

Install Python 3, rsync and the desired compatible tools on your machine.
Copy the package's `backend/` directory there; put any private command overrides
in its `tools.json`. Cache dependencies/rules/query packs on that host.
Establish key-based SSH access and its trusted known-host entry from Termux.
Then adjust these phone settings:

```json
"remote": {
  "enabled": true,
  "host": "builder",
  "worker": ["env", "QODER_REMOTE_ROOT=/srv/qoder-jobs", "python3", "/srv/qoder/backend/remote_worker.py"],
  "tools": ["gradle", "cmake", "node", "ghidra", "semgrep", "codeql", "mobsf", "zap"],
  "prefer_heavy": true,
  "prefer": ["node"]
}
```

The remote root must be writable by that SSH user. Only listed adapters may run
remotely. Transport uses strict host-key checking and no password prompts. It
probes capabilities, transfers source, executes a bounded job, retrieves
registered artifacts and checks file hashes. Stop also sends a cancel marker.
Common credentials, runtime/model folders and node_modules are excluded from
transfer. Configuring a host authorizes sending project source there; other
project files can still contain sensitive content. Remote workspaces persist
for inspection and need your normal retention cleanup.

Inference and patches remain on the phone. Remote execution defaults off and
requires connectivity. The remote worker itself performs no inference.

## Workflow and recovery

Source detection supports Node, Gradle, Python and CMake. The router selects tools
and checks from the requested outcome. Identical failed operations are limited
per source revision; jobs have 32 model turns and an overall time bound.
Completion requires observed evidence for the selected workflow.

Journals live under `~/qoder-selfhost/jobs/`. Git projects use adjacent
`.qoder-worktrees/`; other projects use `.qoder-workspaces/`. Original dirty
tracked and untracked source is retained. Cached dependency folders may be
linked. Edit backups are kept with the journal; `.qoder-artifacts/` holds patches
and reports. Known input and artifact hashes must match before resume; an
unfinished operation is not presumed successful.

Repeating the same objective, profile and target in the same app session resumes
an interrupted/stopped job. CLI recovery uses its reported job ID:

```sh
~/bin/qoder-local-code --resume JOB_ID
```

For independent inventory/routing/tool invocation:

```sh
python ~/qoder-selfhost/tools_cli.py
python ~/qoder-selfhost/tools_cli.py --workspace ~/projects/app --objective 'Refactor parser' --profile BUILD
python ~/qoder-selfhost/tools_cli.py --workspace ~/projects/app --invoke language_server definition --inputs '{"path":"src/parser.ts","line":20,"column":8}'
python ~/qoder-selfhost/tools_cli.py --workspace ~/projects/app --invoke node test --inputs '{}' --timeout 120
```

Direct invocation returns structured results; use the app or coding CLI for
the complete router/recovery loop.
