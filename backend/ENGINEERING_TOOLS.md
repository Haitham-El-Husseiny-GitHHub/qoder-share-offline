Offline coding tools — build 79

Use the existing native task screen and select a local coding model. The model can now call:

- code_search: literal text search with relative file paths and line numbers.
- edit_patch: replace one exact block, optionally checking the file SHA-256; preserves file mode and returns a unified diff.
- git_diff: Git status and staged or unstaged changes. Untracked file contents need read_file.
- diagnose: run a supported build/test argv, recording exit code, output and parsed file/line diagnostics. Unrecognized error formats remain in raw output.
- import_apk: copy installed base/split APKs through Rish into a new project folder.
- apk_tools: inspect metadata, decode resources and all DEX/smali, decompile Java with JADX, and rebuild an unsigned APK.

Examples:
“Search for calculateTotal, read its implementation, patch the bug, run the tests with diagnose, and show the Git diff.”
“Import com.example.app into inspected-app, inspect the APK and decode it into decoded-app. Find its Android permissions and explain them.”

Operations and command output appear in the existing live activity cards. Stop cancels the worker and running command group; completed edits remain. Save/export retains recorded operations.

Code repair uses the selected model plus observed diagnostic evidence. Tool availability does not guarantee model accuracy. APK rebuilding may require manual fixes; Java decompilation may be incomplete. Rebuilt files are unsigned and are never installed automatically. Shizuku shell access does not grant access to all private app files or remove Android signing constraints.

Verification: 25 automated checks pass on the host and phone, including search, precise patches, ambiguous/stale-path rejection, Git changes, syntax diagnostics, cancellation, sessions and bridge behavior. On-phone APK import, metadata inspection, Java decompilation, complete resource/all-DEX decoding and unsigned rebuilding were exercised on copies.
