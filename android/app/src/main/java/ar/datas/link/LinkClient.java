package ar.datas.link;

import java.io.Closeable;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.Map;

import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * The phone's side of the link between a person's own devices.
 *
 * Linking (once): the computer shows a one-time code. The phone invents a long random
 * secret and proves, with the code, that the secret is its own; the computer proves it knows
 * the code too. The code never travels, and both proofs include the fingerprint of the
 * computer's certificate, so a device in between cannot swap in its own.
 *
 * Afterwards: TLS 1.3, accepting only that exact certificate, and the secret shown inside
 * the encrypted connection. No account, no server in the middle.
 *
 * The same messages, in Python, are in tests/phone.py; the computer's side is
 * datas/link/__init__.py. This file uses only the standard library, so the tests compile it
 * with plain javac and run it against a real Datas.
 */
public final class LinkClient {
    public static final String PROTO = "datas-link-v1";
    public static final int DEFAULT_PORT = 8424;
    public static final int PBKDF2_ROUNDS = 300000;
    public static final int CODE_LENGTH = 12;
    private static final SecureRandom RANDOM = new SecureRandom();

    private LinkClient() {}

    /** Something to show the person: wrong code, computer not reachable, not linked any more. */
    public static final class LinkException extends Exception {
        public LinkException(String message) {
            super(message);
        }
    }

    /** A linked computer, as the phone remembers it. */
    public static final class Computer {
        public final String id;      // fingerprint (SHA-256, hex) of the computer's certificate
        public final String name;
        public final String host;
        public final int port;
        public final String secret;  // this phone's secret for that computer (hex)

        public Computer(String id, String name, String host, int port, String secret) {
            this.id = id;
            this.name = name;
            this.host = host;
            this.port = port;
            this.secret = secret;
        }

        public String toJson() {
            return Json.obj("id", id, "name", name, "host", host, "port", port, "secret", secret);
        }

        public static Computer fromJson(String text) {
            Map<String, Object> m = Json.object(text);
            Object p = m.get("port");
            int port = p instanceof Number ? ((Number) p).intValue() : DEFAULT_PORT;
            return new Computer(Json.str(m, "id"), Json.str(m, "name"), Json.str(m, "host"), port, Json.str(m, "secret"));
        }

        public Computer at(String newHost, int newPort) {
            return new Computer(id, name, newHost, newPort, secret);
        }
    }

    // ---- linking -------------------------------------------------------------------

    public static Computer pair(String host, int port, String code, String phoneName, String os)
            throws LinkException, IOException {
        String clean = cleanCode(code);
        if (clean.length() != CODE_LENGTH) throw new LinkException("The code has " + CODE_LENGTH + " letters and digits.");
        byte[] secret = new byte[32];
        RANDOM.nextBytes(secret);
        String me = hex(sha256(secret));
        String[] seen = new String[1];
        SSLSocket s = connect(host, port, null, seen);
        try {
            String computer = seen[0];
            byte[] nc = new byte[16];
            RANDOM.nextBytes(nc);
            send(s, Json.obj("op", "pair", "app", true, "id", me, "name", phoneName, "os", os, "nonce", hex(nc)));
            Map<String, Object> r = receive(s);
            if (!Json.yes(r, "ok")) throw new LinkException(orElse(Json.str(r, "error"), "That computer is not showing a code right now."));
            byte[] ns = unhex(Json.str(r, "nonce"));
            byte[] key = derive(clean, concat(nc, ns));
            send(s, Json.obj("proof", hex(proof(key, "client", me, computer, nc, ns))));
            Map<String, Object> r2 = receive(s);
            if (!Json.yes(r2, "ok")) throw new LinkException(orElse(Json.str(r2, "error"), "Wrong or expired code."));
            byte[] want = proof(key, "server", computer, me, ns, nc);
            if (!MessageDigest.isEqual(want, unhex(Json.str(r2, "proof")))) {
                throw new LinkException("The computer could not prove it knows the code. Nothing was linked.");
            }
            return new Computer(computer, orElse(Json.str(r, "name"), host), host, port, hex(secret));
        } catch (IllegalArgumentException e) {
            throw new LinkException("The computer sent something unexpected. Is its Datas up to date?");
        } finally {
            quietly(s);
        }
    }

    // ---- after linking ---------------------------------------------------------------

    /** How the computer is: name, version, whether an AI is ready. */
    public static Map<String, Object> info(Computer c) throws LinkException, IOException {
        SSLSocket s = open(c, "info");
        quietly(s);
        return lastReply.get();
    }

