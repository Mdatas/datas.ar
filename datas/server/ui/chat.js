"use strict";
/* Datas window, part 2 — the chat: list of chats, choosing the AI and a helper, documents and
   pictures, the answer as it is written, and what you can do with it afterwards. */

const FORMATS = ["docx", "pdf", "xlsx", "pptx", "html", "md", "txt"];

const Chat = {
  cur: null, list: [], sending: false, abort: null, pendingImages: [], lastFailed: null,
  player: null, listening: false, levelTimer: null,

  fresh(helper) {
    Chat.stop();
    Chat.cur = { id: null, msgs: [], helper: helper || null, atts: [], model: "", modelName: "", provider: "", title: "",
      internet: !!(S.priv && S.priv.internet_default) };
    Chat.pendingImages = [];
    Chat.markList();
  },

  /* ---- helpers (ready-made roles) ---- */
  async helpers() {
    if (!S.helpers) {
      const r = await api("/api/assistants?lang=" + S.lang);
      let guide = {};
      try { guide = await api("/api/guide?lang=" + S.lang); } catch (e) { /* the guide still works */ }
      r.guide = { id: "guide", name: t("guide_name"), blurb: t("guide_blurb"), starters: guide.starters || [], export: [], custom: false };
      S.helpers = r;
    }
    return S.helpers;
  },
  async helperById(id) {
    if (!id) return null;
    const hs = await Chat.helpers();
    return id === "guide" ? hs.guide : hs.assistants.find(a => a.id === id) || null;
  },
  async library(fresh) {
    if (fresh || !S.library) S.library = await api("/api/library?lang=" + S.lang);
    return S.library;
  },

  /* ---- the list on the left ---- */
  groupOf(ts) {
    const day = d => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    const diff = Math.round((day(new Date()) - day(new Date(ts * 1000))) / 864e5);
    return t(diff <= 0 ? "today" : diff === 1 ? "yesterday" : diff < 7 ? "this_week" : diff < 31 ? "this_month" : "older");
  },
  async loadList() {
    const box = $("#chatlist");
    if (!box) return;
    const q = ($("#chatSearch") ? $("#chatSearch").value : "").trim();
    let r;
    try { r = await api("/api/chats" + (q ? "?q=" + encodeURIComponent(q) : "")); } catch (e) { return; }
    Chat.list = r.chats;
    clear(box);
    if (r.forget) { box.append(h("div", { class: "chat-empty", text: t("chats_forget") })); return; }
    if (!r.chats.length) { box.append(h("div", { class: "chat-empty", text: t(q ? "chats_none_found" : "chats_none") })); return; }
    let group = "";
    for (const c of r.chats) {
      const g = Chat.groupOf(c.updated);
      if (g !== group) { group = g; box.append(h("div", { class: "chat-group", text: g })); }
      box.append(h("div", { class: "chat-row", data: { id: c.id } },
        h("button", { class: "open", onclick: () => Chat.open(c.id) },
          h("span", { class: "ttl", text: c.title || t("untitled") }),
          h("span", { class: "sub", text: (q && c.snippet) || c.model_name || c.model || "" })),
        h("button", { class: "icon-btn", "aria-label": t("chat_options"), onclick: e => openMenu(e.currentTarget, [
          { label: t("rename"), icon: "edit", fn: () => Chat.rename(c) },
          { label: t("chat_learn"), icon: "spark", fn: () => Chat.learn(c) },
          { label: t("delete"), icon: "trash", danger: true, fn: () => Chat.remove(c) },
        ]) }, icon("more", 18))));
    }
    Chat.markList();
  },
  markList() {
    document.querySelectorAll("#chatlist .chat-row").forEach(r => r.classList.toggle("on", !!Chat.cur && r.dataset.id === Chat.cur.id));
  },
  async open(id) {
    Chat.stop();
    let c;
    try { c = await api("/api/chats/" + id); } catch (e) { oops(e); return; }
    Chat.cur = { id: c.id, msgs: c.messages || [], helper: await Chat.helperById(c.skill), atts: c.attachments || [],
      model: c.model || "", modelName: c.model_name || "", provider: c.provider || "", title: c.title || "",
      internet: !!(S.priv && S.priv.internet_default) };
    Chat.pendingImages = [];
    go("chat");
    Chat.markList();
  },
  async rename(c) {
    const title = await promptDialog(t("rename"), t("chat_name"), c.title || "");
    if (!title) return;
    try { await api("/api/chats/" + c.id, { method: "PATCH", body: { title } }); } catch (e) { oops(e); }
    if (Chat.cur && Chat.cur.id === c.id) Chat.cur.title = title;
    Chat.loadList();
  },
  /* The AI reads the chat and adds up to six short notes about the person to the notes file
     (Settings, "What the AI should remember about you"). Only things the person said. */
  async learn(c) {
    if (aiState().state !== "awake") { toast(t("chat_learn_need_ai"), { ms: 8000 }); return; }
    toast(t("chat_learn_working"), { ms: 4000 });
    try {
      const full = await api("/api/chats/" + c.id);
      const r = await api("/api/chat/learn", { body: { messages: full.messages || [] } });
      if (r.learned) toast(t("chat_learn_done", { n: r.learned }), { actions: [{ label: t("nav_settings"), fn: () => go("settings") }] });
      else toast(t("chat_learn_none"));
    } catch (e) { oops(e); }
  },
  async remove(c) {
    if (!await confirmDialog(t("delete_chat_title"), t("delete_chat_text", { name: c.title || t("untitled") }), t("delete"), true)) return;
    try { await api("/api/chats/" + c.id, { method: "DELETE" }); } catch (e) { oops(e); }
    if (Chat.cur && Chat.cur.id === c.id) { Chat.fresh(); if (S.screen === "chat") go("chat"); }
    Chat.loadList();
  },

  /* ---- top bar: which AI, which helper, internet for this chat ---- */
  renderTop(top) {
    top.append(
      h("button", { class: "pill", id: "aiPill", "aria-haspopup": "menu", onclick: e => Chat.aiMenu(e.currentTarget, false) }),
      h("button", { class: "pill", id: "helperPill", title: t("helper_title"), onclick: () => Chat.helperDialog() }),
      h("span", { class: "grow" }),
      h("button", { class: "pill", id: "netPill", title: t("net_hint"), onclick: () => Chat.toggleNet() }));
    Chat.syncTop();
  },
  syncTop() {
    const ai = $("#aiPill");
    if (!ai || !Chat.cur) return;
    const st = aiState();
    const label = st.state === "none" ? t("ai_none") : st.state === "asleep" ? t("ai_asleep", { name: st.name || t("ai_word") }) : st.name;
    add(clear(ai), sunMark(Chat.sending ? "busy" : st.state, 22), h("span", { text: label }), icon("down", 16));
    ai.title = t("ai_state_" + st.state);
    add(clear($("#helperPill")), icon("spark", 18), h("span", { text: Chat.cur.helper ? Chat.cur.helper.name : t("helper_none") }), icon("down", 16));
    const net = $("#netPill");
    net.className = "pill" + (Chat.cur.internet ? " on" : "");
    net.setAttribute("aria-pressed", String(Chat.cur.internet));
    add(clear(net), icon("globe", 18), h("span", { class: "wide-only", text: t(Chat.cur.internet ? "net_on" : "net_off") }));
  },
  toggleNet() {
    Chat.cur.internet = !Chat.cur.internet;
    Chat.syncTop();
    toast(t(Chat.cur.internet ? "net_on_note" : "net_off_note"), { ms: 6000 });
  },
  async aiMenu(anchor, forNewChat) {
    const items = [];
    let lib = { installed: [] }, prov = { providers: [], active: "local" }, link = { peers: [] };
    try { [lib, prov, link] = await Promise.all([Chat.library(true), api("/api/providers"), api("/api/link").catch(() => ({ peers: [] }))]); } catch (e) { /* show what we have */ }
    const st = S.status, after = () => { if (forNewChat) { Chat.fresh(); go("chat"); } else if (S.screen === "chat") { Chat.syncTop(); Chat.drawBanner(); Chat.drawFine(); } };
    items.push({ head: t("ai_here") });
    if (!lib.installed.length) items.push({ label: t("ai_none_installed"), disabled: true });
    for (const it of lib.installed) {
      const running = st.provider === "local" && st.server.running && st.server.model_id === it.model_id;
      items.push({ label: it.name, icon: sunMark(running ? "awake" : "none", 18),
        note: running ? t("ai_running") : (it.resources ? t("speed_" + it.resources.speed_class) : ""),
        fn: async () => { if (!running) await Chat.runModel(it); after(); } });
    }
    const remote = prov.providers.filter(p => p.kind !== "local" && p.kind !== "pool" && p.kind !== "linked");
    if (remote.length) items.push({ head: t("ai_paid") });
    for (const p of remote) {
      items.push({ label: p.name, icon: "globe", note: prov.active === p.name ? t("ai_in_use") : (p.model || t("ai_leaves_device")),
        fn: async () => { try { await api("/api/providers/active", { body: { name: p.name } }); await refreshStatus(); } catch (e) { oops(e); } after(); } });
    }
    const peers = (link.peers || []).filter(p => p.online && p.ai && p.ai.name);
    if (peers.length) items.push({ head: t("ai_other_devices") });
    for (const p of peers) {
      items.push({ label: p.ai.name, icon: "devices", note: t("ai_on", { device: p.name }) + (p.in_use ? " — " + t("ai_in_use") : ""),
        fn: async () => { try { await api("/api/link/use/" + p.id, { method: "POST" }); await refreshStatus(); } catch (e) { oops(e); } after(); } });
    }
    items.push("hr", { label: t("nav_setup"), icon: "plus", fn: () => go("setup") });
    if (st.server.running) items.push({ label: t("ai_sleep_now"), icon: "moon", fn: async () => { try { await api("/api/stop", { method: "POST" }); await refreshStatus(); } catch (e) { oops(e); } } });
    openMenu(anchor, items);
  },
  /* "Try this AI instead": a faster one, or one that can do what this one cannot — always one
     that fits this device (/api/suggest); or a plain "none fits" */
  async offerAI(need) {
    try {
      const r = await api("/api/suggest?" + new URLSearchParams({ need, model: S.status.model_id || "" }));
      if (r.ok) return;
      const v = { name: r.name, size: r.gib ? gb(r.gib) : "" };
      const say = r.none
        ? { faster: () => t("sug_none_faster"), vision: () => t("sug_none_vision"), tools: () => t("sug_none_tools") }
        : { faster: () => t("sug_faster", v), vision: () => t("sug_vision", v), tools: () => t("sug_tools", v) };
      const go = { model_id: r.model_id, quant: r.quant, name: r.name, capabilities: need === "vision" ? ["vision"] : [] };
      toast((say[need] || say.faster)(), { ms: 20000, actions: r.none ? [] : [{ label: r.installed ? t("sug_switch") : t("sug_get", v), fn: () => Chat.runModel(go) }] });
    } catch (e) { /* a suggestion is never worth an error */ }
  },
  async runModel(it) {
    try {
      const st = S.status;
      if (st.provider !== "local") await api("/api/providers/active", { body: { name: "local" } });
      const custom = it.custom || String(it.model_id).startsWith("custom:");
      const job = custom
        ? await api("/api/run-custom", { body: { path: it.path || String(it.model_id).slice(7), context: st.context } })
        : await api("/api/run", { body: { model_id: it.model_id, quant: it.quant, context: st.context, kv_bits: 16, pool: !!S.pool,
            with_vision: (it.capabilities || []).includes("vision") || String(st.use_cases || "").includes("images"), with_voice: false, starter: true } });
      S.getting = it.name;
      if (S.screen === "chat" && !Chat.cur.msgs.length) Chat.draw();
      const done = await Jobs.track(job, { title: it.name });
      S.getting = null;
      S.library = null;
      if (S.screen === "chat") { Chat.syncTop(); if (!Chat.cur.msgs.length) Chat.draw(); }
      return done;
    } catch (e) { S.getting = null; oops(e); return null; }
  },

  /* ---- the screen ---- */
  screen(view) {
    if (!Chat.cur) Chat.fresh();
    const root = h("div", { class: "chat" },
      h("div", { class: "msgs", id: "msgs" }, h("div", { id: "chatBanner" }), h("div", { class: "msgs-inner", id: "msgList" })),
      h("div", { class: "composer-wrap" },
        h("div", { class: "composer" },
          h("div", { class: "attach-chips", id: "attChips" }),
          h("textarea", { id: "box", rows: "1", placeholder: t("box_placeholder"), "aria-label": t("box_placeholder"),
            oninput: Chat.grow, onpaste: Chat.onPaste,
            onkeydown: e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); Chat.send(); } } }),
          h("div", { class: "composer-bar" },
            h("button", { class: "icon-btn", "aria-label": t("attach"), title: t("attach"), onclick: () => $("#filePick").click() }, icon("clip")),
            h("input", { type: "file", id: "filePick", class: "hidden", multiple: true, onchange: e => { Chat.attach([...e.target.files]); e.target.value = ""; } }),
            !isRemote() && h("button", { class: "icon-btn", id: "camBtn", "aria-label": t("cam_add"), title: t("cam_add"), onclick: e => Chat.cameraMenu(e.currentTarget) }, icon("camera")),
            !isRemote() && h("button", { class: "icon-btn", id: "micBtn", "aria-label": t("mic"), title: t("mic"), onclick: Chat.mic }, icon("mic")),
            h("span", { class: "grow" }),
            h("button", { class: "btn primary", id: "sendBtn", onclick: () => (Chat.sending ? Chat.stop() : Chat.send()) }))),
        h("div", { class: "fineprint", id: "fine" })));
    root.addEventListener("dragover", e => { e.preventDefault(); root.classList.add("dropping"); });
    root.addEventListener("dragleave", () => root.classList.remove("dropping"));
    root.addEventListener("drop", e => { e.preventDefault(); root.classList.remove("dropping"); if (e.dataTransfer.files.length) Chat.attach([...e.dataTransfer.files]); });
    view.append(root);
    Chat.setSending(false);
    Chat.draw();
    $("#box").focus();
  },
  grow() {
    const b = $("#box");
    if (!b) return;
    b.style.height = "auto";
    b.style.height = Math.min(b.scrollHeight, innerHeight * 0.38) + "px";
  },
  onPaste(e) {
    const files = [...(e.clipboardData ? e.clipboardData.files : [])];
    if (files.length) { e.preventDefault(); Chat.attach(files); }
  },
  toBottom(force) {
    const m = $("#msgs");
    if (m && (force || m.scrollHeight - m.scrollTop - m.clientHeight < 160)) m.scrollTop = m.scrollHeight;
  },
  setSending(on) {
    Chat.sending = on;
    const b = $("#sendBtn");
    if (b) { add(clear(b), icon(on ? "stop" : "send", 18), h("span", { text: t(on ? "stop" : "send") })); b.classList.toggle("primary", !on); }
    Chat.syncTop();
  },
  stop() { if (Chat.abort) Chat.abort.abort(); },
  textOf(c) { return Array.isArray(c) ? c.filter(p => p.type === "text").map(p => p.text).join("\n") : String(c || ""); },
  firstWords() { const m = Chat.cur.msgs.find(x => x.role === "user"); return m ? Chat.textOf(m.content).slice(0, 60) : ""; },

  draw() {
    const list = $("#msgList");
    if (!list) return;
    clear(list);
    Chat.drawChips(); Chat.drawBanner(); Chat.drawFine();
    if (!Chat.cur.msgs.length) { Chat.drawEmpty(list); return; }
    for (const m of Chat.cur.msgs) list.append(Chat.msgNode(m));
    Chat.toBottom(true);
  },
  msgNode(m) {
    if (m.role === "user") {
      const el = h("div", { class: "msg user" });
      if (Array.isArray(m.content)) {
        for (const p of m.content) {
          if (p.type === "text") el.append(p.text);
          else if (p.type === "image_url" && p.image_url) el.append(h("img", { src: p.image_url.url, alt: t("picture") }));
        }
      } else el.append(String(m.content || ""));
      return el;
    }
    if (m.role !== "assistant") return h("div", { class: "hidden" });
    const text = Chat.textOf(m.content);
    return h("div", { class: "msg ai" }, sunMark("awake", 26), h("div", {}, h("div", { class: "md" }, md(text)), Chat.actions(text)));
  },
  actions(text) {
    return h("div", { class: "msg-actions" },
      h("button", { class: "btn quiet", onclick: () => copyText(text) }, icon("copy", 16), t("copy")),
      h("button", { class: "btn quiet", onclick: () => Chat.speak(text) }, icon("speaker", 16), t("read_aloud")),
      h("button", { class: "btn quiet", onclick: e => Chat.exportMenu(e.currentTarget, text) }, icon("save", 16), t("save_as")));
  },
  exportMenu(anchor, text) {
    const pref = (Chat.cur.helper && Chat.cur.helper.export) || [];
    const order = [...FORMATS].sort((a, b) => Number(pref.includes(b)) - Number(pref.includes(a)));
    openMenu(anchor, [{ head: t("save_where") }, ...order.map(f => ({ label: t("fmt_" + f), icon: "doc", note: pref.includes(f) ? t("fmt_suggested") : "", fn: () => Chat.exportAs(text, f) })),
      ...(isRemote() ? [] : ["hr", { label: t("print_paper"), icon: "printer", fn: () => Chat.print(text) }])]);
  },
  async exportAs(text, format) {
    try { savedToast(await api("/api/export", { body: { markdown: text, format, title: Chat.cur.title || Chat.firstWords(), lang: S.lang } })); }
    catch (e) { oops(e); }
  },
  async speak(text) {
    if (Chat.player) { Chat.player.pause(); Chat.player = null; return; }
    if (!S.status.voice.installed.tts) { toast(t("voice_missing"), { actions: [{ label: t("voice_get"), fn: () => go("settings") }] }); return; }
    try {
      const r = await fetch("/api/voice/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: text.slice(0, 3000), lang: S.lang }) });
      if (!r.ok) throw new Error((await r.text()).slice(0, 200));
      const url = URL.createObjectURL(await r.blob()), a = new Audio(url);
      Chat.player = a;
      a.onended = () => { URL.revokeObjectURL(url); if (Chat.player === a) Chat.player = null; };
      await a.play();
      toast(t("reading"), { ms: 2500 });
    } catch (e) { Chat.player = null; oops(e); }
  },
  drawFine() {
    const f = $("#fine");
    if (!f) return;
    const st = aiState();
    const far = isRemote() && S.status.remote.device;   // this window shows the Datas of another device of the person
    f.textContent = st.remote ? t("fine_remote", { name: st.name })
      : far ? t(Chat.cur.internet ? "fine_far_net" : "fine_far", { device: far })
      : t(Chat.cur.internet ? "fine_local_net" : "fine_local");
  },
  drawChips() {
    const box = $("#attChips");
    if (!box) return;
    clear(box);
    Chat.cur.atts.forEach((a, k) => box.append(h("span", { class: "chip" }, icon("doc", 15), a.name,
      h("button", { "aria-label": t("remove_name", { name: a.name }), onclick: () => { Chat.cur.atts.splice(k, 1); Chat.drawChips(); } }, "×"))));
    Chat.pendingImages.forEach((u, k) => box.append(h("span", { class: "chip" }, h("img", { src: u, alt: t("picture") }),
      h("button", { "aria-label": t("remove_name", { name: t("picture") }), onclick: () => { Chat.pendingImages.splice(k, 1); Chat.drawChips(); } }, "×"))));
  },
  async drawBanner() {
    const b = $("#chatBanner");
    if (!b) return;
    clear(b);
    const c = Chat.cur, st = S.status, box = $("#box");
    const closer = key => h("button", { class: "icon-btn", "aria-label": t("close"), title: t("close"), onclick: () => { S.closedBanners[key] = true; clear(b); } }, icon("close", 16));
    const asleep = aiState().state === "asleep";
    if (box) box.placeholder = asleep ? t("box_placeholder_wake") : t("box_placeholder");
    if (asleep && !S.closedBanners.wake) {
      b.append(h("div", { class: "banner note row" }, sunMark("asleep", 18),
        h("span", { class: "grow", text: t("banner_wake", { name: aiState().name || t("the_ai") }) }), closer("wake")));
      return;
    }
    if (S.closedBanners["other:" + c.id] || !c.id || !c.model || (c.provider || "local") !== "local" || st.provider !== "local" || !st.server.running || st.server.model_id === c.model) return;
    let lib;
    try { lib = await Chat.library(); } catch (e) { return; }
    const it = lib.installed.find(x => x.model_id === c.model);
    if (!it || Chat.cur !== c) return;
    b.append(h("div", { class: "banner note row" },
      h("span", { class: "grow", text: t("banner_other_ai", { name: c.modelName || it.name, now: st.server.model_name }) }),
      h("button", { class: "btn small", onclick: async () => { await Chat.runModel(it); Chat.drawBanner(); } }, t("banner_switch", { name: it.name })), closer("other:" + c.id)));
  },
  async drawEmpty(list) {
    const cur = Chat.cur, st = aiState(), helper = cur.helper;
    const box = h("div", { class: "empty" });
    list.append(box);
    const guide = helper && helper.id === "guide";
    if (st.state === "none" && !guide) {
      if (S.getting) box.append(h("h1", { text: t("getting_title", { name: S.getting }) }), h("p", { class: "lead", style: "margin:0", text: t("getting_lead") }));
      else await Chat.drawGetAi(box);
      if (Chat.cur !== cur) return;
      box.append(h("div", { class: "row" },
        h("button", { class: "btn quiet", onclick: async () => { cur.helper = (await Chat.helpers()).guide; Chat.draw(); Chat.syncTop(); } }, icon("info", 18), t("ask_guide")),
        h("button", { class: "btn quiet", onclick: () => go("learn") }, icon("book", 18), t("learn_first"))));
      return;
    }
    box.append(h("h1", { text: helper ? helper.name : t("empty_title") }),
      h("p", { class: "lead", style: "margin:0", text: helper ? helper.blurb : t("empty_lead") }));
    const starters = helper && helper.starters && helper.starters.length ? helper.starters : [1, 2, 3, 4].map(k => t("starter_" + k));
    box.append(h("div", { class: "starters" }, starters.slice(0, 4).map(s => h("button", { onclick: () => Chat.send(s) }, s))));
    if (!helper) {
      box.append(h("div", { class: "row" },
        h("button", { class: "btn sky", onclick: () => Chat.helperDialog() }, icon("spark", 18), t("helper_browse")),
        h("button", { class: "btn quiet", onclick: async () => { cur.helper = (await Chat.helpers()).guide; Chat.draw(); Chat.syncTop(); } }, t("ask_guide"))));
    } else if (helper.web && !cur.internet) {
      box.append(h("p", { class: "small muted", text: t("helper_web_hint") }));
    }
  },
  async drawGetAi(box) {
    box.append(h("h1", { text: t("get_title") }));
    let lib = { installed: [] };
    try { lib = await Chat.library(); } catch (e) { /* show the recommendation */ }
    if (lib.installed.length) {
      box.append(h("p", { class: "lead", style: "margin:0", text: t("get_installed_lead") }),
        h("div", { class: "row" }, lib.installed.slice(0, 4).map((it, k) =>
          h("button", { class: "btn" + (k ? "" : " primary"), onclick: () => Chat.runModel(it) }, k ? it.name : t("start_name", { name: it.name })))));
      return;
    }
    box.append(h("p", { class: "lead", style: "margin:0", text: t("get_lead") }));
    const hero = h("div", { class: "hero" }, spinner());
    box.append(hero);
    try {
      const rec = await api("/api/recommend?" + new URLSearchParams({ use: S.status.use_cases || "text", mode: S.status.resource_mode || "balanced" }));
      clear(hero);
      const d = rec.default;
      if (!d) {
        add(hero, h("h2", { text: t("get_none_title") }), h("p", { text: t("get_none_text") }),
          h("div", { class: "row" }, h("button", { class: "btn primary", onclick: () => go("setup") }, t("see_options")),
            h("button", { class: "btn", onclick: () => go("devices") }, t("nav_devices"))));
        return;
      }
      add(hero, h("div", { class: "small muted", text: t("get_recommended") }),
        h("div", { class: "row nowrap" }, sunMark("awake", 34), h("h2", { class: "grow", text: d.name }), speedChip(d)),
        h("p", { text: t("speedl_" + d.speed_class) }), h("p", { class: "muted", text: t("dl_line", { size: gb(d.weights_gib) }) }),
        h("div", { class: "row" },
          h("button", { class: "btn primary", onclick: () => Chat.runModel(d) }, icon("save", 18), t("get_this")),
          h("button", { class: "btn quiet", onclick: () => go("setup") }, t("see_options"))),
        h("p", { class: "small muted", text: t("get_note") }));
    } catch (e) { add(clear(hero), h("p", { class: "note bad", text: e.message })); }
  },

  /* ---- sending ---- */
  async send(given) {
    if (Chat.sending) return;
    const box = $("#box"), c = Chat.cur, helper = c.helper;
    const text = (given != null ? given : box.value).trim(), imgs = Chat.pendingImages;
    if (!text && !imgs.length) return;
    const st = aiState();
    if (st.state === "none" && !(helper && helper.id === "guide")) {
      if (given != null) { box.value = given; Chat.grow(); }
      toast(t("no_ai"), { actions: [{ label: t("nav_setup"), fn: () => go("setup") }] });
      return;
    }
    if (given == null) { box.value = ""; Chat.grow(); }
    const content = imgs.length ? [{ type: "text", text }, ...imgs.map(u => ({ type: "image_url", image_url: { url: u } }))] : text;
    Chat.pendingImages = [];
    Chat.drawChips();
    c.msgs.push({ role: "user", content });
    const list = $("#msgList");
    if (c.msgs.length === 1) clear(list);
    const asked = Chat.msgNode(c.msgs[c.msgs.length - 1]);
    const body = h("div", { class: "md" }), think = h("div", { class: "think hidden" }), notes = h("div", {});
    const holder = h("div", {}, notes, think, body), node = h("div", { class: "msg ai" }, sunMark("busy", 26), holder);
    list.append(asked, node);
    Chat.toBottom(true);
    Chat.setSending(true);
    let full = "", thinking = "", failed = "", raf = 0, firstAt = 0;
    const paint = () => { raf = 0; body.replaceChildren(md(full)); Chat.toBottom(); };
    Chat.abort = new AbortController();
    if (st.state === "asleep") notes.append(h("div", { class: "toolnote" }, t("waking")));
    try {
      const r = await fetch("/api/chat", { method: "POST", signal: Chat.abort.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: c.msgs, internet: c.internet, assistant: helper ? helper.id : null, attachments: c.atts, lang: S.lang, chat_id: c.id }) });
      if (!r.ok) {
        let j = {};
        try { j = await r.json(); } catch (e) { /* not JSON */ }
        failed = j.error === "no_model" ? t("no_ai") : (j.message || (typeof j.detail === "string" ? j.detail : "") || r.statusText || "HTTP " + r.status);
      } else {
        clear(notes);
        const rd = r.body.getReader(), dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await rd.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let k;
          while ((k = buf.indexOf("\n\n")) >= 0) {
            const line = buf.slice(0, k).split("\n").find(l => l.startsWith("data:"));
            buf = buf.slice(k + 2);
            if (!line) continue;
            let ev;
            try { ev = JSON.parse(line.slice(5)); } catch (e) { continue; }
            if (ev.type === "token") { if (!firstAt) firstAt = performance.now(); full += ev.text; if (!raf) raf = requestAnimationFrame(paint); }
            else if (ev.type === "thinking") { thinking += ev.text; think.classList.remove("hidden"); think.textContent = thinking.slice(-320); }
            else if (ev.type === "tool") notes.append(h("div", { class: "toolnote" }, icon("globe", 16), t("looking_up") + " " + ((ev.args && (ev.args.query || ev.args.url)) || "")));
            else if (ev.type === "error") failed = ev.message;
          }
        }
      }
    } catch (e) { if (e.name !== "AbortError") failed = e.message; }
    if (raf) cancelAnimationFrame(raf);
    think.classList.add("hidden");
    Chat.abort = null;
    Chat.setSending(false);
    if (Chat.cur !== c) return;                 // the person moved to another chat meanwhile
    if (full) {
      // slow answers (under ~2 words a second over a real answer): offer a faster AI, once
      const secs = firstAt ? (performance.now() - firstAt) / 1000 : 0, words = full.split(/\s+/).length;
      if (secs > 6 && words / secs < 2 && !S.offeredFaster && !aiState().remote) { S.offeredFaster = true; Chat.offerAI("faster"); }
      c.msgs.push({ role: "assistant", content: full });
      node.replaceChild(sunMark("awake", 26), node.firstChild);
      body.replaceChildren(md(full));
      holder.append(Chat.actions(full));
      Chat.lastFailed = null;
      if (failed) toast(failed, { bad: true });
      await Chat.save();
      if (S.status.voice && S.status.voice.speak_answers && S.status.voice.installed.tts) Chat.speak(full);
    } else {                                     // nothing came back: give the question back
      c.msgs.pop();
      node.remove(); asked.remove();
      Chat.lastFailed = { content, at: Date.now() };
      if (typeof content === "string") { box.value = content; Chat.grow(); } else { Chat.pendingImages = imgs; box.value = text; Chat.drawChips(); }
      if (!c.msgs.length) Chat.draw();
      if (failed) toast(failed, { bad: true, ms: 10000 });
      if (/memory|memoria|out of mem|alloc/i.test(failed || "") && !aiState().remote) Chat.offerAI("faster");
    }
    Chat.toBottom();
    refreshStatus();
  },
  retryAfterFallback() {
    const f = Chat.lastFailed;
    if (f && !Chat.sending && Date.now() - f.at < 120000 && S.screen === "chat" && typeof f.content === "string") { $("#box").value = ""; Chat.send(f.content); }
  },
  async save() {
    const c = Chat.cur, st = S.status;
    if (S.priv && S.priv.memory_mode === "forget") return;
    try {
      const local = st.provider === "local" && st.server.running;
      const r = await api("/api/chats", { body: { chat_id: c.id, messages: c.msgs, model: local ? (st.server.model_id || "") : "",
        model_name: aiState().name || "", skill: c.helper ? c.helper.id : null, attachments: c.atts, provider: st.provider } });
      c.id = r.chat_id;
      if (local) { c.model = st.server.model_id || c.model; c.modelName = st.server.model_name || c.modelName; }
      c.provider = st.provider;
      await Chat.loadList();
    } catch (e) { /* the chat stays on screen; saving is tried again with the next answer */ }
  },

  /* ---- documents, pictures, voice ---- */
  async shrink(file) {
    try {
      const url = URL.createObjectURL(file), img = new Image();
      await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
      const k = Math.min(1, 1280 / Math.max(img.width, img.height));
      const cv = h("canvas", { width: Math.round(img.width * k), height: Math.round(img.height * k) });
      cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
      URL.revokeObjectURL(url);
      return cv.toDataURL("image/jpeg", 0.86);
    } catch (e) { return fileDataUrl(file); }
  },
  async attach(files) {
    for (const f of files) {
      try {
        if (f.type.startsWith("image/")) {
          const st = aiState();
          if (!st.vision && !st.remote) { toast(t("no_vision")); Chat.offerAI("vision"); continue; }
          Chat.pendingImages.push(await Chat.shrink(f));
        } else {
          const r = await api("/api/docs/extract", { body: { name: f.name, content_base64: await fileBase64(f) } });
          Chat.cur.atts = Chat.cur.atts.filter(a => a.name !== r.name).concat([{ name: r.name, text: r.text }]);
          if (r.truncated) toast(t("doc_truncated", { name: r.name }));
        }
      } catch (e) { toast(t("attach_failed", { name: f.name }) + " " + e.message, { bad: true }); }
      Chat.drawChips();
    }
    const b = $("#box");
    if (b) b.focus();
  },
  /* a photo from the camera or a picture of the screen, added like any other picture */
  cameraMenu(anchor) {
    openMenu(anchor, [
      { label: t("cam_photo"), icon: "camera", fn: () => Chat.snap("camera") },
      { label: t("cam_screen"), icon: "screen", fn: () => Chat.snap("screen") },
    ]);
  },
  async snap(kind) {
    const st = aiState(), btn = $("#camBtn");
    if (!st.vision && !st.remote) { toast(t("no_vision")); Chat.offerAI("vision"); return; }
    if (btn) btn.disabled = true;
    try {
      const r = kind === "camera" ? await Things.photo() : await Things.screen(true);
      if (r) { Chat.pendingImages.push(r.image); Chat.drawChips(); }
    } catch (e) { oops(e); }
    if (btn) btn.disabled = false;
    const b = $("#box");
    if (b) b.focus();
  },
  async print(text) {
    try { toast((await api("/api/things/print", { body: { markdown: text, title: Chat.cur.title || Chat.firstWords(), lang: S.lang } })).said); }
    catch (e) { oops(e); }
  },
  async mic() {
    const v = S.status.voice, btn = $("#micBtn");
    if (!Chat.listening) {
      if (!v.available.stt || !v.available.mic) { toast(t("mic_unavailable")); return; }
      if (!(v.installed.stt_models || []).length) { toast(t("voice_missing"), { actions: [{ label: t("voice_get"), fn: () => go("settings") }] }); return; }
      try { await api("/api/voice/listen/start", { method: "POST" }); } catch (e) { oops(e); return; }
      Chat.listening = true;
      btn.classList.add("on-air"); btn.title = t("mic_stop");
      Chat.levelTimer = setInterval(async () => {
        try { const l = await api("/api/voice/listen/level"); btn.style.boxShadow = `0 0 0 ${Math.round((l.level || 0) * 9)}px var(--bad-soft)`; } catch (e) { /* keep listening */ }
      }, 250);
      return;
    }
    clearInterval(Chat.levelTimer);
    btn.style.boxShadow = ""; btn.classList.remove("on-air"); btn.disabled = true;
    try {
      const r = await api("/api/voice/listen/stop", { body: { lang: S.lang } });
      if (r.text) {
        const box = $("#box"), was = box.value.trim();
        box.value = (was ? was + " " : "") + r.text;
        Chat.grow();
        if (!was) Chat.send();
      }
    } catch (e) { oops(e); }
    Chat.listening = false; btn.disabled = false; btn.title = t("mic");
  },

  /* ---- choosing or making a helper ---- */
  async helperDialog() {
    let hs;
    try { hs = await Chat.helpers(); } catch (e) { oops(e); return; }
    const listBox = h("div", {}), search = h("input", { type: "search", placeholder: t("helper_search"), "aria-label": t("helper_search") });
    let close = () => {};
    const choose = a => {
      Chat.cur.helper = a;
      close();
      if (S.screen !== "chat") go("chat"); else { Chat.syncTop(); if (!Chat.cur.msgs.length) Chat.draw(); }
    };
    const row = (a, extra) => h("div", { class: "chat-row" },
      h("button", { class: "open", onclick: () => choose(a) },
        h("span", { class: "ttl", text: a ? a.name : t("helper_none") }),
        h("span", { class: "sub", style: "white-space:normal", text: a ? a.blurb : t("helper_none_hint") })), extra);
    const draw = () => {
      const q = search.value.trim().toLowerCase(), hit = a => !q || (a.name + " " + a.blurb).toLowerCase().includes(q);
      clear(listBox);
      if (!q) listBox.append(row(null), row(hs.guide));
      for (const cat of hs.categories) {
        const items = hs.assistants.filter(a => a.cat === cat.id && hit(a));
        if (!items.length) continue;
        listBox.append(h("div", { class: "chat-group", text: cat.name }));
        for (const a of items) {
          listBox.append(row(a, a.custom && h("button", { class: "icon-btn", "aria-label": t("edit"), onclick: () => { close(); Chat.helperEditor(a.id); } }, icon("edit", 18))));
        }
      }
      if (!listBox.children.length) listBox.append(h("p", { class: "muted", text: t("helper_none_found") }));
    };
    search.addEventListener("input", draw);
    close = openDialog({
      title: t("helper_title"), wide: true,
      body: [h("p", { class: "muted", text: t("helper_lead") }), search, listBox],
      actions: c => h("button", { class: "btn", onclick: () => { c(); Chat.helperEditor(null); } }, icon("plus", 18), t("helper_make")),
    });
    draw();
  },
  async helperEditor(id) {
    let a = { name: "", blurb: "", prompt: "", starters: [], docs: [] };
    if (id) { try { a = await api("/api/assistants/" + id + "?lang=" + S.lang); } catch (e) { oops(e); return; } }
    const name = h("input", { type: "text", value: a.name, maxlength: "60" });
    const prompt = h("textarea", { rows: "6", placeholder: t("he_prompt_example") }); prompt.value = a.prompt || "";
    const blurb = h("input", { type: "text", value: a.blurb || "", maxlength: "140" });
    const starters = h("textarea", { rows: "3" }); starters.value = (a.starters || []).join("\n");
    const files = h("input", { type: "file", multiple: true });
    const docs = h("div", { class: "attach-chips" });
    const drawDocs = () => add(clear(docs), (a.docs || []).map(d => {
      const n = typeof d === "string" ? d : d.name;
      return h("span", { class: "chip" }, icon("doc", 15), n, h("button", { "aria-label": t("remove_name", { name: n }), onclick: async () => {
        try { await api("/api/assistants/" + id + "/docs/" + encodeURIComponent(n), { method: "DELETE" }); a.docs = a.docs.filter(x => (typeof x === "string" ? x : x.name) !== n); drawDocs(); } catch (e) { oops(e); }
      } }, "×"));
    }));
    drawDocs();
    openDialog({
      title: t(id ? "he_edit" : "helper_make"), wide: true,
      body: [
        h("label", { class: "field" }, t("he_name"), name),
        h("label", { class: "field" }, t("he_prompt"), h("span", { class: "hint", text: t("he_prompt_hint") }), prompt),
        h("label", { class: "field" }, t("he_blurb"), blurb),
        h("label", { class: "field" }, t("he_starters"), h("span", { class: "hint", text: t("he_starters_hint") }), starters),
        h("label", { class: "field" }, t("he_docs"), h("span", { class: "hint", text: t("he_docs_hint") }), docs, files),
      ],
      actions: close => [
        id && h("button", { class: "btn danger", onclick: async () => {
          if (!await confirmDialog(t("delete"), t("he_delete_text", { name: a.name }), t("delete"), true)) return;
          try { await api("/api/assistants/" + id, { method: "DELETE" }); } catch (e) { oops(e); }
          S.helpers = null; if (Chat.cur.helper && Chat.cur.helper.id === id) { Chat.cur.helper = null; Chat.syncTop(); }
          close();
        } }, t("delete")),
        h("button", { class: "btn", onclick: close }, t("cancel")),
        h("button", { class: "btn primary", onclick: async () => {
          if (!name.value.trim() || !prompt.value.trim()) { toast(t("he_need")); return; }
          try {
            const saved = await api("/api/assistants", { body: { id: id || null, name: name.value.trim(), prompt: prompt.value.trim(), blurb: blurb.value.trim(),
              starters: starters.value.split("\n").map(s => s.trim()).filter(Boolean).slice(0, 4), export: a.export || [] } });
            for (const f of files.files) await api("/api/assistants/" + saved.id + "/docs", { body: { name: f.name, content_base64: await fileBase64(f) } });
            S.helpers = null;
            Chat.cur.helper = await Chat.helperById(saved.id);
            close();
            if (S.screen !== "chat") go("chat"); else { Chat.syncTop(); if (!Chat.cur.msgs.length) Chat.draw(); }
          } catch (e) { oops(e); }
        } }, t("save")),
      ],
    });
  },
};

function speedChip(c) {
  const fits = c.fits !== false && c.fit_level !== "none";
  const cls = !fits ? "no" : (c.speed_class === "ok" || c.speed_class === "fast" ? "ok" : "slow");
  const key = !fits ? "speed_nofit" : "speed_" + c.speed_class;
  return h("span", { class: "chip " + cls, text: I18N.en[key] ? t(key) : c.speed_class });
}

SCREENS.chat = view => Chat.screen(view);
