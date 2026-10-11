package com.qoder.share.tools;

import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.*;
import android.view.*;
import android.widget.*;

/** Small signed UI; all tool work runs in the existing Termux installation. */
public final class MainActivity extends Activity {
    private static final String PERMISSION = "com.termux.permission.RUN_COMMAND";
    private static final int REQUEST_RUN_COMMAND = 82;
    private static final int REQUEST_BUNDLE = 8201;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status;
    private TextView bundleLabel;
    private Button install, copy, selectBundle;
    private CheckBox tools;
    private boolean launching;
    private int attempts;
    private final Runnable refresh = new Runnable() {
        public void run() { render(); handler.postDelayed(this, 1000); }
    };

    private int dp(int n) { return (int) (getResources().getDisplayMetrics().density * n + .5f); }
    private TextView text(String value, int size, int color) {
        TextView t = new TextView(this);
        t.setText(value); t.setTextSize(size); t.setTextColor(color);
        t.setPadding(0, dp(8), 0, dp(8)); return t;
    }
    private Button button(LinearLayout parent, String label, View.OnClickListener listener) {
        Button b = new Button(this); b.setText(label); b.setAllCaps(false);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(56));
        params.topMargin = dp(10); parent.addView(b, params); b.setOnClickListener(listener);
        return b;
    }

    public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(18, 28, 48));
        getWindow().setNavigationBarColor(Color.rgb(18, 28, 48));
        ScrollView scroll = new ScrollView(this);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(24), dp(30), dp(24), dp(24));
        body.setBackgroundColor(Color.rgb(18, 28, 48));
        scroll.addView(body); setContentView(scroll);

        TextView title = text("Qoder Installer 84", 32, Color.WHITE);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD); body.addView(title);
        body.addView(text("Signed companion for Qoder Share build 79", 16, Color.rgb(111, 222, 203)));
        body.addView(text("The APK keeps the UI small. Termux receives the verified companion and, when selected, the full offline ARM64 tools bundle.", 17, Color.rgb(209, 219, 233)));

        tools = new CheckBox(this);
        tools.setText("Install the full offline ARM64 tools bundle (recommended)");
        tools.setTextColor(Color.WHITE); tools.setTextSize(16);
        tools.setChecked(getPreferences(MODE_PRIVATE).getBoolean("install_bundle", true));
        body.addView(tools);
        bundleLabel = text("No Android tools ZIP selected.", 14, Color.rgb(169, 183, 204));
        body.addView(bundleLabel);
        selectBundle = button(body, "Select Android tools ZIP", new View.OnClickListener() {
            public void onClick(View v) { pickBundle(); }
        });
        body.addView(text("Choose Qoder-Android-Tools-83.zip from shared storage. The APK checks its exact size and SHA-256 before Termux extracts it. Untick for the small companion update only.", 14, Color.rgb(169, 183, 204)));

        status = text("Ready to update.", 16, Color.WHITE);
        status.setPadding(dp(16), dp(16), dp(16), dp(16));
        GradientDrawable card = new GradientDrawable();
        card.setColor(Color.rgb(29, 42, 65)); card.setCornerRadius(dp(14));
        status.setBackground(card); body.addView(status);
        install = button(body, "Install update", new View.OnClickListener() {
            public void onClick(View v) { begin(); }
        });
        button(body, "Open Qoder Share", new View.OnClickListener() {
            public void onClick(View v) { openPackage("com.qoder.mobile.share"); }
        });
        button(body, "Open Termux", new View.OnClickListener() {
            public void onClick(View v) { openPackage("com.termux"); }
        });
        copy = button(body, "Copy setup command", new View.OnClickListener() {
            public void onClick(View v) { copyCommand(); }
        });
        button(body, "Termux permission settings", new View.OnClickListener() {
            public void onClick(View v) {
                startActivity(new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.parse("package:" + getPackageName())));
            }
        });
        body.addView(text("Stop active Qoder jobs before updating. Grant this app permission to run commands in Termux when Android asks. SDK license text and all progress appear in Termux.", 14, Color.rgb(169, 183, 204)));

        tools.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            public void onCheckedChanged(CompoundButton b, boolean checked) {
                getPreferences(MODE_PRIVATE).edit().putBoolean("install_bundle", checked).apply();
                if (checked) renderBundleLabel();
            }
        });
        renderBundleLabel();
        if (state != null && state.getBoolean("launching", false) && InstallerService.isRunning()) {
            launching = true; attempts = 0;
            handler.post(new Runnable() { public void run() { handoff(); } });
        }
    }

    private String bundleUri() {
        return InstallerService.state(this).getString("bundle_uri", "");
    }

    private void renderBundleLabel() {
        if (bundleLabel == null) return;
        String value = bundleUri();
        bundleLabel.setText(value.length() == 0 ? "No Android tools ZIP selected." :
                "Selected offline bundle: " + Uri.parse(value).getLastPathSegment());
    }

    private void pickBundle() {
        Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        pick.setType("*/*");
        pick.putExtra(Intent.EXTRA_MIME_TYPES, new String[] {"application/zip", "application/octet-stream"});
        pick.addCategory(Intent.CATEGORY_OPENABLE);
        pick.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        try { startActivityForResult(pick, REQUEST_BUNDLE); }
        catch (RuntimeException e) { status.setText("No file picker is available. Copy the ZIP to shared storage and choose it with a file manager."); }
    }

    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_BUNDLE || resultCode != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        try {
            getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (SecurityException ignored) { /* A transient grant remains valid while this service runs. */ }
        InstallerService.state(this).edit().putString("bundle_uri", uri.toString()).apply();
        renderBundleLabel();
        if (launching) begin();
    }

    private boolean installed(String name) {
        try { getPackageManager().getPackageInfo(name, 0); return true; }
        catch (PackageManager.NameNotFoundException e) { return false; }
    }
    private void openPackage(String name) {
        Intent i = getPackageManager().getLaunchIntentForPackage(name);
        if (i != null) startActivity(i);
        else new AlertDialog.Builder(this).setMessage(name.equals("com.termux") ?
                "Install official Termux and configure the existing build 79 companion first." :
                "Install your original signed Qoder Share build 79 APK first.")
                .setPositiveButton("OK", null).show();
    }

    private void begin() {
        if (launching) return;
        if (tools.isChecked() && bundleUri().length() == 0) {
            pickBundle(); return;
        }
        if (!installed("com.termux") || !installed("com.qoder.mobile.share")) {
            new AlertDialog.Builder(this).setMessage("This installer needs your existing Qoder Share APK and official Termux installation.")
                    .setPositiveButton("OK", null).show(); return;
        }
        boolean arm64 = false;
        for (String abi : Build.SUPPORTED_ABIS) if (abi.equals("arm64-v8a")) arm64 = true;
        if (!arm64) { status.setText("The offline tool bundle requires an ARM64 Android phone."); return; }
        if (checkSelfPermission(PERMISSION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {PERMISSION}, REQUEST_RUN_COMMAND); return;
        }
        InstallerService.state(this).edit().putBoolean("install_bundle", tools.isChecked()).apply();
        launching = true; attempts = 0; install.setEnabled(false);
        try {
            startForegroundService(new Intent(this, InstallerService.class));
            handler.postDelayed(new Runnable() { public void run() { handoff(); } }, 100);
        } catch (RuntimeException e) {
            launching = false; status.setText("Cannot prepare setup: " + e.getMessage());
        }
    }

    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == REQUEST_RUN_COMMAND && results.length > 0 &&
                results[0] == PackageManager.PERMISSION_GRANTED) begin();
        else if (requestCode == REQUEST_RUN_COMMAND) status.setText("Grant the Termux run-command permission to start setup.");
    }

    private String scriptFor(SharedPreferences saved) {
        return SetupScript.build(saved.getString("url", ""),
                saved.getBoolean("install_bundle", false),
                BuildConfig.COMPANION_SHA256, BuildConfig.COMPANION_BYTES,
                BuildConfig.BUNDLE_SHA256, BuildConfig.BUNDLE_BYTES);
    }

    private void handoff() {
        SharedPreferences saved = InstallerService.state(this);
        if (!"ready".equals(saved.getString("phase", ""))) {
            if (++attempts < 120 && InstallerService.isRunning()) {
                handler.postDelayed(new Runnable() { public void run() { handoff(); } }, 100); return;
            }
            launching = false; status.setText(saved.getString("message", "Cannot prepare installer.")); return;
        }
        String script;
        try { script = scriptFor(saved); }
        catch (IllegalArgumentException e) { launching = false; status.setText(e.getMessage()); return; }
        Intent command = new Intent("com.termux.RUN_COMMAND");
        command.setClassName("com.termux", "com.termux.app.RunCommandService");
        command.putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/bash");
        command.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", new String[] {"-c", script});
        command.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home");
        command.putExtra("com.termux.RUN_COMMAND_BACKGROUND", false);
        command.putExtra("com.termux.RUN_COMMAND_SESSION_ACTION", "0");
        command.putExtra("com.termux.RUN_COMMAND_COMMAND_LABEL", "Qoder Installer 84");
        try {
            startService(command);
            saved.edit().putString("phase", "handoff").putString("message", "Setup sent to Termux. Follow progress there; return here for its result.").apply();
        } catch (RuntimeException e) {
            copyCommand();
            saved.edit().putString("phase", "waiting").putString("message", "Termux could not start setup. Enable allow-external-apps in Termux or paste the copied command.").apply();
        }
        launching = false;
    }

    private void copyCommand() {
        SharedPreferences saved = InstallerService.state(this);
        String url = saved.getString("url", "");
        if (!InstallerService.isRunning() || url.isEmpty()) {
            status.setText("Tap Install update first to prepare the setup command."); return;
        }
        String script;
        try { script = scriptFor(saved); }
        catch (IllegalArgumentException e) { status.setText(e.getMessage()); return; }
        String quoted = "bash -c '" + script.replace("'", "'\"'\"'") + "'";
        ((ClipboardManager) getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(
                ClipData.newPlainText("Qoder tools setup", quoted));
        Toast.makeText(this, "Setup command copied. Paste it in Termux.", Toast.LENGTH_LONG).show();
    }

    private void render() {
        SharedPreferences saved = InstallerService.state(this);
        String phase = saved.getString("phase", "");
        boolean busy = InstallerService.isRunning() && !phase.equals("completed") && !phase.equals("failed");
        install.setEnabled(!busy && !launching); tools.setEnabled(!busy && !launching);
        selectBundle.setEnabled(!busy && !launching); copy.setEnabled(busy);
        if (busy || phase.equals("completed") || phase.equals("failed") || phase.equals("unknown"))
            status.setText(saved.getString("message", "Ready to update."));
        else if (!phase.isEmpty()) status.setText("Setup status is unavailable. Check Termux before retrying.");
    }

    protected void onSaveInstanceState(Bundle out) {
        out.putBoolean("launching", launching); super.onSaveInstanceState(out);
    }
    protected void onResume() { super.onResume(); handler.post(refresh); }
    protected void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
    protected void onDestroy() { handler.removeCallbacksAndMessages(null); super.onDestroy(); }
}
