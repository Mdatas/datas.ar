"use strict";
/* Datas window, part 3 — the other screens: adding an AI, My AIs, Create, Tools, Devices,
   Learn, Settings and About. */

function page(view, title, lead) {
  const wrap = h("div", { class: "wrap" }, h("h1", { class: "title", text: title }), lead && h("p", { class: "lead", text: lead }));
  view.append(wrap);
  return wrap;
}
const sec = (title, sub, ...kids) => h("section", { class: "section" }, h("h2", { text: title }), sub && h("p", { class: "sub", text: sub }), kids);
function seg(options, value, onpick) {
  const el = h("div", { class: "seg", role: "group" });
  const draw = v => add(clear(el), options.map(([val, label]) => h("button", { "aria-pressed": String(val === v), onclick: () => { draw(val); onpick(val); } }, label)));
  draw(value);
  return el;
}
function switchRow(label, hint, checked, onchange, disabled) {
  const input = h("input", { type: "checkbox", role: "switch", checked: !!checked, disabled: !!disabled });
  input.addEventListener("change", () => onchange(input.checked, input));
  return h("label", { class: "switch" }, input, h("span", {}, h("b", { text: label }), hint && h("span", { class: "hint", text: hint })));
}
const more = (label, ...kids) => h("details", { class: "more" }, h("summary", { text: label }), h("div", {}, kids));
const kv = pairs => h("dl", { class: "kv" }, pairs.filter(p => p && p[1]).map(([k, v]) => [h("dt", { text: k }), h("dd", {}, v)]));
const verdictChip = v => h("span", { class: "chip " + ({ yes: "ok", slow: "slow", no: "no" }[v] || "plain"), text: t("verdict_" + (I18N.en["verdict_" + v] ? v : "no")) });
const guard = fn => async (...a) => { try { await fn(...a); } catch (e) { oops(e); } };

/* ======================= Add an AI ======================= */
function modelFacts(c) {
  const p = c.plain || {};
  return kv([
    [t("f_where"), t("where_" + c.placement)], [t("f_memory"), t("mem_line", { size: gb(c.needed_gib) })],
    [t("f_download"), t("dl_line", { size: gb(c.weights_gib) })], [t("f_limits"), p.limits],
    [t("f_like"), p.comparable && [p.comparable.verdict, h("div", { class: "small muted", text: p.comparable.disclaimer || "" })]],
    [t("f_maker"), p.maker && (p.maker_url ? extLink(p.maker, p.maker_url) : p.maker)], [t("f_licence"), p.license],
    [t("f_kind"), t(c.arch === "moe" ? "arch_moe" : "arch_dense")], [t("f_variant"), c.finetune_of && t("variant_of", { name: c.finetune_of })],
    [t("f_page"), p.model_page && extLink(t("open_page"), p.model_page)],
  ]);
}
SCREENS.setup = async view => {
  const wrap = page(view, t("setup_title"), t("setup_lead"));
  const uses = new Set(String(S.status.use_cases || "text").split(",").filter(Boolean));
  uses.add("text");
  let mode = S.status.resource_mode || "balanced", ctx = S.status.context || 8192, lib = { installed: [] };
  const result = h("div"), useRow = h("div", { class: "row" });
  const get = (c, primary) => {
    const inst = lib.installed.some(x => x.model_id === c.model_id);
    return h("button", { class: "btn" + (primary ? " primary" : ""), onclick: () => { Chat.fresh(); Chat.runModel(c); go("chat"); } },
      !inst && icon("save", 18), inst ? t("start") : t(primary ? "get_this" : "get"));
  };
  const render = (rec, relaxed) => {
    const b = rec.budget, d = rec.default, others = rec.fits.filter(c => !d || c.model_id !== d.model_id);
    add(clear(result),
      h("p", { class: "muted", style: "margin-top:22px", text: t("device_line", { ram: gb(b.ram_total_gib), budget: gb(b.total_budget_gib) }) + " " +
        (b.vram_total_gib > 0 ? t("device_gpu", { vram: gb(b.vram_total_gib) }) : t("device_cpu")) + (b.nodes > 1 ? " " + t("device_pool", { n: b.nodes - 1 }) : "") }),
      (rec.unsupported_use_cases || []).length > 0 && h("p", { class: "note", text: t("setup_unsupported", { list: rec.unsupported_use_cases.map(u => t("use_" + u)).join(", ") }) }),
      d ? h("div", { class: "hero", style: "margin-top:14px" },
        h("div", { class: "small muted", text: t("get_recommended") }),
        h("div", { class: "row nowrap" }, sunMark("awake", 34), h("h2", { class: "grow", text: d.name }), speedChip(d)),
        h("p", { text: t("speedl_" + d.speed_class) + " " + t("dl_line", { size: gb(d.weights_gib) }) }),
        relaxed > 0 && h("p", { class: "small muted", text: t("setup_relaxed") }),
        h("div", { class: "row" }, get(d, true)),
        more(t("details"), modelFacts(d)))
        : h("div", { class: "hero", style: "margin-top:14px" }, h("h2", { text: t("get_none_title") }), h("p", { text: t("get_none_text") }),
          h("div", { class: "row" }, h("button", { class: "btn primary", onclick: () => go("devices") }, t("nav_devices")), h("button", { class: "btn", onclick: () => go("settings") }, t("set_paid")))),
      others.length > 0 && sec(t("setup_others"), t("setup_others_sub"), h("div", { class: "list" }, others.map(c => h("div", { class: "item" },
        h("div", { class: "row" }, h("span", { class: "name grow", text: c.name }), speedChip(c), get(c, false)),
        h("div", { class: "muted", text: t("speedl_" + c.speed_class) }), more(t("details"), modelFacts(c)))))),
      (rec.does_not_fit || []).length > 0 && h("section", { class: "section" }, more(t("setup_toobig", { n: rec.does_not_fit.length }),
        h("p", { class: "muted", text: t("setup_toobig_sub") }),
        h("div", { class: "list" }, rec.does_not_fit.map(c => h("div", { class: "item" },
          h("div", { class: "row" }, h("span", { class: "name grow", text: c.name }), speedChip(c)),
          h("div", { class: "muted", text: t("needs_memory", { need: gb(c.needed_gib), have: gb(b.total_budget_gib) }) })))))),
      sec(t("setup_can"), t("setup_can_sub"), h("div", { class: "list" }, (rec.abilities || []).map(a => h("div", { class: "item" },
        h("div", { class: "row" }, h("span", { class: "name grow", text: t("ab_" + a.id) }), verdictChip(a.verdict)),
        h("div", { class: "muted", text: (es() ? a.why_es : a.why) || "" }),
        (es() ? a.needs_es : a.needs) && h("div", { class: "small muted", text: es() ? a.needs_es : a.needs }))))),
      h("section", { class: "section" }, more(t("setup_advanced"),
        h("label", { class: "field" }, t("set_context"), h("span", { class: "hint", text: t("set_context_hint") }),
          h("select", { onchange: e => { ctx = +e.target.value; load(); } }, [2048, 4096, 8192, 16384, 32768].map(n => h("option", { value: n, selected: n === ctx }, t("ctx_" + n))))),
        switchRow(t("setup_pool"), t("setup_pool_hint"), S.pool, v => { S.pool = v; load(); }),
        h("button", { class: "btn", style: "justify-self:start", onclick: ownFileDialog }, icon("folder", 18), t("lib_own_file")))));
  };
  const load = async () => {
    add(clear(result), spinner());
    try {
      lib = await Chat.library(true);
      const q = new URLSearchParams({ use: [...uses].join(","), mode, context: String(ctx), pool: S.pool ? "1" : "0" });
      let rec = await api("/api/recommend?" + q), relaxed = 0;
      for (const c of [4096, 2048]) {
        if (rec.default || ctx <= c) break;
        q.set("context", String(c)); rec = await api("/api/recommend?" + q); relaxed = c;
      }
      S.status.use_cases = [...uses].join(","); S.status.resource_mode = mode;
      render(rec, relaxed);
    } catch (e) { add(clear(result), h("p", { class: "note bad", text: e.message })); }
  };
  const drawUses = () => add(clear(useRow), ["images", "coding", "agents", "sound", "video"].map(u =>
    h("button", { class: "toggle-chip", "aria-pressed": String(uses.has(u)), onclick: () => { if (uses.has(u)) uses.delete(u); else uses.add(u); drawUses(); load(); } }, t("use_" + u))));
  drawUses();
  wrap.append(sec(t("setup_what"), t("setup_what_sub"), useRow),
    sec(t("setup_mode"), t("setup_mode_sub"), seg([["light", t("mode_light")], ["balanced", t("mode_balanced")], ["heavy", t("mode_heavy")]], mode, v => { mode = v; load(); })),
    result);
  await load();
};

