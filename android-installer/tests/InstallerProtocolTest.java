import com.qoder.share.tools.PayloadServer;
import com.qoder.share.tools.SetupScript;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

/** Real loopback protocol checks and generated foreground-shell validation. */
public final class InstallerProtocolTest {
    private static int checks;
    private static void check(boolean value, String label) {
        if (!value) throw new AssertionError(label);
        checks++;
    }
    private static HttpURLConnection request(String url, String body, String range) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(2000); c.setReadTimeout(2000);
        if (range != null) c.setRequestProperty("Range", range);
        if (body != null) {
            c.setRequestMethod("POST"); c.setDoOutput(true);
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            c.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream o = c.getOutputStream()) { o.write(bytes); }
        }
        return c;
    }
    private static byte[] body(HttpURLConnection connection) throws Exception {
        ByteArrayOutputStream copy = new ByteArrayOutputStream();
        try (InputStream in = connection.getInputStream()) {
            byte[] bytes = new byte[64]; int n;
            while ((n = in.read(bytes)) != -1) copy.write(bytes, 0, n);
        }
        return copy.toByteArray();
    }
    public static void main(String[] args) throws Exception {
        File payload = File.createTempFile("qoder-payload-", ".zip");
        byte[] bytes = "checked-payload".getBytes(StandardCharsets.UTF_8);
        byte[] bundle = "offline-bundle".getBytes(StandardCharsets.UTF_8);
        Files.write(payload.toPath(), bytes);
        CountDownLatch progress = new CountDownLatch(1);
        final String[] observed = new String[1];
        PayloadServer.Source bundleSource = new PayloadServer.Source() {
            public long length() { return bundle.length; }
            public InputStream open() { return new ByteArrayInputStream(bundle); }
        };
        PayloadServer server = new PayloadServer(payload, bundleSource, new PayloadServer.Listener() {
            public void progress(String p, String m, int code) {
                if ("preparing".equals(p)) {
                    observed[0] = p + ":" + m + ":" + code;
                    progress.countDown();
                }
            }
        });
        String url = server.baseUrl();
        check(url.matches("http://127\\.0\\.0\\.1:[0-9]+/[0-9a-f]{32}"), "Private IPv4 address and random token");
        HttpURLConnection valid = request(url + "/companion.zip", null, null);
        check(valid.getResponseCode() == 200, "Companion request accepted");
        check(java.util.Arrays.equals(bytes, body(valid)), "Companion exact bytes");
        HttpURLConnection bundleReply = request(url + "/android-tools.zip", null, null);
        check(bundleReply.getResponseCode() == 200 && java.util.Arrays.equals(bundle, body(bundleReply)), "Bundle exact bytes");
        HttpURLConnection ranged = request(url + "/android-tools.zip", null, "bytes=4-");
        check(ranged.getResponseCode() == 206, "Open-ended range accepted for resume");
        check(java.util.Arrays.equals("ine-bundle".getBytes(StandardCharsets.UTF_8), body(ranged)), "Range body exact");
        check(request(url.replaceAll("/[0-9a-f]{32}$", "/bad") + "/companion.zip", null, null).getResponseCode() == 404, "Wrong token rejected");
        check(request(url + "/../companion.zip", null, null).getResponseCode() == 404, "Traversal route rejected");
        check(request(url + "/status", "phase=completed&message=claimed&exit_code=1", null).getResponseCode() == 400, "Failed install cannot claim completion");
        check(request(url + "/status", "phase=unknown&message=anything&exit_code=0", null).getResponseCode() == 400, "Unknown phase rejected");
        check(request(url + "/status", "phase=preparing&message=Checking+bundle&exit_code=-1", null).getResponseCode() == 200, "Preparing callback accepted");
        check(request(url + "/status", "phase=completed&message=Installed+and+verified&exit_code=0", null).getResponseCode() == 200, "Verified completion callback accepted");
        check(progress.await(2, TimeUnit.SECONDS) && "preparing:Checking bundle:-1".equals(observed[0]), "Callback decoded and delivered");
        String digest = new String(new char[64]).replace('\0', 'a');
        String bundleDigest = new String(new char[64]).replace('\0', 'b');
        String full = SetupScript.build(url, true, digest, 127741L, bundleDigest, 1706494607L);
        String minimal = SetupScript.build(url, false, digest, 127741L, bundleDigest, 1706494607L);
        check(full.contains("android-tools.zip") && full.contains("--bundle-sha256"), "Full bundle handoff is generated");
        check(full.contains("$qoder_companion_root/install_offline_tools.py") && full.contains("--companion \"$qoder_companion_root\"") && full.contains("4 GB"), "Offline provision and storage guard are generated");
        check(full.contains("-C -") && full.contains("android-tools.zip"), "Resumable download path is generated");
        check(!minimal.contains("android-tools.zip") && !minimal.contains("--bundle-sha256"), "Companion-only handoff omits bundle transfer");
        check(minimal.contains("--update --no-model") && full.contains("Installed file mismatch"), "Preserve model and verify installed source");
        check(!full.contains("pkg install"), "Installer does not bootstrap from a remote package repository");
        boolean rejected = false;
        try { SetupScript.build(url + "'; touch /tmp/not-authorized", true, digest, 127741L, bundleDigest, 1706494607L); }
        catch (IllegalArgumentException e) { rejected = true; }
        check(rejected, "Shell injection rejected");
        Path script = Files.createTempFile("qoder-setup-", ".sh");
        Files.write(script, full.getBytes(StandardCharsets.UTF_8));
        check(new ProcessBuilder("bash", "-n", script.toString()).inheritIO().start().waitFor() == 0, "Generated setup has valid shell syntax");
        server.close();
        boolean closed = false;
        try { request(url + "/companion.zip", null, null).getResponseCode(); }
        catch (IOException e) { closed = true; }
        check(closed, "Closing service stops transfer socket");
        Files.delete(script); payload.delete();
        System.out.println(checks + " installer checks passed.");
        if (args.length > 0) Files.write(Paths.get(args[0]), minimal.getBytes(StandardCharsets.UTF_8));
        if (args.length > 1) Files.write(Paths.get(args[1]), full.getBytes(StandardCharsets.UTF_8));
    }
}