    private static final ThreadLocal<Map<String, Object>> lastReply = new ThreadLocal<Map<String, Object>>();

    /**
     * Connect to a linked computer and make one request. For "window" the returned connection
     * then carries plain web traffic to that computer's Datas.
     */
    public static SSLSocket open(Computer c, String op) throws LinkException, IOException {
        SSLSocket s = connect(c.host, c.port, c.id, new String[1]);
        try {
            send(s, Json.obj("op", op, "auth", c.secret));
            Map<String, Object> r = receive(s);
            lastReply.set(r);
            if (!Json.yes(r, "ok")) {
                throw new LinkException(orElse(Json.str(r, "error"), "The computer refused."));
            }
            s.setSoTimeout(0); // answers from an AI arrive little by little, for as long as it writes
            return s;
        } catch (LinkException | IOException | RuntimeException e) {
            quietly(s);
            if (e instanceof RuntimeException) throw new LinkException("The computer sent something unexpected.");
            throw e;
        }
    }

    /**
     * A door on this phone (127.0.0.1, a free port): whatever the app's web view asks there is
     * carried, encrypted, to the linked computer's Datas. One encrypted connection per
     * connection of the web view.
     */
    public static final class Door implements Closeable {
        private final ServerSocket server;
        private final Computer computer;
        private volatile boolean closed;

        public Door(Computer computer) throws IOException {
            this.computer = computer;
            this.server = new ServerSocket(0, 64, InetAddress.getByAddress(new byte[] {127, 0, 0, 1}));
            Thread t = new Thread(new Runnable() {
                @Override public void run() {
                    acceptLoop();
                }
            }, "datas-door");
            t.setDaemon(true);
            t.start();
        }

        public int port() {
            return server.getLocalPort();
        }

        public String url() {
            return "http://127.0.0.1:" + port() + "/";
        }

        private void acceptLoop() {
            while (!closed) {
                final Socket local;
                try {
                    local = server.accept();
                } catch (IOException e) {
                    return;
                }
                Thread t = new Thread(new Runnable() {
                    @Override public void run() {
                        carry(local);
                    }
                }, "datas-door-conn");
                t.setDaemon(true);
                t.start();
            }
        }

        private void carry(final Socket local) {
            final SSLSocket remote;
            try {
                remote = open(computer, "window");
            } catch (Exception e) {
                sorry(local, e instanceof LinkException ? e.getMessage()
                        : "Could not reach " + computer.name + ". Is Datas open on it, and is this phone on the same network?");
                return;
            }
            Thread up = new Thread(new Runnable() {
                @Override public void run() {
                    pump(local, remote);
                }
            }, "datas-door-up");
            up.setDaemon(true);
            up.start();
            pump(remote, local);
        }

        private static void pump(Socket from, Socket to) {
            byte[] buf = new byte[16384];
            try {
                InputStream in = from.getInputStream();
                OutputStream out = to.getOutputStream();
                int n;
                while ((n = in.read(buf)) >= 0) {
                    out.write(buf, 0, n);
                    out.flush();
                }
            } catch (IOException ignored) {
                // one side closed: close the other
            } finally {
                quietly(from);
                quietly(to);
            }
        }