/* ======================= My AIs ======================= */
function ownFileDialog() {
  const path = h("input", { type: "text", placeholder: t("own_path_example"), "aria-label": t("own_path") });
  openDialog({
    title: t("lib_own_file"),
    body: [h("p", { text: t("own_text") }),
      h("div", { class: "row" },
        h("button", { class: "btn", onclick: guard(async () => {
          const r = await api("/api/pick-file", { method: "POST" });
          if (r.path) path.value = r.path; else if (!r.available) { toast(t("own_no_picker")); path.focus(); }
        }) }, icon("folder", 18), t("own_choose")),
        h("button", { class: "btn quiet", onclick: () => openFile(S.status.models_dir) }, t("own_open_folder"))),
      h("label", { class: "field" }, t("own_path"), path),
      h("p", { class: "small muted", text: t("own_note") })],
    actions: close => [h("button", { class: "btn", onclick: close }, t("cancel")),
      h("button", { class: "btn primary", onclick: () => {
        const p = path.value.trim().replace(/^"|"$/g, "");
        if (!p) { path.focus(); return; }
        close(); Chat.fresh();
        Chat.runModel({ custom: true, path: p, name: p.split(/[\\/]/).pop() });
        go("chat");
      } }, t("start"))],
  });
}
SCREENS.library = async view => {
  const wrap = page(view, t("lib_title"), t("lib_lead"));
  wrap.append(h("div", { class: "row" },
    h("button", { class: "btn primary", onclick: () => go("setup") }, icon("plus", 18), t("nav_setup")),
    h("button", { class: "btn", onclick: ownFileDialog }, icon("folder", 18), t("lib_own_file"))));
  const box = h("div", { class: "section" }, spinner());
  wrap.append(box);
  const chat = it => { Chat.fresh(); const running = S.status.provider === "local" && S.status.server.running && S.status.server.model_id === it.model_id; if (!running) Chat.runModel(it); go("chat"); };
  const load = async () => {
    const lib = await Chat.library(true), st = S.status;
    clear(box);
    if (!lib.installed.length) { box.append(h("p", { class: "note", text: t("lib_empty") })); return; }
    box.append(h("div", { class: "list" }, lib.installed.map(it => {
      const running = st.provider === "local" && st.server.running && st.server.model_id === it.model_id, r = it.resources;
      const menu = e => openMenu(e.currentTarget, [
        { label: t("lib_shortcut"), icon: "external", fn: guard(async () => { await api("/api/library/shortcut", { body: { model_id: it.model_id } }); toast(t("lib_shortcut_done")); }) },
        running && { label: t("ai_sleep_now"), icon: "moon", fn: guard(async () => { await api("/api/stop", { method: "POST" }); await refreshStatus(); load(); }) },
        { label: t("lib_remove"), icon: "trash", danger: true, fn: async () => {
          if (!await confirmDialog(t("lib_remove"), t("lib_remove_text", { name: it.name, size: gb(it.size_gib) }), t("lib_remove"), true)) return;
          try { await api("/api/library/" + encodeURIComponent(it.model_id), { method: "DELETE" }); } catch (e) { oops(e); }
          await refreshStatus(); load();
        } }]);
      const versions = (it.versions || []).filter(v => v.kind === "quant" || v.fits);
      return h("div", { class: "item" },
        h("div", { class: "row" }, sunMark(running ? "awake" : "none", 26), h("span", { class: "name grow", text: it.name }),
          running && h("span", { class: "chip ok", text: t("ai_running") }), r && speedChip(r),
          h("button", { class: "btn sky", onclick: () => chat(it) }, icon("chat", 18), t("lib_chat")),
          h("button", { class: "icon-btn", "aria-label": t("chat_options"), onclick: menu }, icon("more"))),
        it.custom ? h("div", { class: "muted", text: t("lib_custom", { path: it.path }) }) : [
          it.good_for && h("div", {}, h("b", { text: t("lib_good_for") + " " }), it.good_for),
          it.limits && h("div", { class: "muted" }, h("b", { text: t("lib_keep_in_mind") + " " }), it.limits),
          r && h("div", { class: "muted", text: t("lib_uses", { memory: gb(r.memory_gib), disk: gb(r.disk_gib) }) + " " + t("where_" + r.placement) }),
          more(t("details"), kv([
            [t("f_maker"), it.vendor_url ? extLink(it.vendor, it.vendor_url) : it.vendor], [t("f_licence"), it.license],
            [t("f_like"), it.comparable && [it.comparable.verdict, h("div", { class: "small muted", text: it.comparable.disclaimer || "" })]],
            [t("f_variant"), it.finetune_of && t("variant_of", { name: it.finetune_of })],
            [t("f_speed"), r && t("speedl_" + r.speed_class)], [t("f_page"), it.model_page && extLink(t("open_page"), it.model_page)],
          ])),
          versions.length > 0 && more(t("lib_versions", { n: versions.length }),
            h("p", { class: "small muted", text: t("lib_versions_sub") }),
            h("div", { class: "list" }, versions.map(v => h("div", { class: "item" }, h("div", { class: "row" },
              h("span", { class: "grow" }, v.name, " ", h("span", { class: "chip plain", text: t("rel_" + v.relation) })),
              h("span", { class: "small muted", text: t("lib_version_cost", { download: gb(v.download_gib), memory: gb(v.memory_gib) }) }), speedChip(v),
              h("button", { class: "btn small", onclick: () => { Chat.fresh(); Chat.runModel(v); go("chat"); } }, t(v.installed ? "start" : "get")))))))]);
    })));
  };
  await load();
};

/* ======================= Create: pictures and video ======================= */
const SIZES = {
  image: [["1024x1024", "1024 × 1024"], ["768x1024", "768 × 1024"], ["1024x768", "1024 × 768"], ["640x640", "640 × 640"]],
  video: [["832x480|2", "832 × 480, 2 s"], ["480x832|2", "480 × 832, 2 s"], ["832x480|4", "832 × 480, 4 s"], ["1280x704|3", "1280 × 704, 3 s"]],
};
const mediaNode = (src, isVideo) => isVideo ? h("video", { src, controls: true, loop: true, muted: true, playsinline: true }) : h("img", { src, alt: t("picture"), loading: "lazy" });
SCREENS.create = async view => {
  const wrap = page(view, t("create_title"), t("create_lead"));
  let kind = "image";
  const body = h("div", { class: "stack", style: "margin-top:18px" }), gallery = h("div", { class: "gallery" });
  wrap.append(seg([["image", t("create_image")], ["video", t("create_video")]], kind, v => { kind = v; load(); }), body, sec(t("create_gallery"), null, gallery));
  const loadGallery = async () => {
    try {
      const g = await api("/api/images/list");
      add(clear(gallery), g.images.length ? g.images.map(x => {
        const u = "/api/images/file/" + encodeURIComponent(x.name);
        return h("figure", {}, mediaNode(u, /\.(webm|avi|mp4)$/i.test(x.name)),
          h("button", { class: "icon-btn", "aria-label": t("delete"), onclick: guard(async () => { await api(u, { method: "DELETE" }); loadGallery(); }) }, icon("trash", 16)));
      }) : h("p", { class: "muted", text: t("create_empty") }));
    } catch (e) { /* the gallery is optional */ }
  };
  const load = async () => {
    add(clear(body), spinner());
    let st;
    try { st = await api("/api/images?kind=" + kind); } catch (e) { add(clear(body), h("p", { class: "note bad", text: e.message })); return; }
    const c = st.choice, p = c.plain, run = st.server.running;
    const prompt = h("textarea", { rows: "3", placeholder: t("create_prompt_example") });
    const neg = h("input", { type: "text" }), size = h("select", {}, SIZES[kind].map(([v, l]) => h("option", { value: v }, l)));
    const init = h("input", { type: "file", accept: "image/*" }), consent = h("input", { type: "checkbox" });
    const out = h("div", { class: "result-media stack" });
    add(clear(body),
      h("div", { class: "sheet stack" },
        h("div", { class: "row" }, h("b", { class: "grow", text: p.name }), c.fits ? speedChip({ speed_class: c.speed }) : h("span", { class: "chip no", text: t("speed_nofit") })),
        h("div", { text: p.what }), h("div", { class: "muted", text: p.limits }),
        h("div", { class: "small muted", text: t("create_cost", { download: p.download, memory: p.memory }) + " " + (c.reasons || []).join(" ") }),
        h("div", { class: "row" },
          run ? h("button", { class: "btn", onclick: guard(async () => { await api("/api/images/stop", { method: "POST" }); load(); }) }, t("create_stop"))
            : h("button", { class: "btn primary", onclick: guard(async () => {
              const j = await api("/api/images/setup?kind=" + kind, { method: "POST" });
              await Jobs.track(j, { title: p.name }); if (S.screen === "create") load();
            }) }, t(st.ready ? "create_start" : "create_get")),
          h("span", { class: "small muted", text: t(run ? "create_running" : st.ready ? "create_ready" : "create_not_yet") }))),
      run && h("div", { class: "stack" },
        h("label", { class: "field" }, t("create_prompt"), prompt),
        h("div", { class: "grid2" }, h("label", { class: "field" }, t("create_size"), size), h("label", { class: "field" }, t("create_avoid"), neg)),
        kind === "video" && h("label", { class: "field" }, t("create_from_picture"), init),
        kind === "video" && h("label", { class: "switch" }, consent, h("span", {}, h("b", { text: t("create_consent") }), h("span", { class: "hint", text: t("create_consent_hint") }))),
        h("button", { class: "btn primary", style: "justify-self:start", onclick: guard(async e => {
          const text = prompt.value.trim(), btn = e.currentTarget;
          if (!text) { prompt.focus(); return; }
          const f = init.files && init.files[0];
          if (f && !consent.checked) { toast(t("create_consent_need")); return; }
          btn.disabled = true; clear(out);
          try {
            let j;
            if (kind === "video") {
              const [sz, secs] = size.value.split("|"), [w, hh] = sz.split("x").map(Number);
              j = await api("/api/video/generate", { body: { prompt: text, negative: neg.value.trim(), width: w, height: hh, seconds: +secs, init_image_b64: f ? await fileBase64(f) : null } });
            } else {
              const [w, hh] = size.value.split("x").map(Number);
              j = await api("/api/images/generate", { body: { prompt: text, negative: neg.value.trim(), width: w, height: hh } });
            }
            const x = await Jobs.track(j, { title: t(kind === "video" ? "create_video" : "create_image") }), r = x.result || {};
            if (r.files) add(out, r.files.map(n => mediaNode("/api/images/file/" + encodeURIComponent(n), /\.(webm|avi|mp4)$/i.test(n))));
            else if (r.b64) add(out, r.b64.map(d => mediaNode(`data:${r.ext === "png" ? "image/png" : "video/" + r.ext};base64,${d}`, r.ext !== "png")));
            loadGallery();
          } finally { btn.disabled = false; }
        }) }, t("create_go")), out));
  };
  await load();
  loadGallery();
};

