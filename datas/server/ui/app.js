"use strict";
/* Datas window, part 1 — what every screen shares: building the page, talking to the local
   server, translations, navigation, dialogs, background jobs and a safe Markdown reader.
   Nothing is loaded from outside this computer. */

const NS = "http://www.w3.org/2000/svg";
const $ = (sel, root = document) => root.querySelector(sel);
const S = {
  lang: "en", theme: "auto", status: null, priv: null, screen: "chat", cleanup: null,
  helpers: null, library: null, pool: false, starterTold: false, getting: null,
};
const SCREENS = {};

/* ---------- building the page (never with raw HTML strings) ---------- */
function add(el, ...kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false || k === "") continue;
    el.append(k.nodeType ? k : document.createTextNode(String(k)));
  }
  return el;
}
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k === "data") Object.assign(el.dataset, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (typeof v === "boolean") el[k] = v;
    else el.setAttribute(k, v);
  }
  return add(el, kids);
}
const clear = el => { el.replaceChildren(); return el; };
const debounce = (fn, ms) => { let tm; return (...a) => { clearTimeout(tm); tm = setTimeout(() => fn(...a), ms); }; };

const ICONS = {
  plus: "M12 5v14M5 12h14", close: "M6 6l12 12M18 6L6 18", check: "M5 12.5l4.5 4.5L19 7.5",
  menu: "M4 7h16M4 12h16M4 17h16", down: "M6 9l6 6 6-6", back: "M15 5l-7 7 7 7",
  search: "M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM20 20l-4.6-4.6",
  send: "M4 12l16-8-6 16-3-7-7-1z", stop: "M7 7h10v10H7z", play: "M8 5l11 7-11 7z",
  clip: "M20 11.5l-8.2 8.2a5 5 0 0 1-7.1-7.1l8.6-8.6a3.4 3.4 0 0 1 4.8 4.8l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8",
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
  copy: "M9 9h10v11H9zM5 15V4h10", speaker: "M4 9v6h4l5 4V5L8 9H4zM16.5 8.5a5 5 0 0 1 0 7",
  save: "M12 4v11M7 11l5 5 5-5M5 20h14", trash: "M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13",
  edit: "M4 20h4l11-11-4-4L4 16v4zM14 6l4 4",
  more: "M5 12a1 1 0 1 0 2 0 1 1 0 0 0-2 0zM11 12a1 1 0 1 0 2 0 1 1 0 0 0-2 0zM17 12a1 1 0 1 0 2 0 1 1 0 0 0-2 0z",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.8 3 2.8 15 0 18M12 3c-2.8 3-2.8 15 0 18",
  chip: "M8 8h8v8H8zM4 10h4M4 14h4M16 10h4M16 14h4M10 4v4M14 4v4M10 16v4M14 16v4",
  book: "M5 4h9a4 4 0 0 1 4 4v12H9a4 4 0 0 1-4-4V4zM5 16a4 4 0 0 1 4-4h9",
  toolbox: "M4 9h16v10H4zM9 9V6h6v3M4 13h16M11 12v2h2v-2",
  devices: "M3 6h12v9H3zM7 19h4M9 15v4M17 9h4v11h-4z",
  phone: "M8 3h8v18H8zM11 18h2",
  camera: "M4 8h4l2-2h4l2 2h4v11H4zM12 10.5a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  printer: "M7 9V4h10v5M5 9h14v8H5zM8 14h8v6H8z",
  screen: "M3 5h18v11H3zM9 20h6M12 16v4",
  plug: "M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0zM12 17v4",
  image: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15 9.5h.01",
  sliders: "M5 7h9M18 7h1M5 12h2M11 12h8M5 17h9M18 17h1M16 5v4M9 10v4M16 15v4",
  info: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5h.01",
  folder: "M3 7h6l2 2h10v10H3z", external: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  refresh: "M20 6v5h-5M4 18v-5h5M19 11a7 7 0 0 0-12.5-3.5M5 13a7 7 0 0 0 12.5 3.5",
  lock: "M6 11h12v9H6zM9 11V8a3 3 0 0 1 6 0v3",
  spark: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM18.5 16l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z",
  chat: "M4 5h16v11H9l-5 4z", moon: "M19 14.5A8 8 0 0 1 9.5 5a7 7 0 1 0 9.5 9.5z",
  day: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2",
  doc: "M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6",
  chain: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  shield: "M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z",
  up: "M12 20V8M7 12l5-5 5 5M5 4h14", undo: "M8 8L4 12l4 4M4 12h10a5 5 0 0 1 0 10h-3",
  agent: "M7 9h10v9H7zM12 9V5M10 13h.01M14 13h.01M4 13v3M20 13v3",
};
function icon(name, size = 20) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", size); svg.setAttribute("height", size);
  svg.setAttribute("class", "ic"); svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(NS, "path");
  p.setAttribute("d", ICONS[name] || ICONS.info);
  svg.append(p);
  return svg;
}
/* The sun says how the AI is: rays = awake, turning rays = working, moon = asleep, dashed = none. */
function sunMark(state = "awake", size = 24) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 48 48");
  svg.setAttribute("width", size); svg.setAttribute("height", size);
  svg.setAttribute("class", "sun " + state); svg.setAttribute("aria-hidden", "true");
  if (state === "asleep") {
    const m = document.createElementNS(NS, "path");
    m.setAttribute("class", "moon"); m.setAttribute("d", "M37 30A16 16 0 0 1 18 11a15 15 0 1 0 19 19z");
    svg.append(m);
    return svg;
  }
  const g = document.createElementNS(NS, "g");
  g.setAttribute("class", "rays");
  for (let i = 0; i < 16; i++) {
    const r = document.createElementNS(NS, "path");
    r.setAttribute("d", i % 2 ? "M24 7l1.7 6h-3.4z" : "M24 2l2.3 10h-4.6z");
    r.setAttribute("transform", `rotate(${i * 22.5} 24 24)`);
    g.append(r);
  }
  const c = document.createElementNS(NS, "circle");
  c.setAttribute("cx", 24); c.setAttribute("cy", 24); c.setAttribute("r", 10); c.setAttribute("class", "disc");
  svg.append(g, c);
  return svg;
}
const spinner = () => h("div", { class: "spinner", role: "status", "aria-label": t("loading") });

