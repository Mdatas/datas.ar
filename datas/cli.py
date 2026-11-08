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
app.add_typer(pool_app, name="pool")
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
        serve()


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
    """Install if needed, start llama-server, keep it running until Ctrl-C."""
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
def serve(host: str = "127.0.0.1", port: int | None = None, no_browser: bool = False):
    """Start the web UI + API (default: http://127.0.0.1:8420)."""
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
        httpx.get(url.replace("/v1", "/api/status"), timeout=2)
    except httpx.HTTPError:
        url = f"http://127.0.0.1:{cfg.llama_port}/v1"
    con.print(f"chatting with {url} — Ctrl-C to quit")
    messages = [{"role": "system", "content": system}] if system else []
    with httpx.Client(timeout=600) as client:
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
    max_steps: int = 20,
    yes: bool = typer.Option(False, "--yes", "-y", help="don't ask before shell commands"),
):
    """Run the built-in agent on a task. Files go to the agent workspace (~/.local/share/datas/agent-workspace)."""
    from datas.agents import AgentConfig, run_agent

    cfg = Config.load()
    url = (base_url or f"http://127.0.0.1:{cfg.ui_port}/v1").rstrip("/")
    acfg = AgentConfig(
        base_url=url,
        model=model,
        allow_shell=allow_shell,
        allow_network=not no_network,
        max_steps=max_steps,
        confirm=(None if yes else (lambda q: typer.confirm(q, default=False))),
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


# ---------------------------------------------------------------------------
# pool


@pool_app.command("worker")
def pool_worker(port: int | None = None, host: str = "0.0.0.0"):
    """Offer this device's memory to other Datas nodes (ggml-rpc-server + mDNS)."""
    from datas.pool.worker import run_worker

    core = _core()
    core.ensure_runtime()
    raise typer.Exit(run_worker(core.cfg, core.spec(), port, host, log=con.print))


@pool_app.command("discover")
def pool_discover(seconds: float = 3.0):
    """List pool workers on the LAN."""
    nodes = _core().pool_nodes(refresh=True, seconds=seconds)
    if not nodes:
        con.print("no workers found")
        return
    t = Table(box=None)
    for c in ("host", "endpoint", "llama.cpp", "RAM", "VRAM", "backend"):
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
    set_: str = typer.Option("", "--set", help="manual list host:port,host:port (empty to clear)"),
):
    """Show/set manually configured workers (in addition to mDNS)."""
    cfg = Config.load()
    if set_ or set_ == "":
        if set_ != cfg.pool_nodes:
            cfg.pool_nodes = set_
            cfg.save()
    con.print(f"manual workers: {cfg.pool_nodes or '(none)'}")


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
            if info.size and info.size != f.bytes:
                drift += 1
                con.print(f"[yellow]{m.id} {f.quant}: catalog {f.bytes} → hub {info.size}[/]")
                f.bytes = info.size
                f.verified = time.strftime("%Y-%m-%d")
            elif info.size:
                f.verified = time.strftime("%Y-%m-%d")
    con.print(f"checked; {drift} size change(s)")
    if write:
        data = json.loads(bundled_path().read_text())
        by_id = {m.id: m for m in cat.models}
        for entry in data["models"]:
            m = by_id.get(entry["id"])
            if m:
                entry["files"] = [f.model_dump(exclude_none=True) for f in m.files]
        data["generated"] = time.strftime("%Y-%m-%d")
        bundled_path().write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        con.print(f"wrote {bundled_path()}")


if __name__ == "__main__":
    app()