/* ======================= Tools ======================= */
function resultDialog(title, markdown, extra) {
  openDialog({ title, wide: true, body: [h("div", { class: "md" }, md(markdown))],
    actions: close => [extra, h("button", { class: "btn", onclick: () => copyText(markdown) }, icon("copy", 16), t("copy")),
      h("button", { class: "btn", onclick: e => openMenu(e.currentTarget, FORMATS.map(f => ({ label: t("fmt_" + f), icon: "doc", fn: guard(async () => savedToast(await api("/api/export", { body: { markdown, format: f, title, lang: S.lang } }))) }))) }, icon("save", 16), t("save_as")),
      h("button", { class: "btn primary", onclick: close }, t("close"))] });
}
SCREENS.tools = async view => {
  const wrap = page(view, t("tools_title"), t("tools_lead"));
  const busy = (btn, fn) => guard(async () => { btn.disabled = true; try { await fn(); } finally { btn.disabled = false; } })();
  // recording → text
  const recFile = h("input", { type: "file", accept: "audio/*,video/*" });
  const recBtn = h("button", { class: "btn", onclick: () => busy(recBtn, async () => {
    const f = recFile.files[0];
    if (!f) { recFile.click(); return; }
    const j = await api("/api/tools/transcribe?name=" + encodeURIComponent(f.name) + "&lang=" + S.lang, { raw: f });
    const x = await Jobs.track(j, { title: t("tool_rec") });
    if (x.state === "done" && x.result) resultDialog(f.name, x.result.markdown || x.result.text || "", x.result.srt && h("button", { class: "btn", onclick: () => openFile(x.result.srt, true) }, t("tool_rec_srt")));
  }) }, t("tool_rec_go"));
  // text → audio
  const spText = h("textarea", { rows: "3", placeholder: t("tool_speak_example") });
  const spBtn = h("button", { class: "btn", onclick: () => busy(spBtn, async () => {
    if (!spText.value.trim()) { spText.focus(); return; }
    const x = await Jobs.track(await api("/api/tools/speak", { body: { text: spText.value, lang: S.lang, title: "" } }), { title: t("tool_speak") });
    if (x.state === "done" && x.result) savedToast({ path: x.result.mp3 || x.result.path });
  }) }, t("tool_speak_go"));
  // long documents
  const lgFile = h("input", { type: "file" }), lgText = h("textarea", { rows: "3", placeholder: t("tool_long_paste") });
  let lgMode = "summary", lgLang = S.lang, lgHands = false;
  const lgHelp = h("div");   // filled when linked devices can take parts of the work
  const lgBtn = h("button", { class: "btn", onclick: () => busy(lgBtn, async () => {
    const f = lgFile.files[0];
    if (!f && !lgText.value.trim()) { lgText.focus(); return; }
    const body = { mode: lgMode, lang: lgLang, devices: lgHands, text: f ? "" : lgText.value, name: f ? f.name : "", content_base64: f ? await fileBase64(f) : "" };
    const x = await Jobs.track(await api("/api/tools/long", { body }), { title: t("tool_long") });
    if (x.state === "done" && x.result) {
      resultDialog(f ? f.name : t("tool_long"), x.result.markdown || "");
      if ((x.result.dropped || []).length) toast(t("tool_long_dropped", { names: x.result.dropped.join(", ") }), { ms: 9000 });
      else if ((x.result.helped || []).length) toast(t("tool_long_helped", { names: x.result.helped.join(", ") }));
    }
  }) }, t("tool_long_go"));
  const programs = h("div", {}, spinner()), conns = h("div", {}, spinner()), apps = h("div", {}, spinner()), hw = h("div", {}, spinner());
  api("/api/tools/long/helpers").then(r => {
    const names = (r.devices || []).map(d => d.ai ? d.name + " (" + d.ai + ")" : d.name);
    if (names.length) add(clear(lgHelp), switchRow(t("tool_long_hands"), t("tool_long_hands_hint", { names: names.join(", ") }), lgHands, v => { lgHands = v; }));
  }).catch(() => {});
  wrap.append(
    sec(t("tools_agent"), t("tools_agent_sub"), h("button", { class: "btn primary", onclick: guard(async () => { await api("/api/window/agent", { method: "POST" }); toast(t("agent_opened")); }) }, icon("agent", 18), t("tools_agent_open"))),
    sec(t("tools_everyday"), t("tools_everyday_sub"), h("div", { class: "grid2" },
      h("div", { class: "sheet stack" }, h("b", { text: t("tool_rec") }), h("span", { class: "muted small", text: t("tool_rec_sub") }), recFile, recBtn),
      h("div", { class: "sheet stack" }, h("b", { text: t("tool_speak") }), h("span", { class: "muted small", text: t("tool_speak_sub") }), spText, spBtn),
      h("div", { class: "sheet stack" }, h("b", { text: t("tool_long") }), h("span", { class: "muted small", text: t("tool_long_sub") }), lgFile, lgText,
        h("div", { class: "row" }, seg([["summary", t("tool_long_summary")], ["translate", t("tool_long_translate")]], lgMode, v => { lgMode = v; }),
          seg([["en", "English"], ["es", "Español"]], lgLang, v => { lgLang = v; })), lgHelp, lgBtn))),
    !isRemote() && sec(t("hw_title"), t("hw_sub"), hw),
    sec(t("tools_programs"), t("tools_programs_sub"), programs),
    sec(t("tools_conns"), t("tools_conns_sub"), conns),
    sec(t("tools_apps"), t("tools_apps_sub"), apps));

  const loadPrograms = async () => {
    const r = await api("/api/programs?lang=" + S.lang);
    const row = p => h("div", { class: "item" }, h("div", { class: "row" }, h("span", { class: "name grow", text: p.name }),
      h("span", { class: "chip " + (p.found ? "ok" : "plain"), text: t(p.found ? "prog_found" : "prog_missing") }),
      p.found ? h("button", { class: "btn small", onclick: guard(() => api("/api/programs/" + p.id + "/open", { body: {} })) }, t("open")) : extLink(t("prog_site"), p.site)),
      h("div", { class: "muted", text: p.does }));
    const found = r.programs.filter(p => p.found), missing = r.programs.filter(p => !p.found);
    add(clear(programs),
      h("div", { class: "sheet stack", style: "margin-bottom:12px" }, h("b", { text: "ArtCraft" }), h("span", { class: "muted", text: t("artcraft_text") }),
        h("div", { class: "row" },
          h("button", { class: "btn", onclick: guard(async () => { const x = await Jobs.track(await api("/api/programs/artcraft/get", { method: "POST" }), { title: "ArtCraft" }); if (x.state === "done") toast(t("artcraft_opened")); }) }, icon("save", 18), t("artcraft_get")),
          extLink(t("prog_site"), r.artcraft.site))),
      found.length ? h("div", { class: "list" }, found.map(row)) : h("p", { class: "muted", text: t("prog_none") }),
      missing.length > 0 && more(t("prog_more", { n: missing.length }), h("div", { class: "list" }, missing.map(row))));
    // connections (Model Context Protocol)
    const name = h("input", { type: "text", placeholder: t("conn_name") }), cmd = h("input", { type: "text", placeholder: t("conn_command") }), args = h("input", { type: "text", placeholder: t("conn_args") });
    add(clear(conns),
      r.connections.length ? h("div", { class: "list" }, r.connections.map(c => {
        const note = h("div", { class: "small muted" });
        return h("div", { class: "item" }, h("div", { class: "row" }, icon("chain", 18), h("span", { class: "name grow", text: c.name }),
          h("button", { class: "btn small", onclick: guard(async () => {
            note.textContent = t("conn_testing");
            const x = await api("/api/mcp/" + encodeURIComponent(c.name) + "/test", { method: "POST" });
            note.textContent = x.ok ? t("conn_ok", { n: x.tools.length }) + " " + x.tools.slice(0, 12).map(z => z.name).join(", ") : t("conn_failed") + " " + (x.error || "");
          }) }, t("conn_test")),
          c.source === "yours" && h("button", { class: "icon-btn", "aria-label": t("delete"), onclick: guard(async () => { await api("/api/mcp/" + encodeURIComponent(c.name), { method: "DELETE" }); loadPrograms(); }) }, icon("trash", 16))),
          h("div", { class: "small muted", text: [c.command, ...(c.args || [])].join(" ") }), note);
      })) : h("p", { class: "muted", text: t("conn_none") }),
      more(t("conn_add"), h("div", { class: "stack" }, name, cmd, args, h("p", { class: "small muted", text: t("conn_warn") }),
        h("button", { class: "btn", style: "justify-self:start", onclick: guard(async () => {
          await api("/api/mcp", { body: { name: name.value.trim(), command: cmd.value.trim(), args: args.value.trim() ? args.value.trim().split(/\s+/) : [] } });
          loadPrograms();
        }) }, t("save")))));
  };
  const loadApps = async () => {
    const r = await api("/api/apps");
    add(clear(apps), h("div", { class: "list" }, r.apps.map(a => {
      const note = h("span", { class: "small muted" });
      return h("div", { class: "item" },
        h("div", { class: "row" }, h("span", { class: "name grow", text: a.name }), verdictChip(a.verdict)),
        h("div", { text: es() ? (a.plain_es || a.plain_en) : a.plain_en }),
        h("div", { class: "small muted" }, a.why || "", " ", t("f_maker"), ": ", a.maker, ". ", t("f_licence"), ": ", a.license, ". ", extLink(t("prog_site"), a.url)),
        h("div", { class: "row" },
          h("button", { class: "btn", onclick: guard(async () => {
            const x = await Jobs.track(await api("/api/apps/" + a.id + "/open", { method: "POST" }), { title: a.name, onTick: j => { note.textContent = ((j.log || []).slice(-1)[0] || "").slice(0, 120); } });
            if (S.screen === "tools") loadApps();
            if (x.state === "error") oops(new Error(x.error));
          }) }, t(a.running ? "app_show" : a.installed ? "open" : "app_install")),
          a.running && h("button", { class: "btn", onclick: guard(async () => { await api("/api/apps/" + a.id + "/stop", { method: "POST" }); loadApps(); }) }, t("stop")),
          a.installed && h("button", { class: "btn danger", onclick: async () => {
            if (!await confirmDialog(t("lib_remove"), t("app_remove_text", { name: a.name }), t("lib_remove"), true)) return;
            try { await api("/api/apps/" + a.id, { method: "DELETE" }); } catch (e) { oops(e); }
            loadApps();
          } }, t("lib_remove")), note));
    })));
  };
  loadPrograms().catch(e => add(clear(programs), h("p", { class: "note bad", text: e.message })));
  loadApps().catch(e => add(clear(apps), h("p", { class: "note bad", text: e.message })));
  if (!isRemote()) hardware(hw, busy).catch(e => add(clear(hw), h("p", { class: "note bad", text: e.message })));
};

