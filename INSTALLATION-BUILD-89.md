# Sessions interface source update 89

Status: source update, not an installed or signed APK.

- Qoder navigation opens its original MainActivity Sessions interface. The old CloudCatalogActivity forwards existing intents to that interface; the custom cloud form is removed.
- OpenCode opens a session list and conversation UI with the OpenCode Go catalogue, Go connection dialog, internal project discovery, saved drafts and retained project context for follow-up messages.
- Model rows show published input/output rates per million tokens. DeepSeek models with documented scheduled rates show red peak / green off-peak markers using UTC. Fixed-price models remain neutral. Missing prices are explicitly unpublished.
- Default buttons are gray; confirmed API actions use green and failed actions orange. Offline session selection uses bold text rather than a success color.
- Connection labels use actual bridge health rather than catalogue availability.

Build on the existing authorized phone using backend/patch_unified_native.py. It requires the existing decoded personal APK, Android platform 36, D8, apktool, zipalign and matching share.keystore/signing.pass under ~/qoder-native-share. Output: /sdcard/Download/Qoder-Share-Sessions-89.apk. Preserve signing files and user sessions.

## Pending work

The original Qoder Sessions UI implementation is in the phone's decoded APK, not this repository. Its model dropdown still needs complete catalogue/pricing integration and a verified credit counter. OpenCode Go's verified live allowance endpoint has not been identified: Usage opens the provider console and does not present an estimated number as an actual balance. No VPN endpoint or credentials are configured; VPN integration is pending. The source does not assert regional access or change subscription permissions.

The source needs Android compilation, signing and device UI verification before installation. Host UI tests use simulated provider responses and do not establish a live Termux/Rish connection or model execution.
