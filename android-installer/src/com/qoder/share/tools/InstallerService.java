package com.qoder.share.tools;

import android.app.*;
import android.content.*;
import android.net.Uri;
import android.os.*;
import java.io.*;
import java.security.MessageDigest;

/** Foreground bridge that exposes only the pinned APK payloads over loopback. */
public final class InstallerService extends Service {
    static final String CHANNEL = "qoder-tools-transfer";
    private static volatile boolean running;
    private PayloadServer server;
    private final Handler handler = new Handler(Looper.getMainLooper());

    static boolean isRunning() { return running; }
    static android.content.SharedPreferences state(Context context) {
        return context.getSharedPreferences("update-status", Context.MODE_PRIVATE);
    }

    private void update(String phase, String message, int code) {
        state(this).edit().putString("phase", phase).putString("message", message)
                .putInt("exit_code", code).putLong("updated", System.currentTimeMillis()).apply();
    }

    private static final class UriSource implements PayloadServer.Source {
        private final ContentResolver resolver;
        private final Uri uri;
        private final long size;

        UriSource(ContentResolver resolver, Uri uri) throws IOException {
            this.resolver = resolver;
            this.uri = uri;
            ParcelFileDescriptor descriptor = resolver.openFileDescriptor(uri, "r");
            if (descriptor == null) throw new IOException("The selected bundle cannot be opened.");
            try {
                size = descriptor.getStatSize();
            } finally {
                descriptor.close();
            }
            if (size < 1) throw new IOException("The selected bundle has no readable size.");
        }

        public long length() { return size; }

        public InputStream open() throws IOException {
            ParcelFileDescriptor descriptor = resolver.openFileDescriptor(uri, "r");
            if (descriptor == null) throw new IOException("The selected bundle cannot be reopened.");
            return new ParcelFileDescriptor.AutoCloseInputStream(descriptor);
        }
    }

    public void onCreate() {
        super.onCreate();
        running = true;
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Qoder tools setup", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        startForeground(82, new Notification.Builder(this, CHANNEL)
                .setContentTitle("Qoder Installer 84")
                .setContentText("Open Termux for offline installation progress.")
                .setSmallIcon(android.R.drawable.stat_sys_download)
                .setContentIntent(open).setOngoing(true).build());
    }

    public int onStartCommand(Intent intent, int flags, int startId) {
        if (server != null) return START_NOT_STICKY;
        update("preparing", "Checking the embedded companion and selected bundle.", -1);
        try {
            final File payload = new File(getFilesDir(), "companion-83.zip");
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream in = getAssets().open("companion.zip");
                 OutputStream out = new FileOutputStream(payload)) {
                byte[] bytes = new byte[16384];
                int n;
                while ((n = in.read(bytes)) != -1) {
                    digest.update(bytes, 0, n);
                    out.write(bytes, 0, n);
                }
            }
            StringBuilder actual = new StringBuilder();
            for (byte b : digest.digest()) actual.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
            if (!actual.toString().equals(BuildConfig.COMPANION_SHA256))
                throw new IOException("Embedded companion checksum mismatch.");

            android.content.SharedPreferences saved = state(this);
            PayloadServer.Source bundle = null;
            if (saved.getBoolean("install_bundle", true)) {
                String value = saved.getString("bundle_uri", "");
                if (value == null || value.length() == 0)
                    throw new IOException("Select the offline Android tools ZIP before starting.");
                bundle = new UriSource(getContentResolver(), Uri.parse(value));
                if (bundle.length() != BuildConfig.BUNDLE_BYTES)
                    throw new IOException("Selected bundle size does not match the pinned release.");
            }
            final PayloadServer.Source selectedBundle = bundle;
            server = new PayloadServer(payload, selectedBundle, new PayloadServer.Listener() {
                public void progress(String phase, String message, int code) {
                    update(phase, message, code);
                    if (phase.equals("completed") || phase.equals("failed")) stopSelf();
                }
            });
            saved.edit().putString("url", server.baseUrl()).apply();
            update("ready", selectedBundle == null ? "Companion ready. Waiting for Termux." :
                    "Companion and full bundle ready. Waiting for Termux.", -1);
            handler.postDelayed(new Runnable() {
                public void run() {
                    if (running) {
                        update("unknown", "Setup status is unavailable. Check the Termux session before retrying.", -1);
                        stopSelf();
                    }
                }
            }, 6 * 60 * 60 * 1000L);
        } catch (Exception e) {
            update("failed", e.getMessage() == null ? "Cannot prepare offline update." : e.getMessage(), 1);
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    public IBinder onBind(Intent intent) { return null; }

    public void onDestroy() {
        running = false;
        handler.removeCallbacksAndMessages(null);
        try { if (server != null) server.close(); } catch (IOException ignored) {}
        stopForeground(true);
        super.onDestroy();
    }
}