/* ---- Tools: cameras, printers, boards, home and industrial devices ---- */
async function hardware(box, busy) {
  const th = await api("/api/things"), set = th.settings;
  const again = () => hardware(box, busy).catch(oops);
  const line = (ic, name, sub, ...btns) => h("div", { class: "item" }, h("div", { class: "row" }, icon(ic), h("span", { class: "name grow", text: name }), btns), sub && h("div", { class: "muted", text: sub }));
  const act = (label, fn) => { const b = h("button", { class: "btn small", onclick: () => busy(b, fn) }, label); return b; };
  const rows = [];
  // cameras
  const tryPhoto = c => act(t("hw_try_photo"), async () => { const r = await Things.photo(c && c.id); if (r) Things.show(c ? c.name : t("hw_camera"), r); else again(); });
  if (th.cameras.length) th.cameras.forEach(c => rows.push(line("camera", c.name, t("hw_camera"), tryPhoto(c))));
  else if (!th.ffmpeg.found && th.ffmpeg.bytes && th.problems.cameras) {
    rows.push(line("camera", t("hw_camera"), t("hw_ffmpeg_need", { size: Math.round(th.ffmpeg.bytes / 1e6) }),
      act(t("hw_ffmpeg_get"), async () => { await Jobs.track(await api("/api/things/ffmpeg", { method: "POST" }), { title: "FFmpeg" }); again(); })));
  } else rows.push(line("camera", t("hw_camera"), th.problems.cameras || t("hw_no_camera")));
  // the screen
  rows.push(th.screens.length
    ? line("screen", t("hw_screen"), th.screens.map(x => x.width + " × " + x.height).join(", "), act(t("hw_try_screen"), async () => Things.show(t("hw_screen"), await Things.screen(false))))
    : line("screen", t("hw_screen"), th.problems.screens || t("hw_no_screen")));
  // printers
  if (th.printers.length) th.printers.forEach(p => rows.push(line("printer", p.name, t("hw_printer") + (p.default ? ", " + t("hw_default") : ""))));
  else rows.push(line("printer", t("hw_printer"), th.problems.printers || t("hw_no_printer")));
  // boards and instruments on serial ports
  if (th.serial.length) th.serial.forEach(p => {
    const speed = h("select", { "aria-label": t("hw_speed"), title: t("hw_speed"), style: "width:auto;min-height:32px;padding:2px 8px" }, [9600, 115200, 57600, 38400, 19200, 4800].map(n => h("option", { value: String(n), text: String(n) })));
    rows.push(line("plug", p.what, [p.port, p.maker].filter(Boolean).join(", "), speed, act(t("hw_listen"), async () => {
      const r = await api("/api/things/serial", { body: { port: p.port, seconds: 3, baud: Number(speed.value) } });
      openDialog({ title: t("hw_listen_title", { port: p.port }), wide: true, body: [r.text.trim() ? h("pre", { class: "serial", text: r.text }) : h("p", { class: "muted", text: t("hw_listen_none") })],
        actions: close => [h("button", { class: "btn primary", onclick: close }, t("close"))] });
    })));
  });
  else rows.push(line("plug", t("hw_board"), th.problems.serial || t("hw_no_board")));
  // the mouse and keyboard
  rows.push(line("sliders", t("hw_control"), th.control.ok ? t("hw_control_yes") : t("hw_control_no", { why: th.control.why })));

  // connections to the person's own hubs
  const field = (label, input, hint) => h("label", { class: "field" }, label, input, hint && h("span", { class: "hint", text: hint }));
  const result = () => h("div", { class: "small", role: "status" });
  const check = (note, what, name, save) => async () => {
    note.style.color = ""; note.textContent = t("hw_checking");
    await save();
    const r = await api("/api/things/check", { body: { what, name } });
    note.textContent = r.detail; note.style.color = r.ok ? "var(--ok)" : "var(--bad)";
  };
  const saved = note => { note.style.color = ""; note.textContent = t("saved"); };
  // MQTT
  const mq = set.mqtt, mqHost = h("input", { type: "text", value: mq.host, placeholder: "192.168.1.10" }), mqPort = h("input", { type: "number", value: String(mq.port), min: "1", max: "65535" }),
    mqUser = h("input", { type: "text", value: mq.username, autocomplete: "off" }), mqPass = h("input", { type: "password", autocomplete: "new-password", placeholder: mq.password_set ? t("hw_secret_kept") : "" }),
    mqNote = result();
  let mqTls = !!mq.tls;
  const saveMq = () => api("/api/things/settings", { body: { mqtt: { host: mqHost.value.trim(), port: Number(mqPort.value) || 1883, username: mqUser.value.trim(), password: mqPass.value, tls: mqTls } } });
  // Home Assistant
  const ha = set.home_assistant, haUrl = h("input", { type: "text", value: ha.url, placeholder: "http://homeassistant.local:8123" }),
    haTok = h("input", { type: "password", autocomplete: "new-password", placeholder: ha.token_set ? t("hw_secret_kept") : "" }), haNote = result();
  const saveHa = () => api("/api/things/settings", { body: { home_assistant: { url: haUrl.value.trim(), token: haTok.value.trim() } } });
  // Modbus
  const mbList = h("div", { class: "stack" }), mbNote = result();
  const mbRows = () => [...mbList.children].map(r => ({ name: r.querySelector("[data-k=name]").value.trim(), host: r.querySelector("[data-k=host]").value.trim(),
    port: Number(r.querySelector("[data-k=port]").value) || 502, unit: Number(r.querySelector("[data-k=unit]").value) || 1 })).filter(d => d.host);
  const saveMb = () => api("/api/things/settings", { body: { modbus: mbRows() } });
  const mbRow = d => {
    const name = h("input", { type: "text", value: d.name || "", placeholder: "Inverter", data: { k: "name" } }),
      host = h("input", { type: "text", value: d.host || "", placeholder: "192.168.1.50", data: { k: "host" } });
    const row = h("div", { class: "mb-row" },
      h("div", { class: "fields" }, field(t("hw_name"), name), field(t("hw_address"), host),
        field(t("hw_port"), h("input", { type: "number", value: String(d.port || 502), min: "1", max: "65535", data: { k: "port" } })),
        field(t("hw_unit"), h("input", { type: "number", value: String(d.unit || 1), min: "0", max: "255", data: { k: "unit" } }))),
      h("div", { class: "row" },
        h("button", { class: "btn small", onclick: guard(() => check(mbNote, "modbus", name.value.trim() || host.value.trim(), saveMb)()) }, t("hw_check")),
        h("button", { class: "btn small danger", onclick: () => row.remove() }, t("hw_remove"))));
    return row;
  };
  (set.modbus.length ? set.modbus : []).forEach(d => mbList.append(mbRow(d)));
  const home = more(t("hw_home"), h("p", { class: "muted", text: t("hw_home_sub") }), h("div", { class: "stack" },
    h("div", { class: "sheet stack" }, h("b", { text: t("hw_mqtt") }), h("span", { class: "muted small", text: t("hw_mqtt_hint") }),
      h("div", { class: "fields" }, field(t("hw_address"), mqHost), field(t("hw_port"), mqPort), field(t("hw_user"), mqUser), field(t("hw_password"), mqPass)),
      switchRow(t("hw_tls"), null, mqTls, v => { mqTls = v; }),
      h("div", { class: "row" }, h("button", { class: "btn", onclick: guard(async () => { await saveMq(); saved(mqNote); }) }, t("save")),
        h("button", { class: "btn", onclick: guard(check(mqNote, "mqtt", null, saveMq)) }, t("hw_check")), mqNote)),
    h("div", { class: "sheet stack" }, h("b", { text: t("hw_ha") }), h("span", { class: "muted small", text: t("hw_ha_hint") }),
      h("div", { class: "fields wide" }, field(t("hw_address"), haUrl), field(t("hw_token"), haTok)),
      h("div", { class: "row" }, h("button", { class: "btn", onclick: guard(async () => { await saveHa(); saved(haNote); }) }, t("save")),
        h("button", { class: "btn", onclick: guard(check(haNote, "home_assistant", null, saveHa)) }, t("hw_check")), haNote)),
    h("div", { class: "sheet stack" }, h("b", { text: t("hw_modbus") }), h("span", { class: "muted small", text: t("hw_modbus_hint") }), mbList,
      h("div", { class: "row" }, h("button", { class: "btn", onclick: () => mbList.append(mbRow({})) }, icon("plus", 16), t("hw_add_device")),
        h("button", { class: "btn", onclick: guard(async () => { await saveMb(); saved(mbNote); }) }, t("save")), mbNote))));
  // what announces itself on the network
  const found = h("div");
  const look = h("button", { class: "btn", onclick: () => busy(look, async () => {
    add(clear(found), h("p", { class: "muted", text: t("hw_around_looking") }));
    const r = await api("/api/things/around?seconds=4");
    add(clear(found), r.devices.length ? h("div", { class: "list" }, r.devices.map(d => h("div", { class: "item" },
      h("div", { class: "row" }, h("span", { class: "name grow", text: d.name || d.host || d.address }), h("span", { class: "chip plain", text: d.address })),
      h("div", { class: "muted", text: d.kind })))) : h("p", { class: "muted", text: t("hw_around_none") }));
  }) }, icon("search", 18), t("hw_around_go"));
  const around = more(t("hw_around"), h("p", { class: "muted", text: t("hw_around_sub") }), look, found);
  add(clear(box), h("div", { class: "list" }, rows),
    h("div", { class: "row", style: "margin:10px 0 4px" }, h("button", { class: "btn quiet small", onclick: again }, icon("refresh", 16), t("hw_again")),
      extLink(t("hw_doc"), "https://github.com/Mdatas/datas.ar/blob/main/docs/HARDWARE.md")),
    home, around);
}

