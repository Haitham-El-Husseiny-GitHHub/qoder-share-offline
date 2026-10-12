# Sessions build 90

Build 90 extends the installed Sessions update with the original Qoder chat model picker and a verified account counter. Model IDs and provider permissions are preserved. The picker includes the current published catalogue without local plan/location filtering, retains unknown-price labels where no rate is published, and shows scheduled peak/off-peak labels. Existing server model prices take precedence; catalogue-only additions show estimated CLI reference multipliers.

The original Qoder Sessions interface now has a compact Termux/Rish/shell status and credit counter. Tap the counter for separate plan/add-on quotas and the refresh timestamp. Its read-only adapter initializes the installed Qoder client's credential reader without issuing a coding request; credentials remain on the phone. Failed refreshes retain the last verified number with a stale label.

OpenCode Go has a compact allowance control. It opens key entry when disconnected and the account console when connected. No numeric Go allowance is fabricated: this adapter has no verified Go balance endpoint. Independent provider choices stay hidden.

The APK uses the existing signing key and updates the installed app without clearing its sessions. Output: /sdcard/Download/Qoder-Share-Sessions-90.apk.

External dependencies: a Go API key is still required for live Go execution. No VPN endpoint, tunnel credentials or configured VPN app is present on the phone; automatic VPN connection cannot be enabled until a working tunnel is supplied. Network location does not replenish Qoder credits.
