# Qoder Share build 86: full model catalogs
APK: /sdcard/Download/Qoder-Share-Models-86.apk
Installed version: 0.3.8-full-catalog (86).

## Catalog policy
If a model is advertised, list it. No app-side subscription, account-tier, geographic, or connection-status exclusions.
Every model remains visible and selectable. Provider errors and authentication requirements are displayed as actual service results.

## Changes
- Qoder Cloud combines published Qoder app, IDE and CLI models with observed mobile tiers: 19 options at this audit.
- Cloud tasks use the existing authenticated Qoder CLI in Termux. The original Qoder cloud sessions interface is retained under Sessions.
- OpenCode Zen combines its public API and documented endpoint catalog: 89 entries; all 88 documented entries are present.
- OpenCode Go exposes all 36 runtime/advertised entries; all 32 entries in its published endpoint table are present.
- Provider selector exposes all 226 providers reported by OpenCode, including disconnected providers.
- Model names are searchable; catalog contents are never automatically filtered by subscription or geography.
- Refresh retrieves current catalogs from official sites. Saved catalogs remain available during network failures.
- OpenCode model definitions use the documented protocol: Anthropic Messages, OpenAI Responses or OpenAI-compatible chat.
- Decision models (Jev) are listed; their structured decision endpoint is distinct from coding chat.
- Cloud jobs reserve their execution slot before starting and share source-project locks with Offline jobs.
- Existing source discovery outside the default workspace is preserved.

## Current service state
All catalog entries are selectable. Only the service determines credential validity, billing access, region availability and whether an advertised model is currently served.
No provider subscription, balance or server-side entitlement was changed.

## Sources
https://docs.qoder.com/qoder/model-selector
https://docs.qoder.com/cli/model
https://docs.qoder.com/user-guide/chat/model-tier-selector
https://docs.opencode.ai/docs/zen/
https://docs.opencode.ai/docs/go/
https://opencode.ai/zen/v1/models

## Verification
Six new catalog/job regression tests pass. Full source suite: 166 tests.
Signed APK installation verified by Android package manager as version 86.