/* ======================= Devices ======================= */
SCREENS.devices = async view => {
  const wrap = page(view, t("dev_title"), t("dev_lead"));
  const box = h("div");
  wrap.append(box, sec(t("dev_how"), null,
    h("ul", { class: "muted", style: "padding-left:22px;margin:0;display:grid;gap:6px" }, [1, 2, 3, 4, 5, 6].map(k => h("li", { text: t("dev_how_" + k) }))),
    h("p", { style: "margin-top:10px" }, extLink(t("dev_doc"), "https://github.com/Mdatas/datas.ar/blob/main/docs/DEVICES.md"))));
  let timer = null, st = null, nearby = [];
  const addr = h("input", { type: "text", placeholder: "192.168.1.20:8424", "aria-label": t("dev_address") });
  const code = h("input", { type: "text", placeholder: "ABCD-EFGH-JKLM", "aria-label": t("dev_code"), autocomplete: "off", style: "text-transform:uppercase" });
  const call = (path, opts) => guard(async () => { const r = await api(path, opts); st = r.state || (r.device ? r : st); draw(); if (!r.device && !r.state) refresh(); })();
  const refresh = async () => { try { st = await api("/api/link"); draw(); } catch (e) { /* try again on the next round */ } };
  const draw = () => {
    if (!st) return;
    const typing = document.activeElement === addr || document.activeElement === code;
    if (typing && box.contains(addr)) return;       // do not redraw under the person's fingers
    clear(box);
    box.append(switchRow(t("dev_enable"), t("dev_enable_hint"), st.enabled, v => call("/api/link/enable", { body: { on: v } })));
    if (st.error) box.append(h("p", { class: "note bad", text: st.error }));
    if (!st.enabled) return;
    box.append(
      sec(t("dev_this"), null, kv([[t("dev_name"), [st.device.name, " ", h("button", { class: "btn quiet small", onclick: async () => {
        const n = await promptDialog(t("dev_rename"), t("dev_name"), st.device.name);
        if (n) call("/api/link/options", { body: { device_name: n } });
      } }, t("rename"))]], [t("dev_id"), st.device.short_id], [t("dev_addresses"), (st.addresses || []).join(", ") || t("dev_no_address")]])),
      sec(t("dev_link"), t("dev_link_sub"), h("div", { class: "grid2" },
        h("div", { class: "sheet stack" }, h("b", { text: t("dev_show_code") }),
          st.pairing ? [h("div", { class: "code-big", text: st.pairing.code }),
            h("div", { class: "muted small", text: t("dev_code_valid", { min: Math.max(1, Math.round(st.pairing.expires_in / 60)), address: (st.pairing.addresses || st.addresses || [])[0] || "" }) }),
            h("div", { class: "muted small", text: t("dev_code_phone") }),
            h("button", { class: "btn small", style: "justify-self:start", onclick: () => call("/api/link/pairing", { method: "DELETE" }) }, t("cancel"))]
            : [h("span", { class: "muted small", text: t("dev_show_code_sub") }),
              h("button", { class: "btn primary", style: "justify-self:start", onclick: () => call("/api/link/pairing", { method: "POST" }) }, t("dev_make_code"))]),
        h("div", { class: "sheet stack" }, h("b", { text: t("dev_have_code") }), h("span", { class: "muted small", text: t("dev_have_code_sub") }), addr, code,
          nearby.length > 0 && h("div", { class: "row" }, h("span", { class: "small muted", text: t("dev_nearby") }), nearby.map(n => h("button", { class: "btn small", onclick: () => { addr.value = n.address; code.focus(); } }, n.name))),
          h("button", { class: "btn", style: "justify-self:start", onclick: guard(async () => {
            const r = await api("/api/link/pair", { body: { address: addr.value.trim(), code: code.value.trim().toUpperCase() } });
            addr.value = ""; code.value = ""; st = r.state; toast(t("dev_linked", { name: r.peer.name })); draw();
          }) }, t("dev_link_go"))))),
      sec(t("dev_peers"), null, st.peers.length ? h("div", { class: "list" }, st.peers.map(p => p.kind === "app" ? h("div", { class: "item" },
        h("div", { class: "row" }, icon("phone"), h("span", { class: "name grow", text: p.name }),
          h("span", { class: "chip " + (p.online ? "ok" : "plain"), text: p.online ? t("dev_online") : p.seen ? t("dev_seen", { when: when(p.seen) }) : t("dev_offline") }),
          h("button", { class: "btn small danger", onclick: async () => {
            if (!await confirmDialog(t("dev_unlink"), t("dev_unlink_text", { name: p.name }), t("dev_unlink"), true)) return;
            call("/api/link/peers/" + p.id, { method: "DELETE" });
          } }, t("dev_unlink"))),
        h("div", { class: "muted", text: [t("dev_phone"), p.os].filter(Boolean).join(", ") }),
        switchRow(t("dev_phone_window"), t("dev_phone_window_hint"), p.window, v => call("/api/link/peers/" + p.id, { body: { window: v } })))
        : h("div", { class: "item" },
        h("div", { class: "row" }, icon("devices"), h("span", { class: "name grow", text: p.name }),
          h("span", { class: "chip " + (p.online ? "ok" : "plain"), text: t(p.online ? "dev_online" : "dev_offline") }),
          p.online && p.ai && p.ai.name && h("button", { class: "btn small", disabled: p.in_use, onclick: guard(async () => { await api("/api/link/use/" + p.id, { method: "POST" }); await refreshStatus(); toast(t("dev_using", { name: p.ai.name, device: p.name })); refresh(); }) }, t(p.in_use ? "ai_in_use" : "dev_use_ai")),
          p.online && h("button", { class: "btn small", onclick: guard(async () => {
            const r = await api("/api/link/peers/" + p.id + "/open", { body: {} });
            toast(r.shown ? t("dev_opened", { name: p.name }) : t("dev_opened_at", { url: r.url }), r.shown ? {} : { ms: 20000 });
          }) }, t("dev_open_datas")),
          h("button", { class: "btn small danger", onclick: async () => {
            if (!await confirmDialog(t("dev_unlink"), t("dev_unlink_text", { name: p.name }), t("dev_unlink"), true)) return;
            call("/api/link/peers/" + p.id, { method: "DELETE" });
          } }, t("dev_unlink"))),
        h("div", { class: "muted", text: [p.address, p.os, p.online && p.ai && p.ai.name ? t("dev_ai_there", { name: p.ai.name }) : "",
          p.online && p.shares_memory ? t("dev_shares", { mem: gb(p.memory_gib) }) : "", p.busy ? t("dev_busy") : ""].filter(Boolean).join(", ") }),
        !p.online && p.error && h("div", { class: "small muted", text: p.error }),
        p.online && !p.tag_matches && h("div", { class: "small", style: "color:var(--warn)", text: t("dev_tag_mismatch") }),
        switchRow(t("dev_phone_window"), t("dev_pc_window_hint"), p.window, v => call("/api/link/peers/" + p.id, { body: { window: v } })))))
        : h("p", { class: "muted", text: t("dev_no_peers") })),
      sec(t("dev_options"), null,
        switchRow(t("dev_share"), t("dev_share_hint"), st.share_memory, v => call("/api/link/options", { body: { share_memory: v } })),
        switchRow(t("dev_sync"), t(st.forget ? "dev_sync_forget" : "dev_sync_hint"), st.sync_chats && !st.forget, v => call("/api/link/options", { body: { sync_chats: v } }), st.forget),
        h("div", { class: "row" }, h("button", { class: "btn", onclick: guard(async () => { st = await api("/api/link/sync", { method: "POST" }); toast(t("dev_synced")); Chat.loadList(); draw(); }) }, icon("refresh", 18), t("dev_sync_now")),
          h("span", { class: "small muted", text: st.sync_error ? st.sync_error : st.last_sync ? t("dev_last_sync", { when: when(st.last_sync) }) : "" }))));
  };
  await refresh();
  if (st && st.enabled) api("/api/link/nearby").then(r => { nearby = r.devices || []; draw(); }).catch(() => {});
  timer = setInterval(async () => { try { st = await api("/api/link?refresh=1"); draw(); } catch (e) { /* later */ } }, 7000);
  return () => clearInterval(timer);
};

