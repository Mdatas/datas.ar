"use strict";
/* Datas — the agent's window. Shows every step the agent takes, asks before risky actions,
   and keeps the list of tasks it does by itself. Uses the same look as the main window. */
const $=id=>document.getElementById(id); let lang="en";
const ES={t_pc:"Configurar mi PC",t_pc_d:"Pedile que abra tus apps para que inicies sesión, o que deje las cosas como te gustan: modo oscuro, terminaciones de archivo, la barra de tareas, Wi-Fi, impresoras, apps predeterminadas… Pregunta antes de cada cambio, y todo cambio se puede deshacer. Nunca ve ni escribe tus contraseñas: las escribís vos.",t_setup:"Puede configurar esta computadora: abrir mis apps y la configuración, cambiar ajustes del día a día (pregunta antes)",pc_task:"Configurá mi PC: ",t_ask:"Preguntame",t_stop:"Parar",t_mayi:"El agente pide permiso:",t_yes:"Permitir",t_no:"Denegar",t_allowall:"Permitir todo en esta tarea",t_grant:"Puede trabajar en:",t_sched:"Tareas que hace sola",t_sched_d:"Dale un trabajo y una hora: \"todos los lunes a las 9, ordená mis Descargas en carpetas por tipo y escribí un informe corto\". Corre mientras Datas está abierto; si la computadora estaba apagada, se pone al día al arrancar. Los resultados quedan en la bandeja de abajo.",t_task:"Tarea",t_when:"Cuándo",t_last:"Última vez",t_add:"Agregar",t_sched_f:"La tarea nueva usa las carpetas y los permisos marcados arriba. Corre sola, así que no se detiene a preguntar antes de cada paso: esas carpetas y permisos son su límite. Una tarea que corre sola nunca usa el mouse ni el teclado.",t_inbox:"Bandeja — qué hizo",t_agent:"Agente",t_lead:"Un agente es una IA que trabaja paso a paso en una tarea usando herramientas: puede buscar, leer, escribir, ordenar y mover archivos, abrirte cosas y — si lo permitís — buscar en internet, usar tu cámara, impresora y otros aparatos, o ejecutar comandos. Solo toca las carpetas que marcás acá; lo que \"borra\" va a una papelera de la que podés recuperar. Todo lo que hace se muestra abajo.",t_net:"Puede buscar y leer en internet",t_dev:"Puede usar mi cámara, pantalla, impresora y otros aparatos",t_ctl:"Puede usar el mouse y el teclado (experimental — riesgoso)",t_shell:"Puede ejecutar comandos en esta computadora (avanzado — riesgoso)",t_run:"Iniciar",t_steps:"Qué está haciendo el agente",t_files:"Archivos en la carpeta del agente",ph:"Ejemplo: leé todos los archivos de texto de mi carpeta y escribí un resumen de una página llamado RESUMEN.md",folder:"Carpeta del agente: "};
const EN={}; for(const el of document.querySelectorAll("[id^=t_]")) EN[el.id]=el.textContent; EN.ph=$("task").placeholder; EN.folder="Agent folder: ";
const ASK_ES=["antes de tocar mis carpetas, ejecutar comandos, abrir cosas o usar mis aparatos","antes de cada acción","nunca — que lo haga, yo miro"], ASK_EN=[...$("askSel").options].map(o=>o.textContent);
function applyLang(){ const D=lang==="es"?ES:EN; [...$("askSel").options].forEach((o,i)=>o.textContent=(lang==="es"?ASK_ES:ASK_EN)[i]); for(const k of Object.keys(EN)){ if(k==="ph") $("task").placeholder=D.ph; else if(k!=="folder" && $(k)) $(k).textContent=D[k]||EN[k]; } $("langBtn").textContent=lang==="en"?"ES":"EN"; loadFiles(); loadFolders(); loadTasks(); loadInbox(); }
// ---- folders the agent may use (per session) ----
let FOLDERS=[], GRANTED=new Set();
async function loadFolders(){ try{ const r = await (await fetch("/api/agent/folders")).json(); FOLDERS=r.known; r.granted.forEach(g=>GRANTED.add(g)); renderFolders(); }catch(e){} }
function renderFolders(){ const extra=[...GRANTED].filter(g=>!FOLDERS.some(f=>f.path===g)).map(g=>({id:g,name:g,name_es:g,path:g})); $("folderChips").innerHTML = [...FOLDERS, ...extra].map(f=>`<span class="chip ${GRANTED.has(f.path)?"on":""}" data-p="${esc(f.path)}" title="${esc(f.path)}">${esc(lang==="es"?f.name_es:f.name)}</span>`).join(""); $("folderChips").querySelectorAll(".chip").forEach(c=>c.onclick=()=>{ const p=c.dataset.p; if(GRANTED.has(p)) GRANTED.delete(p); else GRANTED.add(p); renderFolders(); }); }
$("addFolder").onclick=async()=>{ const p=$("customFolder").value.trim(); if(!p) return; const r = await fetch("/api/agent/folders/check",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:p})}); if(!r.ok){ alert((await r.json()).detail||"?"); return; } GRANTED.add((await r.json()).path); $("customFolder").value=""; renderFolders(); };
// ---- scheduled tasks ----
async function loadTasks(){ try{ const r = await (await fetch("/api/agent/tasks")).json(); const D=lang==="es"?{day:"todos los días",week:"todas las semanas",hour:"cada hora",once:"una vez",at:"a las",run:"Correr ahora",del:"Quitar",on:"Activa",off:"Pausada",never:"nunca",running:"corriendo…"}:{day:"every day",week:"every week",hour:"every hour",once:"once",at:"at",run:"Run now",del:"Remove",on:"On",off:"Paused",never:"never",running:"running…"};
  $("taskRows").innerHTML = r.tasks.map(t=>`<tr><td><b>${esc(t.title)}</b><div class="fine">${esc(t.task)}</div><div class="fine">${(t.folders||[]).map(esc).join(", ")}</div></td><td>${D[t.every]}${t.every==="week"?" "+t.weekday:""}${t.every!=="hour"?" "+D.at+" "+t.at:""}<div class="fine">${t.enabled?(t.next_due?("→ "+t.next_due.replace("T"," ")):""):D.off}</div></td><td>${t.running?D.running:(t.last_run?new Date(t.last_run*1000).toLocaleString():D.never)}<div class="fine">${esc((t.last_summary||"").slice(0,160))}</div></td><td><button class="small" data-run="${t.id}">${D.run}</button> <button class="small" data-tog="${t.id}" data-en="${t.enabled}">${t.enabled?D.off:D.on}</button> <button class="small danger" data-del="${t.id}">${D.del}</button></td></tr>`).join("") || `<tr><td colspan="4" class="fine">—</td></tr>`;
  $("taskRows").querySelectorAll("[data-run]").forEach(b=>b.onclick=async()=>{ await fetch(`/api/agent/tasks/${b.dataset.run}/run`,{method:"POST"}); setTimeout(loadTasks,1500); setTimeout(loadInbox,4000); });
  $("taskRows").querySelectorAll("[data-tog]").forEach(b=>b.onclick=async()=>{ await fetch(`/api/agent/tasks/${b.dataset.tog}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled:b.dataset.en!=="true"})}); loadTasks(); });
  $("taskRows").querySelectorAll("[data-del]").forEach(b=>b.onclick=async()=>{ await fetch(`/api/agent/tasks/${b.dataset.del}`,{method:"DELETE"}); loadTasks(); });
 }catch(e){} }
$("tEvery").onchange=()=>{ $("tWeekday").style.display=$("tEvery").value==="week"?"":"none"; $("tAt").style.display=$("tEvery").value==="hour"?"none":""; }; $("tEvery").onchange();
$("tAdd").onclick=async()=>{ const title=$("tTitle").value.trim(), task=$("tTask").value.trim(); if(!title||!task) return; const r = await fetch("/api/agent/tasks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title, task, every:$("tEvery").value, at:$("tAt").value||"09:00", weekday:$("tWeekday").value, folders:[...GRANTED], internet:$("netSw").classList.contains("on"), allow_shell:$("shellSw").classList.contains("on"), devices:$("devSw").classList.contains("on")})}); if(!r.ok){ alert((await r.json()).detail||"?"); return; } $("tTitle").value=""; $("tTask").value=""; loadTasks(); };
async function loadInbox(){ try{ const r = await (await fetch("/api/agent/results")).json(); $("inbox").innerHTML = r.results.slice(0,10).map(x=>`<details style="margin:6px 0"><summary>${new Date(x.when*1000).toLocaleString()} — ${esc(x.name)}</summary><div class="res">${esc(x.text)}</div></details>`).join("") || `<p class="fine">—</p>`; }catch(e){} }
function esc(s){ return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
setInterval(()=>{ loadTasks(); }, 60000);
$("langBtn").onclick=()=>{ lang=lang==="en"?"es":"en"; applyLang(); };
const sw=(el)=>el.classList.toggle("on"); $("netSw").onclick=()=>sw($("netSw")); $("shellSw").onclick=()=>{ if(!$("shellSw").classList.contains("on") && !confirm(lang==="es"?"Con esto el agente puede ejecutar comandos reales en tu computadora, sin preguntar. ¿Continuar?":"This lets the agent run real commands on your computer without asking each time. Continue?")) return; sw($("shellSw")); };
// hardware: the mouse and keyboard only make sense together with the other hardware
$("setupSw").onclick=()=>sw($("setupSw"));
$("pcBtn").onclick=()=>{ $("setupSw").classList.add("on"); if($("askSel").value==="none") $("askSel").value="risky"; const pre=lang==="es"?ES.pc_task:"Configure my PC: "; if(!$("task").value.startsWith(pre)) $("task").value=pre+$("task").value; $("task").focus(); };
$("devSw").onclick=()=>{ sw($("devSw")); if(!$("devSw").classList.contains("on")) $("ctlSw").classList.remove("on"); };
$("ctlSw").onclick=()=>{ if(!$("ctlSw").classList.contains("on") && !confirm(lang==="es"?"Con esto el agente puede mover tu mouse y escribir con tu teclado. Pregunta antes de cada acción, salvo que elijas «nunca». Llevar el mouse a una esquina de la pantalla lo detiene. ¿Continuar?":"This lets the agent move your mouse and type on your keyboard. It asks before every action unless you choose “never”. Moving the mouse into a corner of the screen stops it. Continue?")) return; sw($("ctlSw")); if($("ctlSw").classList.contains("on")) $("devSw").classList.add("on"); };
function picture(ev){ const d=document.createElement("div"); d.className="step result"; const im=document.createElement("img"); im.src=ev.url; im.alt=ev.name; const c=document.createElement("div"); c.textContent=ev.name; d.append(im,c); $("steps").appendChild(d); $("steps").scrollTop=1e9; }
function step(cls, text){ const d=document.createElement("div"); d.className="step "+cls; d.textContent=text; $("steps").appendChild(d); $("steps").scrollTop=1e9; }
async function loadFiles(){ try{ const r = await (await fetch("/api/agent/workspace")).json(); $("t_folder").textContent=(lang==="es"?ES.folder:EN.folder)+r.path; $("files").innerHTML = r.files.map(f=>`<li>${esc(f.name)} <span class="fine">(${(f.bytes/1024).toFixed(0)} KB)</span></li>`).join("") || `<li class="fine">—</li>`; }catch(e){} }
let askPoll=null, allowAll=false;
async function pollAsk(){ try{ const r = await (await fetch("/api/agent/approvals")).json(); const q=r.pending[0]; if(!q){ $("askCard").classList.add("hidden"); return; } if(allowAll){ await fetch(`/api/agent/approvals/${q.id}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ok:true})}); return; } $("askCard").dataset.id=q.id; $("askText").textContent=q.text; $("askCard").classList.remove("hidden"); }catch(e){} }
async function answer(ok){ const id=$("askCard").dataset.id; if(!id) return; $("askCard").classList.add("hidden"); await fetch(`/api/agent/approvals/${id}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ok})}); }
$("askYes").onclick=()=>answer(true); $("askNo").onclick=()=>answer(false); $("askAll").onclick=()=>{ allowAll=true; answer(true); };
$("stop").onclick=async()=>{ await fetch("/api/agent/stop",{method:"POST"}); };
document.addEventListener("keydown",e=>{ if(e.key==="Escape" && !$("stop").classList.contains("hidden")) $("stop").click(); });
$("run").onclick=async()=>{
  const task=$("task").value.trim(); if(!task) return; $("run").disabled=true; $("steps").innerHTML=""; allowAll=false; $("stop").classList.remove("hidden"); askPoll=setInterval(pollAsk, 600);
  step("", (lang==="es"?"Tarea: ":"Task: ")+task);
  try{
    const r = await fetch("/api/agent/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({task, internet:$("netSw").classList.contains("on"), allow_shell:$("shellSw").classList.contains("on"), devices:$("devSw").classList.contains("on"), setup:$("setupSw").classList.contains("on"), control:$("ctlSw").classList.contains("on"), folders:[...GRANTED], ask:$("askSel").value})});
    if(!r.ok){ step("error","⚠ "+((await r.json()).detail||r.status)); $("run").disabled=false; return; }
    const rd=r.body.getReader(), dec=new TextDecoder(); let buf="";
    while(true){ const {value,done}=await rd.read(); if(done) break; buf+=dec.decode(value,{stream:true}); let i; while((i=buf.indexOf("\n\n"))>=0){ const chunk=buf.slice(0,i); buf=buf.slice(i+2); const line=chunk.split("\n").find(l=>l.startsWith("data:")); if(!line) continue; let ev; try{ev=JSON.parse(line.slice(5));}catch(e){continue;}
      if(ev.type==="assistant") step("", ev.content); else if(ev.type==="tool_call") step("tool", `→ ${ev.name} ${typeof ev.arguments==="string"?ev.arguments:JSON.stringify(ev.arguments)}`); else if(ev.type==="tool_result") step(ev.result.startsWith("DENIED")||ev.result.startsWith("STOPPED")?"error":"result", ev.result); else if(ev.type==="picture") picture(ev); else if(ev.type==="final") step("final", (lang==="es"?"Listo. ":"Done. ")+(ev.content||"")); else if(ev.type==="error") step("error", "⚠ "+ev.error); } }
  }catch(e){ step("error","⚠ "+e.message); }
  $("run").disabled=false; clearInterval(askPoll); $("askCard").classList.add("hidden"); $("stop").classList.add("hidden"); loadFiles(); loadInbox();
};
applyLang();

// same language and look as the main window
fetch("/api/status").then(r => r.json()).then(s => {
  const dark = s.theme === "night" || (s.theme !== "day" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "night" : "day";
  if (s.lang === "es" && lang !== "es") { lang = "es"; document.documentElement.lang = "es"; applyLang(); }
}).catch(() => {});

/* the AI that is running cannot use tools: say which AI that fits this device can (or that none can) */
async function checkTools(){ try{
  const st = await (await fetch("/api/status")).json(); if(!st.model_id) return;
  const r = await (await fetch("/api/suggest?"+new URLSearchParams({need:"tools", model:st.model_id}))).json();
  if(r.ok) return;
  const es = lang==="es", el=$("toolsHint");
  el.textContent = r.none
    ? (es ? "La IA que está corriendo no fue hecha para usar herramientas, y ninguna que sí lo sea entra en este dispositivo. El agente igual lo intenta, describiéndole las herramientas en texto: más lento y menos seguro." : "The AI that is running was not made to use tools, and none that is fits this device. The agent still tries, describing its tools in plain text: slower and less reliable.")
    : (es ? `La IA que está corriendo no fue hecha para usar herramientas. ${r.name} sí, y entra en este dispositivo (${r.gib} GB${r.installed?", ya está acá":""}). Elegila arriba, en la ventana principal, para mejores resultados.` : `The AI that is running was not made to use tools. ${r.name} is, and fits this device (${r.gib} GB${r.installed?", already here":""}). Choose it in the main window for better results.`);
  el.classList.remove("hidden");
}catch(e){} }
checkTools();