/* ---------- the local server ---------- */
async function api(path, opts = {}) {
  const init = { method: opts.method || (opts.body !== undefined || opts.raw ? "POST" : "GET"), headers: {} };
  if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
  if (opts.raw) init.body = opts.raw;
  if (opts.signal) init.signal = opts.signal;
  const r = await fetch(path, init);
  if (!r.ok) {
    let msg = r.statusText || ("HTTP " + r.status);
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : (j.message || (j.detail ? JSON.stringify(j.detail) : msg));
    } catch (e) { /* not JSON */ }
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r;
}
const fileBase64 = file => new Promise((res, rej) => {
  const fr = new FileReader();
  fr.onload = () => res(String(fr.result).split(",")[1] || "");
  fr.onerror = () => rej(fr.error);
  fr.readAsDataURL(file);
});
const fileDataUrl = file => new Promise((res, rej) => {
  const fr = new FileReader();
  fr.onload = () => res(String(fr.result));
  fr.onerror = () => rej(fr.error);
  fr.readAsDataURL(file);
});

/* ---------- words ---------- */
function t(key, vars) {
  let s = (I18N[S.lang] && I18N[S.lang][key]) ?? I18N.en[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split("{" + k + "}").join(String(v));
  return s;
}
const es = () => S.lang === "es";
const gb = n => (Math.round(n * 10) / 10).toLocaleString(S.lang) + " GB";
function when(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString(S.lang, { day: "numeric", month: "short" }) + ", " +
    d.toLocaleTimeString(S.lang, { hour: "2-digit", minute: "2-digit" });
}
async function setLang(lang, save = true) {
  S.lang = I18N[lang] ? lang : "en";
  document.documentElement.lang = S.lang;
  S.helpers = null;
  if (save) { try { await api("/api/privacy", { body: { lang: S.lang } }); } catch (e) { /* keep going */ } }
  renderShell();
  go(S.screen);
}
window.setLangForShot = lang => setLang(lang, false);

/* ---------- day and night ---------- */
const isNight = () => document.documentElement.dataset.theme === "night";
function applyTheme() {
  const dark = S.theme === "night" || (S.theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "night" : "day";
  const b = $("#themeBtn");
  if (b) clear(b).append(icon(dark ? "day" : "moon"));
}
async function setTheme(theme) {
  S.theme = theme;
  applyTheme();
  try { await api("/api/settings", { body: { theme } }); } catch (e) { /* cosmetic */ }
}

/* ---------- small floating things ---------- */
function toast(text, opts = {}) {
  const el = h("div", { class: "toast" + (opts.bad ? " bad" : ""), role: "status" }, h("span", { class: "grow", text }));
  for (const a of opts.actions || []) {
    el.append(h("button", { class: "btn small", onclick: () => { el.remove(); a.fn(); } }, a.label));
  }
  el.append(h("button", { class: "icon-btn", "aria-label": t("close"), style: "color:inherit", onclick: () => el.remove() }, icon("close", 16)));
  $("#toasts").append(el);
  setTimeout(() => el.remove(), opts.ms || (opts.actions ? 12000 : 5000));
}
const oops = e => toast(e && e.message ? e.message : String(e), { bad: true, ms: 9000 });

function openDialog({ title, body, actions, wide, onClose }) {
  const close = () => { wrap.remove(); document.removeEventListener("keydown", onKey); if (onClose) onClose(); };
  const onKey = e => { if (e.key === "Escape") close(); };
  const wrap = h("div", { class: "overlay", onmousedown: e => { if (e.target === wrap) close(); } },
    h("div", { class: "dialog" + (wide ? " wide" : ""), role: "dialog", "aria-modal": "true", "aria-label": title },
      h("header", {}, h("h2", { text: title }),
        h("button", { class: "icon-btn", "aria-label": t("close"), onclick: close }, icon("close"))),
      h("div", { class: "dialog-body" }, body),
      actions && h("footer", {}, typeof actions === "function" ? actions(close) : actions)));
  document.body.append(wrap);
  document.addEventListener("keydown", onKey);
  const first = wrap.querySelector(".dialog-body input, .dialog-body textarea, .dialog-body select, footer .primary");
  if (first) first.focus();
  return close;
}
function confirmDialog(title, text, okLabel, danger) {
  return new Promise(resolve => {
    let answered = false;
    const done = (v, close) => { answered = true; close(); resolve(v); };
    openDialog({
      title, body: h("p", { text }), onClose: () => { if (!answered) resolve(false); },
      actions: close => [
        h("button", { class: "btn", onclick: () => done(false, close) }, t("cancel")),
        h("button", { class: "btn " + (danger ? "danger" : "primary"), onclick: () => done(true, close) }, okLabel),
      ],
    });
  });
}
function promptDialog(title, label, value = "") {
  return new Promise(resolve => {
    let answered = false;
    const input = h("input", { type: "text", value, "aria-label": label });
    const done = (v, close) => { answered = true; close(); resolve(v); };
    const close = openDialog({
      title, body: h("label", { class: "field" }, label, input), onClose: () => { if (!answered) resolve(null); },
      actions: c => [
        h("button", { class: "btn", onclick: () => done(null, c) }, t("cancel")),
        h("button", { class: "btn primary", onclick: () => done(input.value.trim(), c) }, t("save")),
      ],
    });
    input.addEventListener("keydown", e => { if (e.key === "Enter") done(input.value.trim(), close); });
    input.select();
  });
}
/* items: {label, note, icon, fn, danger} | {head} | "hr" */
function openMenu(anchor, items) {
  document.querySelectorAll(".menu").forEach(m => m.remove());
  const menu = h("div", { class: "menu", role: "menu" });
  const close = () => { menu.remove(); document.removeEventListener("mousedown", away, true); document.removeEventListener("keydown", onKey); };
  const away = e => { if (!menu.contains(e.target)) close(); };
  const onKey = e => { if (e.key === "Escape") { close(); anchor.focus(); } };
  for (const it of items) {
    if (!it) continue;
    if (it === "hr") menu.append(h("hr"));
    else if (it.head) menu.append(h("div", { class: "head", text: it.head }));
    else {
      menu.append(h("button", { role: "menuitem", class: it.danger ? "danger" : "", disabled: !!it.disabled, onclick: () => { close(); it.fn(); } },
        it.icon && (it.icon.nodeType ? it.icon : icon(it.icon, 18)),
        h("span", { class: "grow" }, it.label, it.note && h("small", { text: it.note }))));
    }
  }
  document.body.append(menu);
  const r = anchor.getBoundingClientRect(), mw = menu.offsetWidth, mh = menu.offsetHeight;
  menu.style.left = Math.max(8, Math.min(r.left, innerWidth - mw - 8)) + "px";
  menu.style.top = (r.bottom + mh + 8 > innerHeight && r.top - mh - 6 > 0 ? r.top - mh - 6 : r.bottom + 6) + "px";
  setTimeout(() => { document.addEventListener("mousedown", away, true); document.addEventListener("keydown", onKey); }, 0);
  const first = menu.querySelector("button:not(:disabled)");
  if (first) first.focus();
  return close;
}
/* Web addresses open in the person's own browser, never inside this window. */
/* S.status.remote: this window is being shown on a linked phone, through the encrypted link.
   What "open" means changes: a web address opens on the phone; a saved file stays on the computer. */
const isRemote = () => !!(S.status && S.status.remote);
async function openUrl(url) {
  if (isRemote()) { location.assign(url); return; }   // the phone app hands web addresses to the phone's browser
  try { await api("/api/open-url", { body: { url } }); } catch (e) { window.open(url, "_blank", "noopener"); }
}
const extLink = (label, url) => h("a", { href: url, rel: "noopener", onclick: e => { e.preventDefault(); openUrl(url); } }, label);
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); }
  catch (e) {
    const ta = h("textarea", { style: "position:fixed;opacity:0" });
    ta.value = text; document.body.append(ta); ta.select();
    try { document.execCommand("copy"); } finally { ta.remove(); }
  }
  toast(t("copied"), { ms: 1800 });
}
const openFile = (path, reveal = false) => api("/api/open", { body: { path, reveal } }).catch(oops);
function savedToast(r) {
  if (isRemote()) { toast(t("remote_saved", { device: S.status.remote.device, name: r.name || String(r.path).split(/[\\/]/).pop() })); return; }
  toast(t("saved_as", { name: r.name || String(r.path).split(/[\\/]/).pop() }), {
    actions: [{ label: t("open"), fn: () => openFile(r.path) }, { label: t("show_folder"), fn: () => openFile(r.path, true) }],
  });
}