/* ======================= Learn ======================= */
SCREENS.learn = async view => {
  const wrap = page(view, t("learn_title"), t("learn_lead"));
  const data = await api("/api/learn?lang=" + S.lang);
  let level = 0, q = "", tab = "paths", path = null;
  const body = h("div");
  const levelName = n => (data.levels.find(l => l.id === n) || {}).name || "";
  const meter = n => h("span", { class: "meter", title: levelName(n), "aria-label": levelName(n) }, [1, 2, 3, 4, 5].map(k => h("i", { class: k <= n ? "on" : "" })));
  const fits = it => (!level || it.level === level) && (!q || (it.title + " " + (it.by || "") + " " + (it.why || "")).toLowerCase().includes(q));
  const setDone = async (it, done) => {
    try { const r = await api("/api/learn/progress", { body: { ref: it.ref, done } }); if (!r.saved && done) toast(t("learn_forget")); } catch (e) { oops(e); return; }
    for (const p of data.paths) for (const x of p.items) if (x.ref === it.ref) x.done = done;
    draw();
  };
  const openLesson = async it => {
    let le;
    try { le = await api("/api/learn/lesson/" + it.id + "?lang=" + S.lang); } catch (e) { oops(e); return; }
    openDialog({ title: le.title, wide: true, body: [h("div", { class: "md" }, md(le.markdown))],
      actions: close => [
        h("button", { class: "btn", onclick: async () => {
          close();
          Chat.fresh((await Chat.helpers()).guide);
          Chat.cur.atts = [{ name: le.title, text: le.markdown }];
          go("chat");
          $("#box").value = t("learn_ask_prefill", { title: le.title });
          Chat.grow();
        } }, icon("chat", 18), t("learn_ask")),
        h("button", { class: "btn primary", onclick: () => { close(); setDone(it, !it.done); } }, icon("check", 18), t(it.done ? "learn_undo" : "learn_done"))] });
  };
  const itemRow = it => it.type === "lesson"
    ? h("div", { class: "item" }, h("div", { class: "row" }, icon("doc"), h("button", { class: "btn quiet grow", style: "justify-content:flex-start;text-align:left;font-size:17px", onclick: () => openLesson(it) }, it.title),
      it.done && h("span", { class: "done-mark" }, icon("check", 18)), meter(it.level), h("span", { class: "small muted", text: t("learn_minutes", { n: it.minutes }) })),
      h("div", { class: "small muted", text: t("learn_lesson_note") }))
    : h("div", { class: "item" }, h("div", { class: "row" }, h("span", { class: "name grow", text: it.title }), it.done && h("span", { class: "done-mark" }, icon("check", 18)), meter(it.level)),
      h("div", { class: "muted", text: it.why }),
      h("div", { class: "row" }, h("span", { class: "small muted grow", text: [it.by, it.year, t("kind_" + it.kind), it.minutes ? t("learn_minutes", { n: it.minutes }) : "", it.langs.map(l => l === "es" ? "Español" : "English").join(" / "), it.free ? t("learn_free") : ""].filter(Boolean).join(", ") }),
        h("button", { class: "btn small", onclick: () => setDone(it, !it.done) }, t(it.done ? "learn_undo" : "learn_done")),
        h("button", { class: "btn small sky", onclick: () => openUrl(it.url) }, icon("external", 16), t("open"))));
  const draw = () => {
    clear(body);
    if (tab === "glossary") {
      const terms = data.glossary.filter(g => !q || (g.term + " " + g.short).toLowerCase().includes(q));
      body.append(terms.length ? h("div", { class: "list" }, terms.map(g => h("div", { class: "item" }, h("span", { class: "name", text: g.term }), h("span", { class: "muted", text: g.short }))))
        : h("p", { class: "muted", text: t("learn_nothing") }));
      return;
    }
    if (path) {
      const p = data.paths.find(x => x.id === path), items = p.items.filter(fits);
      body.append(h("button", { class: "btn quiet", onclick: () => { path = null; draw(); } }, icon("back", 18), t("learn_all_paths")),
        h("h2", { style: "font:600 24px/1.2 var(--display);margin:10px 0 4px", text: p.name }), h("p", { class: "muted", style: "margin-bottom:10px", text: p.blurb }),
        items.length ? h("div", { class: "list" }, items.map(itemRow)) : h("p", { class: "muted", text: t("learn_nothing") }));
      return;
    }
    const rows = data.paths.map(p => ({ p, items: p.items.filter(fits) })).filter(x => x.items.length);
    if (q) {                                  // searching: show the matching things themselves, once each
      const seen = new Set(), found = [];
      for (const x of rows) for (const it of x.items) if (!seen.has(it.ref)) { seen.add(it.ref); found.push(it); }
      body.append(found.length ? h("div", { class: "list" }, found.map(itemRow)) : h("p", { class: "muted", text: t("learn_nothing") }));
      return;
    }
    body.append(rows.length ? h("div", { style: "border-top:1px solid var(--line)" }, rows.map(({ p, items }) => h("button", { class: "path-row", onclick: () => { path = p.id; draw(); view.scrollTop = 0; } },
      h("span", {}, h("span", { class: "name", text: p.name }), h("span", { class: "muted", style: "display:block", text: p.blurb })),
      h("span", { class: "small muted", text: t("learn_count", { done: items.filter(i => i.done).length, n: items.length }) }))))
      : h("p", { class: "muted", text: t("learn_nothing") }));
  };
  wrap.append(
    h("div", { class: "row", style: "margin-bottom:12px" },
      seg([["paths", t("learn_paths")], ["glossary", t("learn_glossary", { n: data.counts.terms })]], tab, v => { tab = v; draw(); }),
      h("label", { class: "search grow", style: "margin:0;min-width:200px" }, icon("search", 18), h("input", { type: "search", placeholder: t("learn_search"), "aria-label": t("learn_search"), oninput: e => { q = e.target.value.trim().toLowerCase(); draw(); } }))),
    h("div", { class: "row", style: "margin-bottom:14px" }, h("span", { class: "small muted", text: t("learn_level") }),
      seg([[0, t("learn_any")], ...data.levels.map(l => [l.id, l.name])], level, v => { level = v; draw(); })),
    body,
    h("p", { class: "small muted", style: "margin-top:22px", text: t("learn_note", { date: data.checked, lessons: data.counts.lessons, links: data.counts.links }) + (data.saves_progress ? "" : " " + t("learn_forget")) }));
  draw();
};