        private static void sorry(Socket local, String why) {
            try {
                byte[] body = ("<!doctype html><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">"
                        + "<body style=\"font-family:sans-serif;padding:24px;line-height:1.5\"><h2>Not connected</h2><p>"
                        + why.replace("&", "&amp;").replace("<", "&lt;") + "</p></body>").getBytes(StandardCharsets.UTF_8);
                OutputStream out = local.getOutputStream();
                out.write(("HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\n"
                        + "Connection: close\r\nContent-Length: " + body.length + "\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
                out.write(body);
                out.flush();
            } catch (IOException ignored) {
                // the web view went away
            } finally {
                quietly(local);
            }
        }

        @Override public void close() {
            closed = true;
            quietly(server);
        }
    }

    // ---- the pieces ---------------------------------------------------------------------

    /** TLS 1.3. While pairing (pin == null) any certificate is noted; afterwards only the pinned one passes. */
    private static SSLSocket connect(String host, int port, final String pin, final String[] seen)
            throws LinkException, IOException {
        X509TrustManager tm = new X509TrustManager() {
            @Override public void checkClientTrusted(X509Certificate[] chain, String authType) throws CertificateException {
                throw new CertificateException("this is a client");
            }

            @Override public void checkServerTrusted(X509Certificate[] chain, String authType) throws CertificateException {
                if (chain == null || chain.length == 0) throw new CertificateException("the computer did not identify itself");
                String fp = hex(sha256(chain[0].getEncoded()));
                seen[0] = fp;
                if (pin != null && !MessageDigest.isEqual(pin.getBytes(StandardCharsets.US_ASCII), fp.getBytes(StandardCharsets.US_ASCII))) {
                    throw new CertificateException("that is not the computer this phone was linked to");
                }
            }

            @Override public X509Certificate[] getAcceptedIssuers() {
                return new X509Certificate[0];
            }
        };
        SSLSocket s = null;
        try {
            SSLContext ctx = SSLContext.getInstance("TLSv1.3");
            ctx.init(null, new TrustManager[] {tm}, RANDOM);
            s = (SSLSocket) ctx.getSocketFactory().createSocket();
            s.connect(new InetSocketAddress(host, port), 12000);
            s.setEnabledProtocols(new String[] {"TLSv1.3"});
            s.setSoTimeout(30000);
            s.startHandshake();
            if (seen[0] == null) throw new IOException("no certificate was seen");
            return s;
        } catch (GeneralSecurityException e) {
            quietly(s);
            throw new LinkException("This phone cannot make the encrypted connection (it needs Android 10 or newer).");
        } catch (IOException e) {
            quietly(s);
            Throwable cause = e.getCause();
            if (cause instanceof CertificateException && pin != null) {
                throw new LinkException("The device at that address is not the computer that was linked.");
            }
            throw e;
        }
    }

    private static void send(Socket s, String json) throws IOException {
        byte[] data = json.getBytes(StandardCharsets.UTF_8);
        DataOutputStream out = new DataOutputStream(s.getOutputStream());
        out.writeInt(data.length);
        out.write(data);
        out.flush();
    }

    private static Map<String, Object> receive(Socket s) throws IOException {
        DataInputStream in = new DataInputStream(s.getInputStream());
        int n = in.readInt();
        if (n < 0 || n > (1 << 20)) throw new IOException("message too large");
        byte[] data = new byte[n];
        in.readFully(data);
        return Json.object(new String(data, StandardCharsets.UTF_8));
    }

    public static String cleanCode(String code) {
        StringBuilder b = new StringBuilder();
        for (char ch : code.toUpperCase(java.util.Locale.ROOT).toCharArray()) {
            if (Character.isLetterOrDigit(ch)) b.append(ch);
        }
        return b.toString();
    }

    /** The code, stretched: PBKDF2-HMAC-SHA256, salt = "datas-link-v1" + both random numbers. */
    static byte[] derive(String cleanCode, byte[] nonces) throws LinkException {
        try {
            byte[] salt = concat(PROTO.getBytes(StandardCharsets.US_ASCII), nonces);
            PBEKeySpec spec = new PBEKeySpec(cleanCode.toCharArray(), salt, PBKDF2_ROUNDS, 256);
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException e) {
            throw new LinkException("This phone lacks a needed security function (PBKDF2).");
        }
    }

    static byte[] proof(byte[] key, String role, String fpSelf, String fpOther, byte[] n1, byte[] n2) throws LinkException {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            String msg = PROTO + "|" + role + "|" + fpSelf + "|" + fpOther + "|" + hex(n1) + "|" + hex(n2);
            return mac.doFinal(msg.getBytes(StandardCharsets.US_ASCII));
        } catch (GeneralSecurityException e) {
            throw new LinkException("This phone lacks a needed security function (HMAC).");
        }
    }

    static byte[] sha256(byte[] data) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(data);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e);
        }
    }

    static String hex(byte[] data) {
        StringBuilder b = new StringBuilder(data.length * 2);
        for (byte x : data) b.append(String.format("%02x", x & 0xff));
        return b.toString();
    }

    static byte[] unhex(String text) {
        if (text.length() % 2 != 0) throw new IllegalArgumentException("odd hex");
        byte[] out = new byte[text.length() / 2];
        for (int k = 0; k < out.length; k++) out[k] = (byte) Integer.parseInt(text.substring(2 * k, 2 * k + 2), 16);
        return out;
    }

    private static byte[] concat(byte[] a, byte[] b) {
        byte[] out = new byte[a.length + b.length];
        System.arraycopy(a, 0, out, 0, a.length);
        System.arraycopy(b, 0, out, a.length, b.length);
        return out;
    }

    private static String orElse(String a, String b) {
        return a == null || a.isEmpty() ? b : a;
    }

    private static void quietly(Closeable c) {
        if (c == null) return;
        try {
            c.close();
        } catch (IOException ignored) {
            // already closed
        }
    }
}