/* ---------- hardware of this computer (cameras, the screen, printers…) ---------- */
const Things = {
  /* The camera is read with FFmpeg. If it is missing, offer to fetch it once. */
  async ensureFfmpeg() {
    if ((await api("/api/things/ffmpeg")).found) return true;
    const th = await api("/api/things");
    if (th.ffmpeg.found) return true;
    if (!th.cameras.length && !th.problems.cameras) { toast(t("hw_no_camera")); return false; }
    if (!th.ffmpeg.bytes) { toast(th.problems.cameras || t("hw_no_camera"), { bad: true, ms: 9000 }); return false; }
    if (!await confirmDialog("FFmpeg", t("cam_need_ffmpeg", { size: Math.round(th.ffmpeg.bytes / 1e6) }), t("cam_get"))) return false;
    const x = await Jobs.track(await api("/api/things/ffmpeg", { method: "POST" }), { title: "FFmpeg" });
    return x.state === "done";
  },
  async photo(camera) {
    if (!await Things.ensureFfmpeg()) return null;
    return api("/api/things/camera/photo", { body: camera ? { camera } : {} });
  },
  /* aside: Datas gets out of the way first, so the picture shows what is behind it */
  async screen(aside) {
    const own = S.status && S.status.own_window;
    if (aside && !own) toast(t("cam_screen_wait"), { ms: 3200 });
    return api("/api/things/screen", { body: { hide: !!aside, wait: aside && !own ? 3 : 0 } });
  },
  show(title, r) {
    openDialog({ title, wide: true, body: [h("img", { class: "shot", src: r.image, alt: title }), h("p", { class: "small muted", text: r.width + " × " + r.height })],
      actions: close => [h("button", { class: "btn primary", onclick: close }, t("close"))] });
  },
};