/* ======================= Settings ======================= */
SCREENS.settings = async view => {
  const wrap = page(view, t("set_title"), null);
  const [settings, priv, provs, voice] = await Promise.all([api("/api/settings"), api("/api/privacy"), api("/api/providers"), api("/api/voice")]);
  const post = (path, body) => guard(async () => { await api(path, { body }); await refreshStatus(); })();
  // --- look
  wrap.append(sec(t("set_look"), null,
    h("div", { class: "row" }, h("span", { style: "min-width:110px", text: t("set_language") }), seg([["en", "English"], ["es", "Español"]], S.lang, v => setLang(v))),
    h("div", { class: "row", style: "margin-top:10px" }, h("span", { style: "min-width:110px", text: t("set_theme") }), seg([["auto", t("theme_auto")], ["day", t("theme_day")], ["night", t("theme_night")]], S.theme, v => setTheme(v)))));
  // --- privacy
  const notes = h("textarea", { rows: "4" }), ctxBox = h("div", { class: "attach-chips" }), ctxFile = h("input", { type: "file", multiple: true });
  const loadCtx = async () => {
    const r = await api("/api/context");
    add(clear(ctxBox), r.files.length ? r.files.map(f => { const n = typeof f === "string" ? f : f.name; return h("span", { class: "chip" }, icon("doc", 15), n, h("button", { "aria-label": t("remove_name", { name: n }), onclick: guard(async () => { await api("/api/context/" + encodeURIComponent(n), { method: "DELETE" }); loadCtx(); }) }, "×")); })
      : h("span", { class: "small muted", text: t("set_ctx_none") }));
  };
  ctxFile.addEventListener("change", guard(async () => { for (const f of ctxFile.files) await api("/api/context", { body: { name: f.name, content_base64: await fileBase64(f) } }); ctxFile.value = ""; loadCtx(); }));
  const forget = priv.memory_mode === "forget";
  wrap.append(sec(t("set_privacy"), t("set_privacy_sub"),
    seg([["remember", t("mode_remember")], ["forget", t("mode_forget")]], forget ? "forget" : "remember", async v => { await post("/api/privacy", { memory_mode: v }); renderFoot(); Chat.loadList(); go("settings"); }),
    h("p", { class: "small muted", style: "margin:6px 0 10px", text: t(forget ? "mode_forget_hint" : "mode_remember_hint") }),
    switchRow(t("set_net_default"), t("set_net_default_hint"), priv.internet_default, v => post("/api/privacy", { internet_default: v })),
    switchRow(t("set_logs"), t("set_logs_hint"), priv.keep_logs && !forget, v => post("/api/privacy", { keep_logs: v }), forget),
    switchRow(t("set_local_fetch"), t("set_local_fetch_hint"), settings.allow_local_fetch, v => post("/api/settings", { allow_local_fetch: v })),
    !forget && h("label", { class: "field", style: "margin-top:10px" }, t("set_notes"), h("span", { class: "hint", text: t("set_notes_hint") }), notes,
      h("button", { class: "btn small", style: "align-self:flex-start", onclick: guard(async () => { await api("/api/memory", { method: "PUT", body: { text: notes.value } }); toast(t("saved")); }) }, t("save"))),
    !forget && h("div", { class: "field", style: "margin-top:12px;display:flex;flex-direction:column;gap:6px" }, h("b", { text: t("set_ctx") }), h("span", { class: "small muted", text: t("set_ctx_hint") }), ctxBox, ctxFile),
    h("button", { class: "btn danger", style: "margin-top:14px", onclick: async () => {
      if (!await confirmDialog(t("set_wipe"), t("set_wipe_text"), t("set_wipe"), true)) return;
      try { await api("/api/privacy/wipe", { method: "POST" }); toast(t("set_wiped")); } catch (e) { oops(e); }
      Chat.fresh(); Chat.loadList(); go("settings");
    } }, icon("trash", 18), t("set_wipe"))));
  if (!forget) { api("/api/memory").then(r => { notes.value = r.text || ""; }).catch(() => {}); loadCtx().catch(() => {}); }
  // --- the AI
  wrap.append(sec(t("set_ai"), null,
    h("label", { class: "field" }, t("set_sleep"), h("span", { class: "hint", text: t("set_sleep_hint") }),
      h("select", { onchange: e => post("/api/settings", { idle_sleep_min: +e.target.value }) }, [10, 30, 60, 180, 0].map(n => h("option", { value: n, selected: n === settings.idle_sleep_min }, n ? t("set_sleep_min", { n }) : t("set_sleep_never"))))),
    h("label", { class: "field", style: "margin-top:12px" }, t("set_context"), h("span", { class: "hint", text: t("set_context_hint") }),
      h("select", { onchange: e => post("/api/settings", { context: +e.target.value }) }, [2048, 4096, 8192, 16384, 32768].map(n => h("option", { value: n, selected: n === settings.context }, t("ctx_" + n)))))));
  // --- paid services
  const pName = h("input", { type: "text", placeholder: t("paid_name") }), pUrl = h("input", { type: "text", placeholder: "https://…/v1" }), pKey = h("input", { type: "password", placeholder: t("paid_key"), autocomplete: "off" }), pModel = h("input", { type: "text", placeholder: t("paid_model") });
  const preset = h("select", { onchange: e => { const k = e.target.value; if (k) { pName.value = k.split(" ")[0]; pUrl.value = provs.presets[k]; } } }, h("option", { value: "" }, t("paid_preset")), Object.keys(provs.presets).map(k => h("option", { value: k }, k)));
  const remote = provs.providers.filter(p => p.kind !== "local" && p.kind !== "pool" && p.kind !== "linked");
  wrap.append(sec(t("set_paid"), t("set_paid_sub"),
    remote.length ? h("div", { class: "list" }, remote.map(p => h("div", { class: "item" }, h("div", { class: "row" }, icon("globe"), h("span", { class: "name grow", text: p.name }),
      provs.active === p.name ? h("span", { class: "chip ok", text: t("ai_in_use") }) : h("button", { class: "btn small", onclick: async () => { await post("/api/providers/active", { name: p.name }); go("settings"); } }, t("paid_use")),
      h("button", { class: "icon-btn", "aria-label": t("delete"), onclick: guard(async () => { await api("/api/providers/" + encodeURIComponent(p.name), { method: "DELETE" }); await refreshStatus(); go("settings"); }) }, icon("trash", 16))),
      h("div", { class: "small muted", text: [p.base_url, p.model, p.has_key ? t("paid_has_key") : ""].filter(Boolean).join(", ") })))) : null,
    provs.active !== "local" && h("button", { class: "btn", style: "margin:10px 0", onclick: async () => { await post("/api/providers/active", { name: "local" }); go("settings"); } }, t("paid_back_local")),
    more(t("paid_add"), h("div", { class: "stack" }, preset, pName, pUrl, pKey, pModel,
      h("button", { class: "btn", style: "justify-self:start", onclick: guard(async () => {
        await api("/api/providers", { body: { name: pName.value.trim(), base_url: pUrl.value.trim(), api_key: pKey.value, model: pModel.value.trim() } });
        go("settings");
      }) }, t("save"))))));
  // --- voice
  const ready = voice.installed.ready, can = voice.available.stt && voice.available.tts;
  wrap.append(sec(t("set_voice"), t("set_voice_sub"),
    h("div", { class: "row" }, h("span", { class: "chip " + (ready ? "ok" : "plain"), text: t(ready ? "voice_ready" : can ? "voice_not_yet" : "voice_cannot") }),
      !ready && can && h("button", { class: "btn", onclick: guard(async () => { await Jobs.track(await api("/api/voice/install", { method: "POST" }), { title: t("set_voice") }); if (S.screen === "settings") go("settings"); }) },
        icon("save", 18), t("voice_get") + (voice.choice && voice.choice.plain ? " (" + voice.choice.plain.download + ")" : "")),
      !voice.available.mic && h("span", { class: "small muted", text: t("voice_no_mic") })),
    switchRow(t("voice_speak"), t("voice_speak_hint"), voice.speak_answers, v => post("/api/settings", { voice_speak_answers: v }))));
  // --- updates
  const upd = h("div", {}, spinner());
  wrap.append(sec(t("upd_title"), t("upd_sub"), upd),
    sec(t("nav_about"), null, h("div", { class: "row" }, h("button", { class: "btn", onclick: () => go("about") }, icon("info", 18), t("about_open")),
      h("button", { class: "btn", onclick: () => go("learn") }, icon("book", 18), t("nav_learn")))));
  const drawUpd = (u, checked) => {
    const job = (path, body, title) => guard(async () => { const x = await Jobs.track(await api(path, { method: "POST", ...(body ? { body } : {}) }), { title }); if (x.state === "done") toast(t("upd_done")); loadUpd(); });
    const now = guard(async (path, method) => { await api(path, { method }); toast(t("upd_done")); loadUpd(); });
    const line = (name, value, ...buttons) => h("div", { class: "item" }, h("div", { class: "row" }, h("span", { class: "name", style: "min-width:150px", text: name }), h("span", { class: "muted grow", text: value }), buttons));
    const a = u.app, e = u.engine, im = u.images, c = u.catalog;
    add(clear(upd),
      h("div", { class: "list" },
        line(t("upd_app"), a.version + (checked && !a.latest ? ", " + t("upd_latest") : ""),
          a.latest && h("button", { class: "btn small primary", onclick: job("/api/updates/app", {}, "Datas " + a.latest.version) }, t("upd_to", { v: a.latest.version })),
          (a.older || []).length > 0 && h("button", { class: "btn small", onclick: ev => openMenu(ev.currentTarget, a.older.map(o => ({ label: t("upd_back_to", { v: o.version }), icon: "undo", fn: job("/api/updates/app", { version: o.version }, "Datas " + o.version) }))) }, icon("undo", 16), t("upd_back"))),
        line(t("upd_engine"), e.tag || t("upd_not_installed"),
          e.newer && e.latest && h("button", { class: "btn small", onclick: job("/api/updates/engine", { tag: e.latest }, t("upd_engine")) }, t("upd_to", { v: e.latest })),
          e.previous && h("button", { class: "btn small", onclick: job("/api/updates/engine/rollback", null, t("upd_engine")) }, icon("undo", 16), t("upd_back_to", { v: e.previous })),
          (e.installed || []).length > 1 && h("button", { class: "btn small quiet", onclick: () => now("/api/updates/engine/cleanup", "POST") }, t("upd_cleanup"))),
        line(t("upd_images"), im.tag || t("upd_not_installed"),
          im.previous && h("button", { class: "btn small", onclick: job("/api/updates/images/rollback", null, t("upd_images")) }, icon("undo", 16), t("upd_back_to", { v: im.previous }))),
        line(t("upd_catalog"), t("upd_catalog_value", { date: c.active, n: c.models }),
          (!checked || c.newer) && h("button", { class: "btn small", onclick: () => now("/api/updates/catalog", "POST") }, t("upd_catalog_get")),
          c.source !== "bundled" && h("button", { class: "btn small", onclick: () => now("/api/updates/catalog", "DELETE") }, icon("undo", 16), t("upd_catalog_back")))),
      h("div", { class: "row", style: "margin-top:12px" },
        h("button", { class: "btn", onclick: guard(async ev => { const b = ev.currentTarget; b.disabled = true; try { drawUpd(await api("/api/updates/check", { method: "POST" }), true); } finally { b.disabled = false; } }) }, icon("refresh", 18), t("upd_check")),
        h("span", { class: "small muted", text: u.checked ? t("upd_checked", { when: when(u.checked) }) : "" })),
      (u.errors || []).length > 0 && h("p", { class: "small muted", text: t("upd_errors") + " " + u.errors.map(x => x.split("\n")[0]).join("; ") }),
      (u.history || []).length > 0 && more(t("upd_history"), h("ul", { class: "small muted", style: "padding-left:20px;margin:0" },
        u.history.slice(-8).reverse().map(x => h("li", { text: [when(x.when), x.piece, x.from && x.to ? x.from + " → " + x.to : (x.to || x.note || "")].filter(Boolean).join(", ") })))));
  };
  const loadUpd = async () => { try { drawUpd(await api("/api/updates"), false); } catch (e) { add(clear(upd), h("p", { class: "note bad", text: e.message })); } };
  loadUpd();
};

