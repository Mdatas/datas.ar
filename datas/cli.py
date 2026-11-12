"""`datas` command line.

datas                 → open the web UI (same as `datas serve`)
datas scan            → device specs
datas recommend       → ranked models for this device
datas install <id>    → fetch llama.cpp + the model
datas run [<id>]      → install if needed, then start the local server
datas chat            → terminal chat against whatever is running / the active provider
datas agent "<task>"  → run the built-in agent
datas pool worker     → offer this device's memory to a pool
datas provider …      → manage API-key providers
datas runtime …       → pin/update llama.cpp
datas doctor          → diagnostics
datas selftest        → check that every part of this copy is present and works
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from datas import __version__
from datas.config import Config, home
from datas.orchestrator import Datas

app = typer.Typer(
    add_completion=False, no_args_is_help=False, help="Datas.ar — local AI for everyone."
)
pool_app = typer.Typer(help="Pool several devices into one model.")
provider_app = typer.Typer(help="Remote OpenAI-compatible providers (API keys).")
runtime_app = typer.Typer(help="llama.cpp runtime management.")
catalog_app = typer.Typer(help="Model catalog.")
voice_app = typer.Typer(help="Hearing (whisper.cpp) and speaking (Kokoro).")
images_app = typer.Typer(help="Making images (stable-diffusion.cpp, Z-Image-Turbo).")
app.add_typer(pool_app, name="pool")
link_app = typer.Typer(help="Link your own devices (encrypted): share memory, the AI, chats.")
app.add_typer(link_app, name="link")
app.add_typer(voice_app, name="voice")
app.add_typer(images_app, name="images")
app.add_typer(provider_app, name="provider")
app.add_typer(runtime_app, name="runtime")
app.add_typer(catalog_app, name="catalog")

con = Console()
GiB = 2**30


def _core() -> Datas:
    return Datas()


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context, version: bool = typer.Option(False, "--version", "-V")):
    if version:
        con.print(f"datas {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        # Double-click / Desktop icon: no sub-command. Call the implementation directly — calling the
        # typer-decorated function would pass its OptionInfo default object as the model id.
        from datas.desktop import open_window as _open

        _open(model_id=None)


@app.command("open")
def open_window(
    model: str | None = typer.Option(None, "--model", help="start this installed AI right away"),
    selfcheck: Path | None = typer.Option(
        None,
        "--selfcheck",
        help="open the window, check that it shows the app, write a report to this file, close",
    ),
):
    """Open the Datas window (the default when you double-click the app)."""
    from datas.desktop import open_window as _open

    _open(model_id=model, selfcheck=selfcheck)


@app.command("open-url")
def open_url(url: str, title: str = "Datas.ar"):
    """Open a local web app in its own Datas window (used for third-party tools)."""
    from datas.desktop import open_external

    if not url.startswith(("http://127.0.0.1", "http://localhost")):
        raise typer.BadParameter("only local addresses")
    open_external(url, title)


@app.command("agent-window")
def agent_window():
    """Open the agent in its own window (separate process)."""
    from datas.desktop import open_window as _open

    _open(path="/agent", title="Datas.ar — Agent", width=980, height=760)


@app.command()
def shortcut(
    model: str | None = typer.Option(
        None, "--model", help="installed AI id; omit for the app itself"
    ),
):
    """Create a Desktop shortcut for Datas or for an installed AI."""
    from datas import library, shortcuts

    if model:
        items = {i["model_id"]: i for i in library.installed()}
        if model not in items:
            con.print(f"[red]{model} is not installed[/]")
            raise typer.Exit(1)
        p = shortcuts.create_model_shortcut(model, items[model]["name"])
        library.set_shortcut(model, str(p))
    else:
        p = shortcuts.create_app_shortcut()
    con.print(f"created {p}")


# ---------------------------------------------------------------------------


@app.command()
def scan(as_json: bool = typer.Option(False, "--json")):
    """Show what Datas sees in this device."""
    s = _core().spec(refresh=True)
    if as_json:
        con.print_json(json.dumps(s.to_dict()))
        return
    t = Table(show_header=False, box=None)
    t.add_row("OS", f"{s.os} / {s.arch}  ({s.os_version})")
    t.add_row(
        "CPU",
        f"{s.cpu_name} — {s.cpu_cores_physical}c/{s.cpu_cores_logical}t  [{' '.join(s.cpu_flags)}]",
    )
    t.add_row("RAM", f"{s.ram_gib:.1f} GiB total, {s.ram_available / GiB:.1f} GiB available now")
    for g in s.gpus:
        t.add_row(
            "GPU",
            f"{g.name} — {f'{g.vram_gib:.1f} GiB' if g.vram_gib is not None else 'VRAM unknown'}"
            f"{' (unified)' if g.unified else ''} → {g.backend} [{g.source}]",
        )
    if not s.gpus:
        t.add_row("GPU", "none detected → CPU")
    t.add_row("Disk", f"{s.disk_free_models / GiB:.1f} GiB free for models")
    t.add_row("Form", s.form_factor + (" · on battery" if s.on_battery else ""))
    con.print(t)
    for n in s.notes:
        con.print(f"[yellow]note:[/] {n}")


@app.command()
def recommend(
    context: int | None = None,
    headroom: float | None = typer.Option(None, help="fraction of RAM to keep free, e.g. 0.25"),
    kv: int = typer.Option(16, help="KV cache bits: 16 or 8"),
    role: str = "general",
    want: str = typer.Option("", help="comma-separated capabilities, e.g. coding,vision"),
    pool: bool = False,
    as_json: bool = typer.Option(False, "--json"),
):
    """Rank catalog models against this device and show the pick."""
    core = _core()
    nodes = core.pool_nodes(refresh=True) if pool else None
    rec = core.recommendation(
        headroom=headroom,
        context=context,
        kv_bits=kv,
        role=role,
        want=[w for w in want.split(",") if w] or None,
        pool_nodes=nodes,
    )
    if as_json:
        con.print_json(json.dumps(rec.to_dict()))
        return
    b = rec.budget
    con.print(
        f"Budget: [bold]{b.total_budget / GiB:.1f} GiB[/] (RAM {b.ram_budget / GiB:.1f} + VRAM {b.vram_budget / GiB:.1f}, "
        f"keeping {b.ram_headroom / GiB:.1f} GiB free) · ctx {rec.context} · kv {rec.kv_bits}-bit · backend {b.backend}"
        + (f" · {b.nodes} nodes" if b.nodes > 1 else "")
    )
    d = rec.default
    if not d:
        con.print("[red]No catalog model fits.[/] Lower --headroom or --context, or try --kv 8.")
    else:
        con.print(
            f"\n[bold green]→ {d.name}[/]  {d.quant}  ({d.need.total / GiB:.1f} GiB needed, {d.placement}, {d.speed_class}, {d.fit_level})"
        )
        for r in d.reasons:
            con.print(f"   • {r}")
        for w in d.warnings:
            con.print(f"   [yellow]• {w}[/]")
        con.print(f"   run it:  [bold]datas run {d.model_id} --quant {d.quant}[/]")
    t = Table(title="Fits", box=None)
    for col in ("model", "quant", "needs", "runs", "speed", "fit", "tier"):
        t.add_column(col)
    for c in rec.fits:
        t.add_row(
            c.model_id,
            c.quant,
            f"{c.need.total / GiB:.1f} GiB",
            c.placement,
            c.speed_class,
            c.fit_level,
            "●" * c.quality_tier,
        )
    con.print(t)
    if rec.does_not_fit:
        t2 = Table(title="Doesn't fit (closest first)", box=None)
        for col in ("model", "quant", "needs", "short by", "hint"):
            t2.add_column(col)
        for c in rec.does_not_fit[:8]:
            t2.add_row(
                c.model_id,
                c.quant,
                f"{c.need.total / GiB:.1f} GiB",
                f"{-c.margin / GiB:.1f} GiB",
                c.fallbacks[0] if c.fallbacks else "",
            )
        con.print(t2)


def _progress_printer(label: str):
    last = [0.0]

    def cb(done: int, total: int | None):
        now = time.time()
        if now - last[0] < 0.5 and (total is None or done < total):
            return
        last[0] = now
        if total:
            con.print(
                f"  {label}: {done / GiB:.2f}/{total / GiB:.2f} GiB ({done / total * 100:.0f}%)",
                end="\r",
            )
        else:
            con.print(f"  {label}: {done / 2**20:.0f} MiB", end="\r")

    return cb


@app.command()
def install(model_id: str = typer.Argument(None), quant: str | None = None, vision: bool = False):
    """Download llama.cpp for this device and a model (default: the recommended one)."""
    core = _core()
    from datas.orchestrator import Job

    job = Job(id="cli", kind="model", title="install")
    job.say = lambda m: con.print(m)  # type: ignore[method-assign]
    job.progress = _progress_printer("download")  # type: ignore[method-assign]
    core.ensure_runtime(job)
    if not model_id:
        d = core.recommendation().default
        if not d:
            con.print("[red]Nothing fits; pass a model id explicitly.[/]")
            raise typer.Exit(1)
        model_id, quant = d.model_id, d.quant
    m = core.catalog.get(model_id)
    if not quant:
        same = [c for c in core.recommendation().fits if c.model_id == model_id]
        quant = same[0].quant if same else m.smallest().quant
    path = core.ensure_model(model_id, quant, job, with_vision=vision)
    con.print(f"\n[green]Installed[/] {model_id} {quant} → {path}")


def _datas_is_open(port: int | None = None) -> bool:
    """Is a Datas already answering on this device (the window or the background service)?"""
    import httpx

    try:
        r = httpx.get(
            f"http://127.0.0.1:{port or Config.load().ui_port}/api/status",
            timeout=2,
            trust_env=False,
        )
        return r.status_code == 200 and "version" in r.json()
    except (httpx.HTTPError, ValueError):
        return False


def _run_in_open_datas(
    model_id: str | None, quant: str | None, context: int | None, kv: int, pool: bool, vision: bool
) -> None:
    """Ask the Datas that is already running here to install and start an AI, and follow it."""
    if not model_id or not quant:
        rec = _app_api(
            "GET",
            "/api/recommend",
            params={"kv_bits": kv} | ({"context": context} if context else {}),
        )
        pick = (
            rec.get("default")
            if not model_id
            else next((c for c in rec.get("fits", []) if c["model_id"] == model_id), None)
        )
        if not pick and not model_id:
            con.print("[red]Nothing fits; pass a model id explicitly.[/]")
            raise typer.Exit(1)
        if pick:
            model_id, quant = pick["model_id"], quant or pick["quant"]
    if not quant:
        con.print(f"[red]Say which size of {model_id} to use with --quant.[/]")
        raise typer.Exit(1)
    con.print(
        f"Datas is already running on this device: starting [bold]{model_id}[/] {quant} there."
    )
    job = _app_api(
        "POST",
        "/api/run",
        json={"model_id": model_id, "quant": quant, "context": context, "kv_bits": kv,
              "pool": pool, "with_vision": vision, "starter": False},
    )  # fmt: skip
    last = ""
    while True:
        j = _app_api("GET", f"/api/jobs/{job['id']}")
        line = f"  {j.get('phase') or j.get('state')}" + (
            f" {j['percent']:.0f}%" if j.get("percent") is not None else ""
        )
        if line != last:
            con.print(line)
            last = line
        if j["state"] == "done":
            con.print("[bold green]Ready.[/] The AI is running in Datas on this device.")
            return
        if j["state"] == "error":
            con.print(f"[red]{j.get('error')}[/]")
            raise typer.Exit(1)
        time.sleep(2)


@app.command()
def run(
    model_id: str = typer.Argument(None),
    quant: str | None = None,
    context: int | None = None,
    kv: int = 16,
    pool: bool = False,
    vision: bool = False,
    exact_layers: bool = False,
    custom: Path | None = typer.Option(None, help="run a GGUF file you already have"),
):
    """Install if needed and start the AI. When Datas is already running on this device (its
    window, or the background service), the AI is started there; otherwise it runs here
    until Ctrl-C."""
    if not custom and _datas_is_open():
        _run_in_open_datas(model_id, quant, context, kv, pool, vision)
        return
    core = _core()
    from datas.orchestrator import Job

    job = Job(id="cli", kind="run", title="run")
    job.say = lambda m: con.print(m)  # type: ignore[method-assign]
    job.progress = _progress_printer("download")  # type: ignore[method-assign]
    if custom:
        core.run_custom(custom, context, kv, job=job)
    else:
        if not model_id:
            d = core.recommendation(context=context, kv_bits=kv).default
            if not d:
                con.print("[red]Nothing fits; pass a model id explicitly.[/]")
                raise typer.Exit(1)
            model_id, quant = d.model_id, d.quant
        if not quant:
            rec = core.recommendation(context=context, kv_bits=kv)
            same = [c for c in rec.fits if c.model_id == model_id]
            quant = same[0].quant if same else core.catalog.get(model_id).smallest().quant
        nodes = core.pool_nodes(refresh=True) if pool else None
        core.run(
            model_id, quant, context, kv, nodes, job, exact_layers=exact_layers, with_vision=vision
        )
    con.print(
        f"\n[bold green]Ready.[/] OpenAI-compatible API: {core.server.base_url()}/v1   (Ctrl-C to stop)"
    )
    con.print("Web UI with chat: run `datas serve` in another terminal, or `datas chat` here.")
    try:
        while core.server.running():
            time.sleep(1)
        con.print("[red]llama-server exited.[/]")
        con.print(core.server.log_tail(30))
    except KeyboardInterrupt:
        core.stop()
        con.print("stopped.")


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int | None = None,
    no_browser: bool = False,
    home: str | None = typer.Option(None, help="keep Datas' data in this folder (DATAS_HOME)"),
):
    """Start the web UI + API (default: http://127.0.0.1:8420)."""
    import os

    if home:  # the background service of a copy that keeps its data in a folder of its own
        os.environ["DATAS_HOME"] = home
    if _datas_is_open(port):
        # already running (the window, or the service started twice): nothing to do, and a
        # clean exit, so the system does not keep starting it again
        con.print("Datas is already running on this computer.")
        raise typer.Exit(0)
    from datas.server.app import serve as _serve

    con.print(
        f"Datas.ar {__version__} · UI at http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port or Config.load().ui_port}  (Ctrl-C to quit)"
    )
    _serve(host, port, open_browser=not no_browser)


@app.command()
def stop():
    """Stop the local llama-server started by `datas run` in this process tree (or kill by port)."""
    import psutil

    cfg = Config.load()
    killed = 0
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if "llama-server" in (p.info.get("name") or "") and f"--port {cfg.llama_port}" in cmd:
                p.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    con.print(f"stopped {killed} llama-server process(es)")


@app.command()
def chat(base_url: str | None = None, model: str = "datas", system: str | None = None):
    """Terminal chat through the Datas /v1 proxy (default) or any OpenAI-compatible URL."""
    import httpx

    cfg = Config.load()
    url = (base_url or f"http://127.0.0.1:{cfg.ui_port}/v1").rstrip("/")
    # If the UI server isn't up, talk to llama-server directly.
    try:
        httpx.get(url.replace("/v1", "/api/status"), timeout=2, trust_env=False)
    except httpx.HTTPError:
        url = f"http://127.0.0.1:{cfg.llama_port}/v1"
    con.print(f"chatting with {url} — Ctrl-C to quit")
    messages = [{"role": "system", "content": system}] if system else []
    with httpx.Client(timeout=600, trust_env="127.0.0.1" not in url) as client:
        while True:
            try:
                q = con.input("[bold cyan]you ›[/] ")
            except (KeyboardInterrupt, EOFError):
                break
            if not q.strip():
                continue
            messages.append({"role": "user", "content": q})
            full = ""
            with client.stream(
                "POST",
                f"{url}/chat/completions",
                json={"model": model, "messages": messages, "stream": True},
            ) as r:
                if r.status_code != 200:
                    con.print(f"[red]{r.read().decode()[:400]}[/]")
                    messages.pop()
                    continue
                con.print("[bold green]ai  ›[/] ", end="")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
                    except (KeyError, ValueError, IndexError):
                        continue
                    full += delta
                    sys.stdout.write(delta)
                    sys.stdout.flush()
                print()
            messages.append({"role": "assistant", "content": full})


@app.command()
def agent(
    task: str,
    allow_shell: bool = False,
    no_network: bool = False,
    workspace: Path | None = None,
    base_url: str | None = None,
    model: str = "datas",
    max_steps: int = 40,
    folder: list[Path] = typer.Option(
        [], "--folder", help="a folder of yours the agent may use (repeatable)"
    ),
    ask: str = typer.Option("risky", help="approve actions: all | risky | none"),
    yes: bool = typer.Option(False, "--yes", "-y", help="same as --ask none"),
    devices: bool = typer.Option(
        False, help="may use cameras, printers, boards, home and industrial devices"
    ),
    control: bool = typer.Option(
        False, help="may use the mouse and keyboard (experimental; needs --devices)"
    ),
):
    """Run the built-in agent on a task. Files go to the agent workspace (~/.local/share/datas/agent-workspace)."""
    from datas.agents import AgentConfig, run_agent

    cfg = Config.load()
    url = (base_url or f"http://127.0.0.1:{cfg.ui_port}/v1").rstrip("/")
    sees = False
    if devices and not base_url:  # can the AI that is running look at pictures?
        try:
            sees = bool(_app_api("GET", "/api/things").get("vision"))
        except Exception:  # noqa: BLE001 - the app is not open: the next lines say so
            sees = False
    acfg = AgentConfig(
        base_url=url,
        model=model,
        roots=list(folder),
        allow_shell=allow_shell,
        allow_network=not no_network,
        max_steps=max_steps,
        ask="none" if yes else ask,
        confirm=(None if yes or ask == "none" else (lambda q: typer.confirm(q, default=False))),
        allow_things=devices,
        allow_control=devices and control,
        vision=sees,
    )
    if workspace:
        acfg.workspace = workspace
    con.print(
        f"workspace: {acfg.workspace} · shell: {'on' if allow_shell else 'off'} · network: {'off' if no_network else 'on'}"
    )
    for ev in run_agent(task, acfg):
        kind = ev["type"]
        if kind == "assistant":
            con.print(f"[bold]ai:[/] {ev['content']}")
        elif kind == "tool_call":
            con.print(f"[cyan]→ {ev['name']}[/] {ev['arguments'][:200]}")
        elif kind == "tool_result":
            con.print(f"[dim]{ev['result'][:600]}[/]")
        elif kind == "picture":
            con.print(f"[dim](the AI was shown the picture {ev['name']})[/]")
        elif kind == "final":
            con.print(f"\n[green]done[/] in {ev['step'] + 1} step(s)")
        elif kind == "error":
            con.print(f"[red]error:[/] {ev['error']}")


@app.command()
def bench(model_path: str | None = None, ngl: int = 99):
    """Measure real tokens/s with llama-bench (stops a running server first)."""
    res = _core().bench(model_path, ngl)
    con.print_json(json.dumps(res))


@app.command()
def doctor():
    """Diagnostics: paths, runtime, config, last server log lines."""
    core = _core()
    st = core.status()
    con.print_json(
        json.dumps({k: v for k, v in st.items() if k not in ("installed_models",)}, default=str)
    )
    con.print(f"home: {home()}")
    con.print(f"installed models: {len(st['installed_models'])}")
    for m in st["installed_models"]:
        con.print(f"  {m['model_id']:28s} {m['file']}  {m['bytes'] / GiB:.1f} GiB")
    tail = core.server.log_tail(20)
    if tail:
        con.print("\n[dim]llama-server.log (tail):[/]")
        con.print(tail)


@app.command()
def selftest(as_json: bool = typer.Option(False, "--json")):
    """Check that every part of this copy of Datas is present and works: the window, the
    lessons, writing and reading documents, the encrypted link between devices, the local
    service. Changes nothing, downloads nothing, starts no AI."""
    from datas.selftest import run

    rows = run()
    failed = [r for r in rows if not r[1]]
    if as_json:
        print(json.dumps([{"check": n, "ok": ok, "detail": d} for n, ok, d in rows]))
    else:
        for name, ok, detail in rows:
            con.print(f"{'[green]ok    [/]' if ok else '[red]FAILED[/]'} {name}: {detail}")
        con.print(
            f"\nDatas {__version__}: "
            + (
                "everything is in place."
                if not failed
                else f"{len(failed)} part(s) need attention."
            )
        )
    raise typer.Exit(1 if failed else 0)


# ---------------------------------------------------------------------------
# pool


@pool_app.command("worker")
def pool_worker(port: int | None = None, host: str = "127.0.0.1"):
    """Expert use: run llama.cpp's worker by hand (for your own VPN or SSH tunnel).

    Linked devices (the Devices screen, or `datas link`) do this for you over an encrypted
    link. A worker bound to anything but 127.0.0.1 accepts unencrypted, unauthenticated
    connections from that network.
    """
    from datas.pool.worker import run_worker

    core = _core()
    core.ensure_runtime()
    if host not in ("127.0.0.1", "localhost"):
        con.print(
            "[yellow]Warning:[/] this worker will accept unencrypted connections from the network "
            f"({host}). Use linked devices instead unless the network itself is private."
        )
    raise typer.Exit(run_worker(core.cfg, core.spec(), port, host, log=con.print))


@pool_app.command("discover")
def pool_discover(seconds: float = 3.0):
    """List devices whose memory can be added to this one (linked devices that are online)."""
    nodes = _core().pool_nodes(refresh=True, seconds=seconds)
    if not nodes:
        con.print("no linked device is offering memory right now (see: datas link status)")
        return
    t = Table(box=None)
    for c in ("device", "local endpoint", "llama.cpp", "RAM", "VRAM", "backend"):
        t.add_column(c)
    for n in nodes:
        t.add_row(
            n.host,
            n.endpoint,
            n.tag or "?",
            f"{n.ram_budget / GiB:.1f} GiB",
            f"{n.vram_budget / GiB:.1f} GiB",
            n.backend,
        )
    con.print(t)


@pool_app.command("nodes")
def pool_nodes(
    set_: str | None = typer.Option(
        None, "--set", help='workers listed by hand: host:port,host:port ("" to clear)'
    ),
):
    """Show, or with --set change, the workers listed by hand (added to linked devices)."""
    cfg = Config.load()
    if set_ is not None and set_ != cfg.pool_nodes:
        cfg.pool_nodes = set_
        cfg.save()
    con.print(f"manual workers: {cfg.pool_nodes or '(none)'}")


# ---------------------------------------------------------------------------
# linked devices (the app must be open: these commands talk to it)


def _app_api(method: str, path: str, **kw):  # noqa: ANN202
    import httpx

    cfg = Config.load()
    try:
        r = httpx.request(
            method, f"http://127.0.0.1:{cfg.ui_port}{path}", timeout=60, trust_env=False, **kw
        )
    except httpx.HTTPError:
        con.print("Datas is not open on this device. Start it first (`datas` or `datas serve`).")
        raise typer.Exit(1) from None
    if r.status_code >= 400:
        try:
            msg = r.json().get("detail") or r.text
        except ValueError:
            msg = r.text
        con.print(f"[red]{msg}[/]")
        raise typer.Exit(1)
    return r.json()


def _print_link(st: dict) -> None:
    d = st["device"]
    con.print(
        f"this device: [bold]{d['name']}[/]  id {d['short_id']}  link {'on' if st['enabled'] else 'off'}"
    )
    if st["enabled"]:
        con.print("addresses: " + ", ".join(st["addresses"]))
    for p in st["peers"]:
        state = "[green]online[/]" if p["online"] else "[dim]offline[/]"
        extra = []
        if p["memory_gib"]:
            extra.append(f"offers {p['memory_gib']} GB")
        if p.get("ai", {}).get("available"):
            extra.append(f"AI: {p['ai'].get('name') or 'yes'}")
        if p.get("window"):
            extra.append("may open Datas here")
        con.print(f"  {p['name']}  {p['address']}  {state}  {'; '.join(extra)}")
    if not st["peers"]:
        con.print("  (no linked devices yet)")


@link_app.command("status")
def link_status():
    """This device's link, and the devices linked to it."""
    _print_link(_app_api("GET", "/api/link", params={"refresh": 1}))


@link_app.command("code")
def link_code():
    """Show an address and a one-time code; type them on the other device within ten minutes."""
    st = _app_api("POST", "/api/link/pairing")
    pr = st["pairing"]
    con.print(
        "On the other device, open Datas → Devices (on a phone: My computers → Link a "
        "computer), and type:"
    )
    con.print(f"  address: [bold]{(pr['addresses'] or ['(no network address found)'])[0]}[/]")
    con.print(
        f"  code:    [bold]{pr['code']}[/]   (valid {pr['expires_in'] // 60} minutes, works once)"
    )


@link_app.command("pair")
def link_pair(address: str, code: str):
    """Link to a device that is showing ADDRESS and CODE."""
    r = _app_api("POST", "/api/link/pair", json={"address": address, "code": code})
    con.print(f"[green]Linked[/] with {r['peer']['name']} ({r['peer']['short_id']}).")


@link_app.command("unlink")
def link_unlink(name_or_id: str):
    """Remove a linked device (by name or by the start of its id)."""
    st = _app_api("GET", "/api/link")
    key = name_or_id.lower().replace("-", "")
    for p in st["peers"]:
        if p["name"].lower() == name_or_id.lower() or p["id"].startswith(key):
            _app_api("DELETE", f"/api/link/peers/{p['id']}")
            con.print(f"unlinked {p['name']}")
            return
    con.print("no linked device matches")
    raise typer.Exit(1)


def _linked(name_or_id: str) -> dict:
    """The linked device called NAME (or whose id starts with it)."""
    st = _app_api("GET", "/api/link")
    key = name_or_id.lower().replace("-", "")
    for p in st["peers"]:
        if p["name"].lower() == name_or_id.lower() or p["id"].startswith(key):
            return p
    names = ", ".join(f'"{p["name"]}"' for p in st["peers"]) or "none yet"
    con.print(f"no linked device matches. Linked: {names}")
    raise typer.Exit(1)


@link_app.command("window")
def link_window(name_or_id: str, on: str = typer.Argument("on", help="on or off")):
    """Let a linked device open the Datas of THIS computer (on), or stop it (off).

    For a computer without a screen: link your laptop, then `datas-cli link window "Laptop" on`
    here, and on the laptop press Devices → Open its Datas. What arrives that way cannot run
    commands, use this computer's hardware or link other devices."""
    if on.lower() not in ("on", "off"):
        raise typer.BadParameter("say on or off")
    p = _linked(name_or_id)
    r = _app_api("POST", f"/api/link/peers/{p['id']}", json={"window": on.lower() == "on"})
    con.print(
        f"{r['name']} may open the Datas of this computer."
        if r["window"]
        else f"{r['name']} may no longer open the Datas of this computer."
    )


@link_app.command("open")
def link_open(
    name_or_id: str,
    show: bool = typer.Option(True, "--window/--no-window", help="open it in a window"),
):
    """Open the Datas of a linked computer here (it has to allow it: `link window`)."""
    p = _linked(name_or_id)
    r = _app_api("POST", f"/api/link/peers/{p['id']}/open", json={"show": show})
    con.print(
        f"The Datas of {r['name']} is open in its own window."
        if r["shown"]
        else f"The Datas of {r['name']} is at {r['url']} — open that address in a browser."
    )


@link_app.command("sync")
def link_sync():
    """Bring chats in step with the linked devices that are online, now."""
    r = _app_api("POST", "/api/link/sync")
    con.print("synced with: " + (", ".join(r["synced_with"]) or "nobody online"))
    for e in r["errors"]:
        con.print(f"[yellow]{e}[/]")


# ---------------------------------------------------------------------------
# providers


@provider_app.command("list")
def provider_list():
    from datas.providers import all_providers

    cfg = Config.load()
    t = Table(box=None)
    for c in ("name", "kind", "base_url", "model", "key", "active"):
        t.add_column(c)
    for p in all_providers(cfg, False):
        t.add_row(
            p.name,
            p.kind,
            p.base_url,
            p.model,
            "✓" if p.api_key else "—",
            "●" if cfg.provider == p.name else "",
        )
    con.print(t)


@provider_app.command("add")
def provider_add(
    name: str,
    base_url: str,
    model: str = "",
    api_key: str = typer.Option("", prompt=True, hide_input=True),
):
    """Add/update an OpenAI-compatible provider. The key is stored in the local config only."""
    from datas.providers import set_remote

    set_remote(Config.load(), name, base_url, api_key, model)
    con.print(f"saved provider {name}")


@provider_app.command("use")
def provider_use(name: str):
    """Make a provider the active one for the /v1 proxy, chat and agents."""
    cfg = Config.load()
    if name not in ("local", "pool") and cfg.remote(name) is None:
        con.print(f"[red]unknown provider {name}[/]")
        raise typer.Exit(1)
    cfg.provider = name
    cfg.save()
    con.print(f"active provider: {name}")


@provider_app.command("remove")
def provider_remove(name: str):
    from datas.providers import remove_remote

    con.print("removed" if remove_remote(Config.load(), name) else "not found")


# ---------------------------------------------------------------------------
# runtime


@runtime_app.command("info")
def runtime_info():
    from datas.runtime import llamacpp

    cfg = Config.load()
    con.print(f"pinned tag: {cfg.llamacpp_tag or '(none → ' + llamacpp.KNOWN_GOOD_TAG + ')'}")
    d = llamacpp.installed_dir(cfg)
    con.print(f"installed: {d or 'no'}")
    if d:
        con.print(llamacpp.version_string(cfg))


@runtime_app.command("pin")
def runtime_pin(tag: str):
    """Pin a llama.cpp build tag (e.g. b11669). All pool nodes must share one."""
    cfg = Config.load()
    cfg.llamacpp_tag = tag
    cfg.save()
    con.print(f"pinned {tag}; run `datas install` to fetch it")


@runtime_app.command("update")
def runtime_update():
    """Move the pin to the newest llama.cpp build and install it."""
    from datas.runtime import llamacpp

    core = _core()
    tag = llamacpp.latest_tag()
    if not tag:
        con.print("[red]could not reach GitHub to find the latest build[/]")
        raise typer.Exit(1)
    core.cfg.llamacpp_tag = tag
    core.cfg.save()
    con.print(f"newest build: {tag}")
    core.ensure_runtime()


# ---------------------------------------------------------------------------
# catalog


@catalog_app.command("list")
def catalog_list():
    from datas.catalog import load

    t = Table(box=None)
    for c in ("id", "name", "params", "quants", "license", "repo"):
        t.add_column(c)
    for m in load().models:
        t.add_row(
            m.id,
            m.name,
            f"{m.params_b or '?'}B"
            + (f" (A{m.active_params_b})" if m.arch == "moe" and m.active_params_b else ""),
            ", ".join(f"{f.quant} {f.bytes / GiB:.1f}G" for f in m.files),
            m.license,
            m.hf_repo,
        )
    con.print(t)


@catalog_app.command("add")
def catalog_add(
    repo: str,
    file: str,
    model_id: str | None = None,
    name: str | None = None,
    quant: str | None = None,
    license_: str = typer.Option("see-model-card", "--license"),
):
    """Add any Hugging Face GGUF to your personal catalog (size is read from the Hub)."""
    from datas.catalog import add_user_model
    from datas.runtime.downloader import remote_info

    info = remote_info(repo, file)
    if not info.size:
        con.print("[red]could not read the file size from the Hub[/]")
        raise typer.Exit(1)
    q = quant or (file.rsplit("-", 1)[-1].replace(".gguf", "") if "-" in file else "custom")
    mid = model_id or repo.split("/")[-1].lower().replace("-gguf", "")
    entry = {
        "id": mid,
        "name": name or mid,
        "family": "custom",
        "vendor": repo.split("/")[0],
        "license": license_,
        "license_source": "unverified",
        "hf_repo": repo,
        "quality_tier": 3,
        "files": [
            {"quant": q, "path": file, "bytes": info.size, "verified": time.strftime("%Y-%m-%d")}
        ],
    }
    m = add_user_model(entry)
    con.print(f"added {m.id} ({q}, {info.size / GiB:.1f} GiB) → {home() / 'catalog.json'}")


@catalog_app.command("refresh")
def catalog_refresh(
    write: bool = typer.Option(False, help="write updated sizes into the bundled models.json"),
):
    """Re-read every catalog file's size from the Hugging Face API and report drift."""
    from datas.catalog import bundled_path, load
    from datas.runtime.downloader import remote_info

    cat = load()
    drift = 0
    for m in cat.models:
        for f in m.files:
            try:
                info = remote_info(m.hf_repo, f.path)
            except Exception as e:  # noqa: BLE001
                con.print(f"[yellow]{m.id} {f.quant}: {e}[/]")
                continue
            if info.sha256 and info.sha256 != f.sha256:
                if f.sha256:
                    drift += 1
                    con.print(f"[yellow]{m.id} {f.quant}: the file changed on Hugging Face[/]")
                f.sha256 = info.sha256
            if info.size and info.size != f.bytes:
                drift += 1
                con.print(f"[yellow]{m.id} {f.quant}: catalog {f.bytes} → hub {info.size}[/]")
                f.bytes = info.size
                f.verified = time.strftime("%Y-%m-%d")
            elif info.size:
                f.verified = time.strftime("%Y-%m-%d")
        for x in m.extras.values():
            try:
                info = remote_info(m.hf_repo, x.path)
            except Exception as e:  # noqa: BLE001
                con.print(f"[yellow]{m.id} {x.path}: {e}[/]")
                continue
            if info.sha256:
                x.sha256 = info.sha256
            if info.size:
                x.bytes = info.size
    con.print(f"checked; {drift} change(s)")
    if write:
        data = json.loads(bundled_path().read_text())
        by_id = {m.id: m for m in cat.models}
        for entry in data["models"]:
            m = by_id.get(entry["id"])
            if m:
                entry["files"] = [f.model_dump(exclude_none=True) for f in m.files]
                if m.extras:
                    entry["extras"] = {
                        k: v.model_dump(exclude_none=True) for k, v in m.extras.items()
                    }
        data["generated"] = time.strftime("%Y-%m-%d")
        bundled_path().write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        con.print(f"wrote {bundled_path()}")


# ---- voice ---------------------------------------------------------------------


@voice_app.command("status")
def voice_status():
    """Is the voice stack available, which models are installed, what would be picked."""
    core = _core()
    st = core.voice_status()
    con.print_json(json.dumps(st))


@voice_app.command("install")
def voice_install():
    """Download the hearing model chosen for this device and the Kokoro voice."""
    core = _core()
    job = core.start_voice_install_job()
    last = None
    while job.state in ("queued", "running"):
        if job.log and job.log[-1] != last:
            last = job.log[-1]
            con.print(last)
        time.sleep(0.5)
    if job.state == "error":
        con.print(f"[red]{job.error}[/red]")
        raise typer.Exit(1)
    con.print("[green]voice ready[/green]")


@voice_app.command("say")
def voice_say(
    text: str,
    lang: str = typer.Option("en", help="en or es"),
    out: Path = typer.Option(Path("datas-say.wav"), help="WAV file to write"),
    voice: str | None = typer.Option(None, help="Kokoro voice name, e.g. ef_dora"),
):
    """Speak TEXT into a WAV file (downloads the voice on first use)."""
    from datas.engines import voice as ve

    core = _core()
    if not ve.installed()["tts"]:
        ch = core.voice_choice()
        for f in ve.catalog()["text_to_speech"]["files"]:
            con.print(f"downloading {f['name']} ({f['bytes'] / 2**20:.0f} MB)")
            ve._download_url(f["url"], ve.tts_paths()[f["name"]], f["bytes"], f.get("sha256"), None)
        del ch
    out.write_bytes(ve.speak(text, lang, voice))
    con.print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


@voice_app.command("hear")
def voice_hear(
    wav: Path, lang: str | None = typer.Option(None, help="en, es … or omit to auto-detect")
):
    """Transcribe a 16-bit WAV file with the installed hearing model."""
    from datas.engines import voice as ve

    core = _core()
    text = core.hear(ve.pcm_from_wav(wav.read_bytes()), lang)
    con.print(text or "[dim](nothing heard)[/dim]")


# ---- images --------------------------------------------------------------------


@images_app.command("status")
def images_status():
    """Engine/model state and what this device would get."""
    con.print_json(json.dumps(_core().image_status()))


@images_app.command("engine")
def images_engine():
    """Download only the image engine (stable-diffusion.cpp) for this device — no model files."""
    from datas.engines import images as ie

    core = _core()
    exe = ie.ensure_runtime(core.spec(), core.cfg)
    con.print(f"[green]{exe}[/green]")


def _wait(job) -> None:  # noqa: ANN001
    last = None
    while job.state in ("queued", "running"):
        if job.log and job.log[-1] != last:
            last = job.log[-1]
            con.print(last)
        time.sleep(0.5)
    if job.state == "error":
        con.print(f"[red]{job.error}[/red]")
        raise typer.Exit(1)


@images_app.command("setup")
def images_setup():
    """Download the engine and Z-Image-Turbo files for this device and start the server."""
    core = _core()
    _wait(core.start_images_job())
    con.print("[green]image engine running[/green]")


@images_app.command("make")
def images_make(
    prompt: str,
    out: Path = typer.Option(Path("datas-image.png")),
    width: int = 1024,
    height: int = 1024,
    steps: int | None = None,
    seed: int = -1,
):
    """Make one picture (starts the engine if everything is downloaded)."""
    core = _core()
    if not core.sd.running():
        _wait(core.start_images_job())
    job = core.start_generate_job(prompt, "", width, height, steps, seed)
    _wait(job)
    res = job.result or {}
    if res.get("files"):
        from datas.engines import images as ie

        data = (ie.images_dir() / res["files"][0]).read_bytes()
    else:
        import base64 as _b

        data = _b.b64decode(res["b64"][0])
    out.write_bytes(data)
    con.print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


@images_app.command("stop")
def images_stop():
    _core().stop_images()
    con.print("stopped")


# ---- third-party apps -----------------------------------------------------------

tools_app = typer.Typer(help="Third-party AI apps (ComfyUI, FaceFusion, your own recipes).")
app.add_typer(tools_app, name="apps")


@tools_app.command("list")
def apps_list():
    for a in _core().apps.list():
        con.print(
            f"{a['id']:12s} {a['name']:12s} {a['tag']:10s} installed={a['installed']} running={a['running']} · {a['verdict']}: {a['why']}"
        )


@tools_app.command("install")
def apps_install(app_id: str):
    core = _core()
    _wait(core.start_app_job(app_id, install_only=True))
    con.print("[green]installed[/green]")


@tools_app.command("open")
def apps_open(app_id: str):
    """Install if needed, start, and open its window. Ctrl-C stops it."""
    core = _core()
    _wait(core.start_app_job(app_id))
    con.print(core.apps.url(app_id))
    try:
        while core.apps.running(app_id):
            time.sleep(1)
    except KeyboardInterrupt:
        core.apps.stop(app_id)


@tools_app.command("remove")
def apps_remove(app_id: str, keep_models: bool = False):
    con.print("removed" if _core().apps.remove(app_id, keep_models) else "not installed")


# ---------------------------------------------------------------------------
# Datas without a window: start with the computer (Linux), for a Raspberry Pi, a NAS or a
# home server — docs/SMALL_COMPUTERS.md

service_app = typer.Typer(
    help="Start Datas with the computer, without a window (Linux): Raspberry Pi, NAS, home server."
)
app.add_typer(service_app, name="service")


def _service(fn):  # noqa: ANN001, ANN202
    from datas.words import Problem

    try:
        return fn()
    except Problem as e:
        con.print(f"[red]{e.say(Config.load().lang)}[/]")
        raise typer.Exit(1) from None


@service_app.command("install")
def service_install():
    """Start Datas now and every time this computer starts, without a window."""
    from datas import service

    r = _service(service.install)
    con.print(f"service file: {r['file']}")
    if r["started"]:
        con.print(
            "[green]Datas is running in the background[/]"
            + (" and starts with the computer." if r["at_boot"] else ".")
        )
        con.print(
            "Next: `datas-cli run` adds the best AI for this computer; `datas-cli link code` "
            "shows a code to link your phone or another computer."
        )
    for note in r["notes"]:
        con.print(f"[yellow]{note}[/]")
    if not r["started"]:
        raise typer.Exit(1)


@service_app.command("remove")
def service_remove():
    """Stop starting Datas with the computer. Your AIs, chats and settings stay."""
    from datas import service

    r = _service(service.remove)
    con.print("removed" if r["removed"] else "it was not installed")


@service_app.command("status")
def service_status(as_json: bool = typer.Option(False, "--json")):
    """Is the background service installed and running?"""
    from datas import service

    st = _service(service.status)
    if as_json:
        print(json.dumps(st))
        return
    con.print(
        f"installed: {'yes' if st['installed'] else 'no'} · running: "
        f"{'yes' if st['running'] else 'no'} · starts with the computer: "
        f"{'yes' if st['at_boot'] else 'only after you log in'}"
    )


# ---------------------------------------------------------------------------
# hardware: cameras, the screen, printers, boards, home and industrial devices
# (docs/HARDWARE.md). These work on their own; the app does not have to be open.

things_app = typer.Typer(
    help="Cameras, the screen, printers, boards (Arduino…), home and industrial devices."
)
app.add_typer(things_app, name="things")


def _thing(fn, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
    from datas.things import ThingError

    try:
        return fn(*args, **kwargs)
    except ThingError as e:
        con.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None


@things_app.command("list")
def things_list(as_json: bool = typer.Option(False, "--json")):
    """What is plugged into this computer and which connections are set up."""
    from datas import things

    inv = things.inventory()
    if as_json:
        print(json.dumps(inv, indent=1, ensure_ascii=False))
    else:
        con.print(things.describe(inv))
        if not inv["ffmpeg"]["found"]:
            con.print("FFmpeg (needed for the camera) is not here: `datas things ffmpeg` gets it.")


@things_app.command("around")
def things_around(seconds: float = 3.0, as_json: bool = typer.Option(False, "--json")):
    """Devices on this network that announce themselves (nothing is probed)."""
    from datas.things import net

    found = net.around(seconds)
    if as_json:
        print(json.dumps(found, indent=1, ensure_ascii=False))
        return
    for d in found:
        con.print(f"{d['address']:<16} {d['name'] or d.get('host') or '?'} — {d['kind']}")
    if not found:
        con.print("No device announced itself.")


@things_app.command("ffmpeg")
def things_ffmpeg():
    """Fetch FFmpeg once (reads cameras and recordings); checked against its checksum."""
    from datas import programs

    have = programs.ffmpeg()
    if have:
        con.print(f"FFmpeg is here: {have}")
        return
    try:
        con.print(programs.fetch_ffmpeg(_progress_printer("FFmpeg")))
    except RuntimeError as e:
        con.print(f"[red]{e}[/]")
        raise typer.Exit(1) from None


@things_app.command("photo")
def things_photo(
    out: Path = typer.Argument(Path("photo.jpg")),
    camera: str | None = None,
    fetch: bool = typer.Option(False, help="get FFmpeg first if it is missing"),
):
    """Take one picture with a camera of this computer."""
    from datas.things import local

    out.write_bytes(_thing(local.photo, camera, fetch=fetch))
    con.print(f"saved {out}")


@things_app.command("screen")
def things_screen(out: Path = typer.Argument(Path("screen.jpg"))):
    """Save a picture of what is on the screen."""
    from datas.things import local

    out.write_bytes(_thing(local.screenshot))
    con.print(f"saved {out}")


@things_app.command("print")
def things_print(file: Path, printer: str | None = None, copies: int = 1):
    """Print a file on paper."""
    from datas.things import local

    con.print(_thing(local.print_file, file, printer, copies))


@things_app.command("serial")
def things_serial(
    port: str,
    send: str | None = typer.Option(None, help="a line of text to write first"),
    seconds: float = 3.0,
    baud: int = 9600,
):
    """Listen to a board or instrument on a serial port (and optionally write one line)."""
    from datas.things import local

    print(_thing(local.serial_talk, port, send, seconds, baud))


@things_app.command("check")
def things_check(what: str, name: str | None = None):
    """Try a connection that is set up: mqtt | home_assistant | modbus (with --name)."""
    from datas.things import net

    con.print(_thing(net.check, what, name))


if __name__ == "__main__":
    app()