/* ---------- Markdown, read safely: text becomes page elements, never markup ---------- */
function mdInline(text, into) {
  const re = /(`[^`\n]+`)|(\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\))|(\*\*([^*\n]+)\*\*)|(__([^_\n]+)__)|(\*([^*\s][^*\n]*?)\*)|(https?:\/\/[^\s<>()]*[^\s<>().,;:!?'"])/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) into.append(text.slice(last, m.index));
    if (m[1]) into.append(h("code", { text: m[1].slice(1, -1) }));
    else if (m[2]) into.append(extLink(m[3], m[4]));
    else if (m[5]) into.append(mdInline(m[6], h("strong")));
    else if (m[7]) into.append(mdInline(m[8], h("strong")));
    else if (m[9]) into.append(mdInline(m[10], h("em")));
    else if (m[11]) into.append(extLink(m[11], m[11]));
    last = re.lastIndex;
  }
  if (last < text.length) into.append(text.slice(last));
  return into;
}
function codeBlock(code, lang) {
  return h("div", { class: "code" },
    h("div", { class: "code-head" }, h("span", { class: "grow", text: lang || t("code") }),
      h("button", { class: "btn quiet small", onclick: () => copyText(code) }, icon("copy", 16), t("copy")),
      h("button", { class: "btn quiet small", onclick: async () => {
        try { savedToast(await api("/api/export/code", { body: { code, lang: lang || "", title: "" } })); } catch (e) { oops(e); }
      } }, icon("save", 16), t("save_file"))),
    h("pre", {}, h("code", { text: code })));
}
function md(src) {
  const out = document.createDocumentFragment();
  const lines = String(src || "").replace(/\r\n?/g, "\n").split("\n");
  const LIST = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
  const isSep = s => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(s);
  const cells = s => s.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
  const tableAt = k => lines[k].includes("|") && k + 1 < lines.length && isSep(lines[k + 1]);
  let i = 0, m;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if ((m = line.match(/^\s*(```|~~~)\s*([\w+#.-]*)\s*$/))) {
      const buf = []; i++;
      while (i < lines.length && !lines[i].trim().startsWith(m[1])) buf.push(lines[i++]);
      i++;
      out.append(codeBlock(buf.join("\n"), m[2]));
    } else if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      out.append(mdInline(m[2].replace(/\s+#+\s*$/, ""), h("h" + Math.min(m[1].length + 1, 5)))); i++;
    } else if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      out.append(h("hr")); i++;
    } else if (/^\s*>/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.append(add(h("blockquote"), md(buf.join("\n"))));
    } else if (tableAt(i)) {
      const head = cells(line), rows = []; i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) rows.push(cells(lines[i++]));
      out.append(h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, head.map(c => mdInline(c, h("th"))))),
        h("tbody", {}, rows.map(r => h("tr", {}, head.map((_, k) => mdInline(r[k] || "", h("td")))))))));
    } else if ((m = line.match(LIST))) {
      const ordered = /\d/.test(m[2]), base = m[1].length, list = h(ordered ? "ol" : "ul");
      if (ordered && parseInt(m[2], 10) !== 1) list.setAttribute("start", parseInt(m[2], 10));
      while (i < lines.length) {
        const mm = lines[i].match(LIST);
        if (!mm || mm[1].length < base || (mm[1].length === base && /\d/.test(mm[2]) !== ordered)) break;
        if (mm[1].length > base && list.lastChild) {      // a list inside the last item
          const ind = mm[1].length, buf = [];
          while (i < lines.length && lines[i].trim() && lines[i].match(/^\s*/)[0].length >= ind) buf.push(lines[i++].slice(ind));
          list.lastChild.append(md(buf.join("\n")));
          continue;
        }
        let txt = mm[3]; i++;
        while (i < lines.length && lines[i].trim() && !LIST.test(lines[i]) && /^\s{2,}\S/.test(lines[i])) txt += " " + lines[i++].trim();
        list.append(mdInline(txt, h("li")));
      }
      out.append(list);
    } else {
      const buf = [lines[i++]];
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*(```|~~~)|\s*>)/.test(lines[i]) && !LIST.test(lines[i]) && !tableAt(i)) buf.push(lines[i++]);
      const p = h("p");
      buf.forEach((l, k) => { if (k) p.append(h("br")); mdInline(l, p); });
      out.append(p);
    }
  }
  return out;
}

/* ---------- frame: sidebar, top bar, moving between screens ---------- */
const NAV = [["library", "chip"], ["create", "image"], ["tools", "toolbox"], ["devices", "devices"], ["learn", "book"], ["settings", "sliders"]];
function renderShell() {
  add(clear($("#side")),
    h("div", { class: "brand" }, sunMark("awake", 32), h("span", { class: "wordmark", text: "Datas" }),
      h("button", { class: "icon-btn drawer-close", "aria-label": t("close"), onclick: closeDrawer }, icon("close"))),
    h("div", { class: "ribbon", "aria-hidden": "true" }),
    h("div", { class: "side-actions" },
      h("button", { class: "btn sky grow", onclick: () => { Chat.fresh(); go("chat"); } }, icon("plus"), t("new_chat")),
      h("button", { class: "btn sky", "aria-label": t("new_chat_with"), title: t("new_chat_with"), onclick: e => Chat.aiMenu(e.currentTarget, true) }, icon("down"))),
    h("label", { class: "search" }, icon("search", 18),
      h("input", { id: "chatSearch", type: "search", placeholder: t("search_chats"), "aria-label": t("search_chats"), oninput: debounce(() => Chat.loadList(), 250) })),
    h("div", { id: "chatlist", class: "chatlist" }),
    h("nav", { class: "nav", "aria-label": t("sections") },
      NAV.map(([name, ic]) => h("button", { class: "nav-item", data: { go: name }, onclick: () => go(name) }, icon(ic), t("nav_" + name)))),
    h("div", { class: "side-foot", id: "sideFoot" }));
  renderFoot();
  Chat.loadList();
}
function renderFoot() {
  const foot = $("#sideFoot");
  if (!foot || !S.priv) return;
  if (isRemote()) {   // shown on a linked phone: say where things are
    add(clear(foot), icon("devices", 16), h("span", { text: t("remote_on", { device: S.status.remote.device }) }),
      h("div", { class: "remote-note" }, icon("lock", 16), h("span", { text: t(S.priv.memory_mode === "forget" ? "foot_forget" : "remote_kept", { device: S.status.remote.device }) })));
    return;
  }
  add(clear(foot), icon("lock", 16),
    h("button", { onclick: () => go("settings"), text: t(S.priv.memory_mode === "forget" ? "foot_forget" : "foot_remember") }));
}
function renderTop() {
  const top = clear($("#top"));
  top.append(h("button", { class: "icon-btn drawer-open", "aria-label": t("menu"), onclick: openDrawer }, icon("menu")));
  if (S.screen === "chat") Chat.renderTop(top);
  else top.append(h("h1", { class: "top-title", text: t("nav_" + S.screen) }), h("span", { class: "grow" }));
  top.append(h("button", { class: "icon-btn", id: "themeBtn", "aria-label": t("theme_toggle"), title: t("theme_toggle"),
    onclick: () => setTheme(isNight() ? "day" : "night") }, icon(isNight() ? "day" : "moon")));
}
const openDrawer = () => document.body.classList.add("drawer");
const closeDrawer = () => document.body.classList.remove("drawer");
function go(name, arg) {
  if (!SCREENS[name]) name = "chat";
  if (S.cleanup) { try { S.cleanup(); } catch (e) { /* screen already gone */ } S.cleanup = null; }
  S.screen = name;
  closeDrawer();
  document.querySelectorAll(".menu").forEach(m => m.remove());
  document.querySelectorAll(".nav-item").forEach(b => b.dataset.go === name ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  renderTop();
  const view = clear($("#view"));
  view.scrollTop = 0;
  const keep = fn => { if (typeof fn !== "function") return; if (S.screen === name) S.cleanup = fn; else fn(); };
  try {
    const r = SCREENS[name](view, arg);
    if (r && typeof r.then === "function") r.then(keep).catch(e => { view.append(h("div", { class: "wrap" }, h("p", { class: "note bad", text: e.message }))); });
    else keep(r);
  } catch (e) { view.append(h("div", { class: "wrap" }, h("p", { class: "note bad", text: e.message }))); }
}
window.go = go;

/* ---------- what the AI is doing right now ---------- */
function aiState() {
  const s = S.status;
  if (!s) return { state: "none", name: "" };
  if (s.provider && s.provider !== "local" && !String(s.provider).startsWith("pool")) {
    const name = String(s.provider).startsWith("link:") ? t("ai_on_device") : s.provider;
    return { state: "awake", name, remote: true };
  }
  if (s.server.running) return { state: "awake", name: s.server.model_name || s.model_id, vision: s.server.vision, starter: s.starter_active };
  if (s.can_wake) return { state: "asleep", name: s.last_model_name || "" };
  return { state: "none", name: "" };
}
async function refreshStatus() {
  try { S.status = await api("/api/status"); } catch (e) { return S.status; }
  S.priv = S.status.privacy;
  if (S.screen === "chat") Chat.syncTop();
  renderFoot();
  return S.status;
}
async function tick() {
  await refreshStatus();
  try {
    const n = (await api("/api/notice")).notice;
    if (n) {
      const text = n.kind === "fallback" ? t("notice_fallback", { lost: n.lost || t("a_device"), now: n.now })
        : n.kind === "fallback_none" ? t("notice_fallback_none", { lost: n.lost || t("a_device") })
        : n.kind === "engine_stopped" ? t("notice_engine_stopped") : n.text;
      toast(text, { ms: 14000, bad: n.kind === "fallback_none" });
      if (n.kind === "fallback") Chat.retryAfterFallback();
    }
  } catch (e) { /* the server is busy; ask again next time */ }
}

/* ---------- long tasks (downloads, starting an AI, updates): one card each, bottom right ---------- */
const Jobs = {
  track(job, opts = {}) {
    return new Promise(resolve => {
      const el = h("div", { class: "job", role: "status" });
      $("#jobs").append(el);
      let cur = job, open = false, timer = null;
      const finished = () => cur.state === "done" || cur.state === "error";
      const draw = () => {
        const phase = I18N.en["ph_" + cur.phase] ? t("ph_" + cur.phase) : "";
        const bytes = cur.total && cur.total > 5e6;
        add(clear(el),
          h("div", { class: "row nowrap" }, h("b", { class: "grow", text: opts.title || cur.title || "" }),
            finished() && h("button", { class: "icon-btn", "aria-label": t("close"), onclick: () => el.remove() }, icon("close", 16))),
          h("div", { class: "small muted", text: cur.state === "error" ? t("job_failed") + " " + (cur.error || "")
            : cur.state === "done" ? t("job_done")
            : [phase, cur.percent != null ? Math.round(cur.percent) + "%" : "", bytes ? gb(cur.done / 2 ** 30) + " / " + gb(cur.total / 2 ** 30) : ""].filter(Boolean).join("  ") || t("working") }),
          !finished() && h("div", { class: "bar" + (cur.percent == null ? " wait" : "") }, h("i", { style: `width:${cur.percent || 0}%` })),
          cur.phase === "model" && !finished() && h("div", { class: "small muted", text: t("job_keep_using") }),
          (cur.log || []).length > 0 && h("button", { class: "btn quiet small", style: "justify-self:start", onclick: () => { open = !open; draw(); } }, t(open ? "hide_details" : "details")),
          open && h("pre", { text: (cur.log || []).slice(-30).join("\n") }));
      };
      const step = async () => {
        try { cur = await api("/api/jobs/" + job.id); }
        catch (e) { cur = { ...cur, state: "error", error: e.message }; }
        draw();
        if (opts.onTick) opts.onTick(cur);
        if (cur.kind === "run" && cur.phase === "model" && !S.starterTold) {
          const st = await refreshStatus();
          if (st && st.starter_active) { S.starterTold = true; toast(t("starter_ready"), { ms: 9000 }); }
        }
        if (finished()) {
          clearInterval(timer);
          S.starterTold = false;
          if (cur.state === "done") setTimeout(() => el.remove(), 3500);
          await refreshStatus();
          resolve(cur);
        }
      };
      draw();
      timer = setInterval(step, 900);
    });
  },
};

/* ---------- first run and start ---------- */
function welcome() {
  let mode = "remember";
  const pick = h("div", { class: "stack" });
  const drawModes = () => add(clear(pick), ["remember", "forget"].map(m =>
    h("button", { class: "toggle-chip", style: "border-radius:14px;text-align:left;display:block;padding:12px 14px", "aria-pressed": String(mode === m), onclick: () => { mode = m; drawModes(); } },
      h("b", { text: t("mode_" + m) }), h("span", { class: "small muted", style: "display:block;font-weight:400", text: t("mode_" + m + "_hint") }))));
  drawModes();
  const langs = h("div", { class: "seg" }, [["en", "English"], ["es", "Español"]].map(([code, name]) =>
    h("button", { "aria-pressed": String(S.lang === code), onclick: async () => { S.lang = code; document.documentElement.lang = code; closeWelcome(); welcome(); } }, name)));
  const closeWelcome = openDialog({
    title: t("welcome_title"),
    body: [h("p", { text: t("welcome_text") }), langs, h("h3", { text: t("welcome_memory") }), pick,
      h("p", { class: "small muted", text: t("welcome_change_later") })],
    actions: close => h("button", { class: "btn primary", onclick: async () => {
      try { S.priv = await api("/api/privacy", { body: { memory_mode: mode, onboarded: true, lang: S.lang } }); } catch (e) { oops(e); }
      close(); await refreshStatus(); renderShell(); go("chat");
    } }, t("welcome_start")),
  });
}
async function hello() {
  try {
    const r = await api("/api/hello");
    if (r.upgraded_from) toast(t("hello_upgraded", { from: r.upgraded_from, to: r.version }), { ms: 9000 });
    else if (r.reinstalled && (r.models || r.chats)) toast(t("hello_kept", { models: r.models, chats: r.chats }), { ms: 9000 });
  } catch (e) { /* not important */ }
}
async function boot() {
  try { S.status = await api("/api/status"); }
  catch (e) { document.body.textContent = "Datas is not answering. Close it and open it again."; return; }
  S.lang = I18N[S.status.lang] ? S.status.lang : "en";
  S.priv = S.status.privacy;
  S.theme = S.status.theme || "auto";
  document.documentElement.lang = S.lang;
  applyTheme();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
  $("#scrim").addEventListener("click", closeDrawer);
  renderShell();
  Chat.fresh();
  go("chat");
  if (!S.priv.onboarded) welcome(); else hello();
  setInterval(tick, 6000);
  const asked = new URLSearchParams(location.search);
  if (asked.get("autorun")) autorun(asked.get("autorun"));
  if (asked.has("selfcheck")) selfcheck();
}
document.addEventListener("DOMContentLoaded", boot);

/* A desktop shortcut to one AI opens the window with ?autorun=<id>: start that AI. */
async function autorun(id) {
  try {
    const lib = await Chat.library(true);
    const it = lib.installed.find(x => x.model_id === id);
    const st = S.status;
    if (!it || (st.provider === "local" && st.server.running && st.server.model_id === id)) return;
    await Chat.runModel(it);
    await refreshStatus();
  } catch (e) { oops(e); }
}

/* The installer builds open the real window with ?selfcheck: the page walks through its
   screens and tells the local service what it saw (datas/desktop.py reads that report). */
async function selfcheck() {
  const errors = [];
  addEventListener("error", e => errors.push(String(e.message || e)));
  addEventListener("unhandledrejection", e => errors.push(String(e.reason)));
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const seen = { version: S.status.version, lang: S.lang, wordmark: ($("#side .wordmark") || {}).textContent || "",
    nav: document.querySelectorAll("#side .nav .nav-item").length,
    width: innerWidth, height: innerHeight, agent: navigator.userAgent, screens: {} };
  for (const name of ["chat", "learn", "setup", "devices", "tools", "settings", "about"]) {
    try {
      go(name);
      await wait(1500);
      seen.screens[name] = { parts: $("#view").children.length, heading: (($("#view h1") || {}).textContent || "").slice(0, 80), letters: $("#view").textContent.length,
        sections: document.querySelectorAll("#view .section").length,
        problems: [...document.querySelectorAll("#view .note.bad")].map(n => n.textContent.slice(0, 160)) };
    } catch (e) { errors.push(name + ": " + e); }
  }
  seen.errors = errors;
  try { await api("/api/selfcheck", { body: seen }); } catch (e) { /* no report is itself the finding */ }
}