/* ======================= About ======================= */
SCREENS.about = async view => {
  const s = await api("/api/sources");
  const wrap = page(view, "Datas", s.project.summary);
  const logs = h("pre", { class: "small", style: "white-space:pre-wrap;max-height:260px;overflow:auto" });
  wrap.append(
    kv([[t("about_version"), S.status.version], [t("f_licence"), s.project.license], [t("about_code"), extLink(s.project.repo, s.project.repo)],
      [t("about_privacy"), extLink(t("about_privacy_link"), s.project.repo + "/blob/main/docs/PRIVACY.md")],
      [t("about_folder"), S.status.home]]),
    h("div", { class: "row", style: "margin-top:16px" },
      h("button", { class: "btn", onclick: async () => { Chat.fresh((await Chat.helpers()).guide); go("chat"); } }, icon("info", 18), t("ask_guide")),
      h("button", { class: "btn", onclick: guard(async () => { await api("/api/shortcut/app", { method: "POST" }); toast(t("lib_shortcut_done")); }) }, t("about_shortcut"))),
    sec(t("about_sources"), t("about_sources_sub"), h("div", { class: "list" }, s.sources.map(x => h("div", { class: "item" },
      h("div", { class: "row" }, h("span", { class: "name grow" }, extLink(x.name, x.url)), h("span", { class: "chip plain", text: x.license })),
      h("div", { class: "muted", text: x.role }), h("div", { class: "small muted", text: x.by }))))),
    h("section", { class: "section" }, more(t("about_logs"), h("p", { class: "small muted", text: t("about_logs_hint") }), logs)));
  api("/api/logs").then(r => { logs.textContent = Object.entries(r).map(([k, v]) => "— " + k + " —\n" + (v || t("about_logs_empty"))).join("\n\n"); }).catch(() => {});
};
