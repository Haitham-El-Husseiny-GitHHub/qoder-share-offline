# Direct attachments

Qoder Share APK build 84 adds a paperclip to the native task composer. Select
one or more files through Android's document picker. Imported files appear in
a removable list before sending. Up to eight files can accompany a message;
each file may be at most 256 MiB. Text, Markdown, images and APKs are accepted.

The matching companion backend exposes `POST /api/attachments`. Send raw file
bytes with a Content-Length and URL-encoded `workspace` and `name` parameters.
The existing loopback Host/Origin checks apply. Imports must target an existing
folder inside `~/coding-workspace` or `~/projects`, excluding the projects parent.
Imports use unique `attachments/<id>/<filename>` paths, stream without loading
the whole file into memory, report SHA-256, and never overwrite source files.
Incomplete transfers are removed. Private configuration and signing keys are
rejected. Existing symlink attachment directories are rejected.

Sending adds workspace-relative attachment paths to the task. The worker can
read text or inspect APKs using the tools selected by the router. Uploading an
APK does not install or execute it. Images remain files; visual understanding
requires a working vision or OCR adapter. Selecting an attachment does not
alter the worker policy or authorize additional tools.

Draft attachment lists survive reopening the app. Removing a list entry or
sending clears its reference, leaving the imported workspace file available.
Delete unwanted imports from the project's attachments folder when finished.

Install the build 84 APK and matching companion together for this feature.
The companion retains build 83's tools baseline and remains compatible with
APK build 79. Native sources are in `backend/native`; the personal build script
is `backend/patch_unified_native.py`. Rebuilding needs the existing decoded
APK, Android SDK, APKTool and original signing key on the phone. Keys and
runtime files are excluded from the repository and companion archive.
