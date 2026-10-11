package com.qoder.share.tools;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

/** One private loopback transfer and bounded authenticated status callbacks. */
public final class PayloadServer implements Closeable {
    public interface Listener { void progress(String phase, String message, int exitCode); }

    /** A repeatable, seekable-by-reopen source. The server never keeps it open between requests. */
    public interface Source {
        long length();
        InputStream open() throws IOException;
    }

    private final Source companion;
    private final Source bundle;
    private final Listener listener;
    private final ServerSocket socket;
    private final String token = UUID.randomUUID().toString().replace("-", "");
    private final ExecutorService clients = Executors.newFixedThreadPool(2);
    private volatile boolean closed;

    public PayloadServer(File payload, Listener listener) throws IOException {
        this(fileSource(payload), null, listener);
    }

    public PayloadServer(File payload, Source bundle, Listener listener) throws IOException {
        this(fileSource(payload), bundle, listener);
    }

    public PayloadServer(Source companion, Source bundle, Listener listener) throws IOException {
        if (companion == null || companion.length() < 0) throw new IOException("Companion source is unavailable.");
        this.companion = companion;
        this.bundle = bundle;
        this.listener = listener;
        socket = new ServerSocket();
        socket.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 4);
        Thread thread = new Thread(new Runnable() { public void run() { accept(); } }, "qoder-transfer");
        thread.setDaemon(true); thread.start();
    }

    private static Source fileSource(final File payload) {
        return new Source() {
            public long length() { return payload.length(); }
            public InputStream open() throws IOException { return new FileInputStream(payload); }
        };
    }

    public String baseUrl() { return "http://127.0.0.1:" + socket.getLocalPort() + "/" + token; }

    private void accept() {
        while (!closed) try {
            final Socket peer = socket.accept();
            clients.execute(new Runnable() { public void run() { handle(peer); } });
        } catch (IOException | RejectedExecutionException e) { if (closed) return; }
    }

    private static String line(InputStream in, int limit) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        int b;
        while ((b = in.read()) != -1 && b != '\n') {
            if (bytes.size() >= limit) throw new IOException("Header limit.");
            if (b != '\r') bytes.write(b);
        }
        if (b == -1 && bytes.size() == 0) throw new EOFException();
        return bytes.toString("US-ASCII");
    }

    private static void reply(OutputStream out, int status, String type, long length) throws IOException {
        reply(out, status, type, length, null, -1);
    }

    private static void reply(OutputStream out, int status, String type, long length,
                              String contentRange, long total) throws IOException {
        String reason = status == 200 ? "OK" : status == 206 ? "Partial Content" :
                status == 404 ? "Not Found" : status == 416 ? "Range Not Satisfiable" : "Bad Request";
        StringBuilder headers = new StringBuilder();
        headers.append("HTTP/1.1 ").append(status).append(' ').append(reason)
                .append("\r\nContent-Type: ").append(type)
                .append("\r\nContent-Length: ").append(length)
                .append("\r\nCache-Control: no-store\r\nConnection: close\r\n");
        if (contentRange != null) headers.append("Content-Range: ").append(contentRange).append("\r\n");
        if (status == 200 || status == 206) headers.append("Accept-Ranges: bytes\r\n");
        headers.append("\r\n");
        out.write(headers.toString().getBytes(StandardCharsets.US_ASCII));
    }

    private static long skipFully(InputStream in, long amount) throws IOException {
        long skipped = 0;
        while (skipped < amount) {
            long n = in.skip(amount - skipped);
            if (n > 0) { skipped += n; continue; }
            if (in.read() == -1) throw new EOFException("Payload ended before requested range.");
            skipped++;
        }
        return skipped;
    }

    private static long[] range(String header, long size) {
        if (header == null || header.length() == 0) return new long[] {0, size - 1, 200};
        if (!header.startsWith("bytes=") || header.indexOf(',') >= 0) return null;
        String spec = header.substring(6).trim();
        int dash = spec.indexOf('-');
        if (dash <= 0 || dash != spec.lastIndexOf('-')) return null;
        try {
            long start = Long.parseLong(spec.substring(0, dash));
            if (start < 0 || start >= size) return null;
            String endText = spec.substring(dash + 1).trim();
            long end = endText.length() == 0 ? size - 1 : Long.parseLong(endText);
            if (end < start) return null;
            if (end >= size) end = size - 1;
            return new long[] {start, end, 206};
        } catch (NumberFormatException e) { return null; }
    }

    private static void serve(OutputStream out, Source source, String rangeHeader) throws IOException {
        long size = source.length();
        if (size < 0) { reply(out, 404, "text/plain", 0); out.flush(); return; }
        long[] selection = range(rangeHeader, size);
        if (selection == null || size == 0) {
            reply(out, 416, "text/plain", 0, "bytes */" + size, size);
            out.flush(); return;
        }
        long start = selection[0], end = selection[1], count = end - start + 1;
        if (selection[2] == 206) reply(out, 206, "application/zip", count,
                "bytes " + start + "-" + end + "/" + size, size);
        else reply(out, 200, "application/zip", count);
        try (InputStream file = source.open()) {
            skipFully(file, start);
            byte[] bytes = new byte[16384];
            long remaining = count;
            while (remaining > 0) {
                int wanted = (int) Math.min(bytes.length, remaining);
                int n = file.read(bytes, 0, wanted);
                if (n == -1) throw new EOFException("Payload ended early.");
                out.write(bytes, 0, n);
                remaining -= n;
            }
        }
        out.flush();
    }

    private void handle(Socket peer) {
        try (Socket p = peer) {
            p.setSoTimeout(5000);
            InputStream in = new BufferedInputStream(p.getInputStream());
            OutputStream out = new BufferedOutputStream(p.getOutputStream());
            String[] request = line(in, 2048).split(" ");
            if (request.length != 3) { reply(out, 400, "text/plain", 0); out.flush(); return; }
            int length = 0, total = 0;
            String rangeHeader = null, header;
            while (!(header = line(in, 4096)).isEmpty()) {
                total += header.length(); if (total > 8192) throw new IOException("Headers too large.");
                String lower = header.toLowerCase(Locale.ROOT);
                if (lower.startsWith("content-length:")) length = Integer.parseInt(header.substring(15).trim());
                if (lower.startsWith("range:")) rangeHeader = header.substring(6).trim();
                if (lower.startsWith("transfer-encoding:")) throw new IOException("Chunked requests are unsupported.");
            }
            String base = "/" + token + "/";
            if (request[0].equals("GET") && request[1].equals(base + "companion.zip")) {
                serve(out, companion, rangeHeader); return;
            }
            if (request[0].equals("GET") && request[1].equals(base + "android-tools.zip")) {
                if (bundle == null) { reply(out, 404, "text/plain", 0); out.flush(); return; }
                serve(out, bundle, rangeHeader); return;
            }
            if (!request[0].equals("POST") || !request[1].equals(base + "status")) {
                reply(out, 404, "text/plain", 0); out.flush(); return;
            }
            if (length < 1 || length > 8192) { reply(out, 400, "text/plain", 0); out.flush(); return; }
            byte[] bytes = new byte[length]; int offset = 0;
            while (offset < length) { int n = in.read(bytes, offset, length-offset); if (n == -1) throw new EOFException(); offset += n; }
            Map<String,String> fields = new HashMap<String,String>();
            for (String pair : new String(bytes, StandardCharsets.UTF_8).split("&")) {
                String[] parts = pair.split("=", 2);
                if (parts.length == 2) fields.put(URLDecoder.decode(parts[0], "UTF-8"), URLDecoder.decode(parts[1], "UTF-8"));
            }
            String phase = fields.get("phase"), message = fields.get("message");
            int exitCode = Integer.parseInt(fields.containsKey("exit_code") ? fields.get("exit_code") : "-1");
            if (phase == null || !Arrays.asList("preparing","downloading","installing","verifying","completed","failed").contains(phase) || message == null || message.length() > 2000 || phase.equals("completed") && exitCode != 0) {
                reply(out, 400, "text/plain", 0); out.flush(); return;
            }
            reply(out, 200, "text/plain", 0); out.flush(); listener.progress(phase,message,exitCode);
        } catch (IOException | IllegalArgumentException e) { /* An incomplete request is not a verified status. */ }
    }

    public void close() throws IOException { closed = true; socket.close(); clients.shutdownNow(); }
}
