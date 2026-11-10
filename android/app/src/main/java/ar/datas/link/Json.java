package ar.datas.link;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Just enough JSON for the link's small messages, so this package needs nothing but the
 * standard library and can be compiled and tested on any computer as well as on Android.
 * Objects become Map, lists become List, numbers become Long or Double.
 */
public final class Json {
    private final String s;
    private int i;

    private Json(String s) {
        this.s = s;
    }

    public static Object parse(String text) {
        Json p = new Json(text);
        p.space();
        Object v = p.value();
        p.space();
        if (p.i != text.length()) throw new IllegalArgumentException("unexpected text after JSON");
        return v;
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> object(String text) {
        Object v = parse(text);
        if (!(v instanceof Map)) throw new IllegalArgumentException("not a JSON object");
        return (Map<String, Object>) v;
    }

    /** obj("op", "pair", "app", true) → {"op":"pair","app":true} */
    public static String obj(Object... keysAndValues) {
        StringBuilder b = new StringBuilder("{");
        for (int k = 0; k + 1 < keysAndValues.length; k += 2) {
            if (k > 0) b.append(',');
            b.append(quote(String.valueOf(keysAndValues[k]))).append(':');
            Object v = keysAndValues[k + 1];
            if (v == null) b.append("null");
            else if (v instanceof Number || v instanceof Boolean) b.append(v);
            else b.append(quote(String.valueOf(v)));
        }
        return b.append('}').toString();
    }

    public static String quote(String text) {
        StringBuilder b = new StringBuilder("\"");
        for (int k = 0; k < text.length(); k++) {
            char c = text.charAt(k);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        return b.append('"').toString();
    }

    public static String str(Map<String, Object> m, String key) {
        Object v = m == null ? null : m.get(key);
        return v == null ? "" : String.valueOf(v);
    }

    public static boolean yes(Map<String, Object> m, String key) {
        return m != null && Boolean.TRUE.equals(m.get(key));
    }

    private void space() {
        while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++;
    }

    private Object value() {
        if (i >= s.length()) throw new IllegalArgumentException("unexpected end of JSON");
        char c = s.charAt(i);
        if (c == '{') return map();
        if (c == '[') return list();
        if (c == '"') return string();
        if (s.startsWith("true", i)) { i += 4; return Boolean.TRUE; }
        if (s.startsWith("false", i)) { i += 5; return Boolean.FALSE; }
        if (s.startsWith("null", i)) { i += 4; return null; }
        return number();
    }

    private Map<String, Object> map() {
        Map<String, Object> m = new LinkedHashMap<String, Object>();
        i++;
        space();
        if (s.charAt(i) == '}') { i++; return m; }
        while (true) {
            space();
            String k = string();
            space();
            if (s.charAt(i++) != ':') throw new IllegalArgumentException("expected ':'");
            space();
            m.put(k, value());
            space();
            char c = s.charAt(i++);
            if (c == '}') return m;
            if (c != ',') throw new IllegalArgumentException("expected ',' or '}'");
        }
    }

    private List<Object> list() {
        List<Object> l = new ArrayList<Object>();
        i++;
        space();
        if (s.charAt(i) == ']') { i++; return l; }
        while (true) {
            space();
            l.add(value());
            space();
            char c = s.charAt(i++);
            if (c == ']') return l;
            if (c != ',') throw new IllegalArgumentException("expected ',' or ']'");
        }
    }

    private String string() {
        if (s.charAt(i) != '"') throw new IllegalArgumentException("expected a string");
        StringBuilder b = new StringBuilder();
        i++;
        while (true) {
            char c = s.charAt(i++);
            if (c == '"') return b.toString();
            if (c != '\\') { b.append(c); continue; }
            char e = s.charAt(i++);
            switch (e) {
                case 'n': b.append('\n'); break;
                case 'r': b.append('\r'); break;
                case 't': b.append('\t'); break;
                case 'b': b.append('\b'); break;
                case 'f': b.append('\f'); break;
                case 'u': b.append((char) Integer.parseInt(s.substring(i, i + 4), 16)); i += 4; break;
                default: b.append(e);
            }
        }
    }

    private Object number() {
        int start = i;
        while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
        String n = s.substring(start, i);
        if (n.isEmpty()) throw new IllegalArgumentException("unexpected character in JSON");
        if (n.indexOf('.') < 0 && n.indexOf('e') < 0 && n.indexOf('E') < 0) {
            try { return Long.valueOf(n); } catch (NumberFormatException ignored) { /* too big: as double */ }
        }
        return Double.valueOf(n);
    }
}
