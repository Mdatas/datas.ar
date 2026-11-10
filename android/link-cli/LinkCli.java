import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

import ar.datas.link.Json;
import ar.datas.link.LinkClient;

/**
 * A tiny command line around the phone's link code, for the tests (it is not part of the app):
 *   LinkCli pair <host> <port> <code> <name>        prints what the phone would remember
 *   LinkCli info <remembered>                        prints how the computer is
 *   LinkCli get  <remembered> <path>                 a web request through the door
 *   LinkCli post <remembered> <path> <json>
 */
public final class LinkCli {
    public static void main(String[] a) throws Exception {
        try {
            if (a[0].equals("pair")) {
                System.out.println(LinkClient.pair(a[1], Integer.parseInt(a[2]), a[3], a[4], "android").toJson());
            } else if (a[0].equals("info")) {
                System.out.println(Json.obj("name", Json.str(LinkClient.info(LinkClient.Computer.fromJson(a[1])), "name")));
            } else {
                LinkClient.Door door = new LinkClient.Door(LinkClient.Computer.fromJson(a[1]));
                try {
                    HttpURLConnection c = (HttpURLConnection) new URL("http://127.0.0.1:" + door.port() + a[2]).openConnection(java.net.Proxy.NO_PROXY);
                    c.setConnectTimeout(15000);
                    c.setReadTimeout(60000);
                    if (a[0].equals("post")) {
                        c.setRequestMethod("POST");
                        c.setDoOutput(true);
                        c.setRequestProperty("Content-Type", "application/json");
                        OutputStream out = c.getOutputStream();
                        out.write(a[3].getBytes(StandardCharsets.UTF_8));
                        out.close();
                    }
                    int status = c.getResponseCode();
                    InputStream in = status >= 400 ? c.getErrorStream() : c.getInputStream();
                    ByteArrayOutputStream buf = new ByteArrayOutputStream();
                    byte[] b = new byte[8192];
                    int n;
                    while (in != null && (n = in.read(b)) >= 0) buf.write(b, 0, n);
                    System.out.println(status);
                    System.out.println(new String(buf.toByteArray(), StandardCharsets.UTF_8));
                } finally {
                    door.close();
                }
            }
        } catch (LinkClient.LinkException e) {
            System.out.println("LINK: " + e.getMessage());
            System.exit(2);
        }
    }
}
