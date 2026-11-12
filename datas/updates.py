"""Updating what can be updated — and going back when something breaks.

Every piece is updated *beside* the old one, never over it, so going back is a switch, not a
repair:

    app       a newer installer from the project's releases page (it keeps AIs, chats and
              settings); earlier installers stay there, and installing one goes back
    engine    llama.cpp builds live in <data>/llamacpp/<tag>/ — the active one is a setting.
              After an update the new engine is tried at once; if it does not start, Datas
              returns to the previous build by itself and says so.
    images    stable-diffusion.cpp builds, the same way (<data>/sdcpp/<tag>/)
    catalog   the list of AIs can be refreshed from the project; the list that came with the
              app is never touched and is one click away
    tools     third-party tools are reinstalled at the version their recipe names; their
              downloaded models are kept

Keeping up to date by itself (Settings → Updates, on unless switched off): while Datas runs it
asks the project's releases page at most every 12 hours. A newer Datas installer is downloaded
and checked against the checksum published with the release, then installed when Datas is
closed (Windows; elsewhere Datas offers to open it) — or at once with "Install now". The list of
AIs is refreshed. The AI engine is not changed by itself (llama.cpp publishes new builds several
times a day): Settings → Updates offers the newest, with a way back. Switched off, Datas makes no
update request unless the user presses "Check for updates".
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from datas import __version__
from datas.config import home, runtime_dir, write_text_safely

REPO = "Mdatas/datas.ar"
API = f"https://api.github.com/repos/{REPO}"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
CATALOG_URL = f"https://raw.githubusercontent.com/{REPO}/main/datas/catalog/models.json"
SD_REPO = "leejet/stable-diffusion.cpp"


def _state_path() -> Path:
    return home() / "updates.json"


def state() -> dict:
    try:
        d = json.loads(_state_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (ValueError, OSError):
        return {}


def _save(d: dict) -> None:
    write_text_safely(_state_path(), json.dumps(d, indent=1))


def _record(piece: str, **entry) -> None:
    d = state()
    hist = d.setdefault("history", [])
    hist.append({"piece": piece, "when": time.time(), **entry})
    d["history"] = hist[-40:]
    _save(d)


def _headers() -> dict:
    h = {"User-Agent": f"datas.ar/{__version__}", "Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4]) or (0,)


# ---------------------------------------------------------------------------
# the app itself
# ---------------------------------------------------------------------------


def asset_for_this_os(assets: list[dict]) -> dict | None:
    """The installer of a release that fits this computer."""
    system = platform.system()
    names = [(a.get("name", ""), a) for a in assets]

    def pick(pred):  # noqa: ANN001, ANN202
        return next((a for n, a in names if pred(n)), None)

    if system == "Windows":
        return pick(lambda n: n.startswith("Datas-Setup-") and n.endswith(".exe"))
    if system == "Darwin":
        return pick(lambda n: n.endswith(".dmg"))
    if Path("/etc/debian_version").exists():
        return pick(lambda n: n.endswith(".deb")) or pick(lambda n: n.endswith(".tar.gz"))
    if Path("/etc/arch-release").exists():
        return pick(lambda n: n.endswith(".pkg.tar.zst")) or pick(lambda n: n.endswith(".tar.gz"))
    return pick(lambda n: n.endswith(".tar.gz"))


def _release_public(rel: dict) -> dict:
    a = asset_for_this_os(rel.get("assets") or [])
    return {
        "version": str(rel.get("tag_name", "")).lstrip("v"),
        "tag": rel.get("tag_name", ""),
        "page": rel.get("html_url") or RELEASES_PAGE,
        "published": rel.get("published_at"),
        "notes": (rel.get("body") or "")[:1500],
        "asset": (
            {
                "name": a["name"],
                "url": a["browser_download_url"],
                "size": a.get("size"),
                "digest": a.get("digest"),
            }
            if a
            else None
        ),
    }


def check_app(client: httpx.Client) -> dict:
    out: dict = {"version": __version__, "latest": None, "older": [], "page": RELEASES_PAGE}
    r = client.get(f"{API}/releases", params={"per_page": 8})
    if r.status_code == 404:
        return out
    r.raise_for_status()
    rels = [x for x in r.json() if not x.get("draft") and not x.get("prerelease")]
    rels.sort(key=lambda x: version_tuple(str(x.get("tag_name", ""))), reverse=True)
    for rel in rels:
        pub = _release_public(rel)
        v = version_tuple(pub["version"])
        if v > version_tuple(__version__) and out["latest"] is None:
            out["latest"] = pub
        elif v < version_tuple(__version__):
            out["older"].append(pub)
    out["older"] = out["older"][:4]
    return out


def downloads_dir() -> Path:
    try:
        from datas.agents.folders import known_folders

        d = next((Path(f["path"]) for f in known_folders() if f["id"] == "Downloads"), None)
    except Exception:  # noqa: BLE001
        d = None
    d = d or (home() / "downloads")
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_installer(asset: dict, job=None, folder: Path | None = None) -> Path:  # noqa: ANN001
    """Fetch an installer into Downloads (resumable name, verified size and checksum)."""
    import hashlib

    dest = (folder or downloads_dir()) / Path(asset["name"]).name
    part = dest.with_suffix(dest.suffix + ".part")
    if job:
        job.phase = "app-download"
        job.say(f"Downloading {asset['name']}")
    h = hashlib.sha256()
    with httpx.Client(
        timeout=httpx.Timeout(60, read=600), follow_redirects=True, headers=_headers()
    ) as c:
        with c.stream("GET", asset["url"]) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0)) or asset.get("size")
            done = 0
            with part.open("wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if job:
                        job.progress(done, total)
    if asset.get("size") and part.stat().st_size != asset["size"]:
        part.unlink(missing_ok=True)
        raise OSError("The download is incomplete. Try again.")
    digest = str(asset.get("digest") or "")
    if digest.startswith("sha256:") and digest[7:] != h.hexdigest():
        part.unlink(missing_ok=True)
        raise ValueError(
            "The downloaded installer does not match the checksum published with the release. "
            "It was deleted; try again."
        )
    part.replace(dest)
    return dest


def open_installer(path: Path) -> str:
    """Start the installer (Windows), open the disk image (macOS), or show the package."""
    system = platform.system()
    if system == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
        return "started"
    if system == "Darwin":
        subprocess.Popen(["open", str(path)])
        return "opened"
    opener = shutil.which("xdg-open")
    if opener:
        target = path if path.suffix == ".deb" else path.parent
        subprocess.Popen(
            [opener, str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    return "shown"


def backup_settings(previous_version: str) -> Path | None:
    """Keep the settings as the previous version left them (one copy per version), so that
    going back to that version can also bring its settings back."""
    src = home() / "config.json"
    if not src.exists() or not previous_version:
        return None
    d = home() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"config-{previous_version}.json"
    if not dest.exists():
        shutil.copy2(src, dest)
        try:
            os.chmod(dest, 0o600)
        except OSError:
            pass
    return dest


# ---------------------------------------------------------------------------
# engines (llama.cpp, stable-diffusion.cpp): side-by-side builds
# ---------------------------------------------------------------------------


def engine_installed_tags() -> list[str]:
    from datas.runtime import llamacpp

    out = []
    for d in sorted(runtime_dir().glob("b*")):
        if d.is_dir() and llamacpp.find_binary(d, "llama-server"):
            out.append(d.name)
    return sorted(out, key=lambda t: int(t[1:]) if t[1:].isdigit() else 0, reverse=True)


def engine_info(core) -> dict:  # noqa: ANN001
    from datas.runtime import llamacpp

    cur = llamacpp.installed_dir(core.cfg)
    st = state().get("engine", {})
    tags = engine_installed_tags()
    prev = st.get("previous")
    return {
        "tag": cur.name if cur else None,
        "tested": llamacpp.KNOWN_GOOD_TAG,
        "installed": tags,
        "previous": prev if prev in tags and (not cur or prev != cur.name) else None,
    }


def _engine_works(core) -> None:  # noqa: ANN001
    """Raises when the active engine cannot even print its version."""
    from datas.runtime import llamacpp

    exe = llamacpp.binary(core.cfg, "llama-server")
    env = os.environ.copy()
    if platform.system() == "Linux":
        env["LD_LIBRARY_PATH"] = str(exe.parent) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    elif platform.system() == "Darwin":
        env["DYLD_LIBRARY_PATH"] = str(exe.parent) + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
    out = subprocess.run(
        [str(exe), "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=str(exe.parent),
    )
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout or "the engine did not start")[-400:])


def _restart_ai(core, was_running: bool) -> None:  # noqa: ANN001
    if was_running and core.can_wake():
        core.wake()


def switch_engine(core, tag: str, job=None) -> dict:  # noqa: ANN001
    """Install ``tag`` beside the current build, make it the active one and try it. If it does
    not work on this device, return to the build that was active and raise with a plain reason."""
    from datas.runtime import llamacpp

    if not re.fullmatch(r"b\d+", tag):
        raise ValueError("an engine version looks like b12345")
    say = job.say if job else print
    cur = llamacpp.installed_dir(core.cfg)
    prev = cur.name if cur else ""
    if prev == tag:
        return {"tag": tag, "changed": False}
    was_running = core.server.running()
    if was_running:
        core.server.stop()
    core.cfg.llamacpp_tag = tag
    try:
        if job:
            job.phase = "runtime"
        llamacpp.install(core.spec(), core.cfg, progress=(job.progress if job else None), log=say)
        if job:
            job.phase = "starting"
        say("Trying the new engine…")
        _engine_works(core)
        _restart_ai(core, was_running)
    except Exception as e:  # noqa: BLE001 - anything wrong → go back
        core.cfg.llamacpp_tag = prev
        core.cfg.save()
        _record("engine", action="update", to=tag, result="rolled_back", error=str(e)[:300])
        say(f"The new engine did not work here ({e}). Going back to {prev or 'none'}.")
        if prev:
            try:
                _restart_ai(core, was_running)
            except Exception:  # noqa: BLE001
                pass
        raise RuntimeError(
            f"Engine {tag} did not work on this device, so Datas went back to "
            f"{prev or 'the previous state'}. Nothing was lost. ({str(e)[:200]})"
        ) from e
    core.cfg.save()
    d = state()
    d.setdefault("engine", {})["previous"] = prev or None
    _save(d)
    _record("engine", action="update", frm=prev, to=tag, result="ok")
    return {"tag": tag, "previous": prev or None, "changed": True}


def rollback_engine(core, job=None) -> dict:  # noqa: ANN001
    prev = engine_info(core)["previous"]
    if not prev:
        raise RuntimeError("There is no earlier engine version on this device to go back to.")
    return switch_engine(core, prev, job)


def remove_old_engines(core) -> dict:  # noqa: ANN001
    """Free disk space: keep the active build and the one before it."""
    info = engine_info(core)
    keep = {info["tag"], info["previous"]}
    freed = 0
    removed = []
    for tag in info["installed"]:
        if tag in keep:
            continue
        d = runtime_dir() / tag
        freed += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        shutil.rmtree(d, ignore_errors=True)
        removed.append(tag)
    return {"removed": removed, "freed_mb": round(freed / 2**20)}


def images_info(core) -> dict:  # noqa: ANN001
    from datas.engines import images

    st = state().get("images", {})
    tags = sorted(
        (d.name for d in images.sd_dir().iterdir() if d.is_dir() and images.binary(d)),
        reverse=True,
    )
    cur = images.active_tag()
    prev = st.get("previous")
    return {
        "tag": cur if cur in tags else None,
        "active": cur,
        "tested": images.KNOWN_GOOD_TAG,
        "installed": tags,
        "previous": prev if prev in tags and prev != cur else None,
    }


def switch_images(core, tag: str, job=None) -> dict:  # noqa: ANN001
    from datas.engines import images

    if not re.fullmatch(r"master-\d+-[0-9a-f]{7}", tag):
        raise ValueError("an image engine version looks like master-920-2f88688")
    prev = images.active_tag()
    if prev == tag and images.installed_dir():
        return {"tag": tag, "changed": False}
    was_running = core.sd.running()
    if was_running:
        core.sd.stop()
    try:
        exe = images.ensure_runtime(core.spec(), core.cfg, job, tag=tag)
        out = subprocess.run(
            [str(exe), "--help"], capture_output=True, timeout=60, cwd=str(exe.parent)
        )
        if out.returncode not in (0, 1):  # --help exits 0 or 1 depending on the build
            raise RuntimeError("the image engine did not start")
    except Exception as e:  # noqa: BLE001
        _record("images", action="update", to=tag, result="rolled_back", error=str(e)[:300])
        raise RuntimeError(
            f"Image engine {tag} did not work on this device; Datas keeps using {prev}. ({str(e)[:200]})"
        ) from e
    core.cfg.sd_tag = "" if tag == images.KNOWN_GOOD_TAG else tag
    core.cfg.save()
    images.set_tag(core.cfg.sd_tag)
    d = state()
    d.setdefault("images", {})["previous"] = prev
    _save(d)
    _record("images", action="update", frm=prev, to=tag, result="ok")
    return {"tag": tag, "previous": prev, "changed": True}


def rollback_images(core, job=None) -> dict:  # noqa: ANN001
    prev = images_info(core)["previous"]
    if not prev:
        raise RuntimeError("There is no earlier image engine on this device to go back to.")
    return switch_images(core, prev, job)


# ---------------------------------------------------------------------------
# the list of AIs (catalog)
# ---------------------------------------------------------------------------


def catalog_info() -> dict:
    from datas import catalog

    bundled = json.loads(catalog.bundled_path().read_text(encoding="utf-8")).get("generated")
    upd = catalog.update_path()
    updated = None
    if upd.exists():
        try:
            updated = json.loads(upd.read_text(encoding="utf-8")).get("generated")
        except ValueError:
            updated = None
    active = catalog.load()
    return {
        "bundled": bundled,
        "updated": updated,
        "active": active.generated,
        "source": "updated" if updated and active.generated == updated else "bundled",
        "models": len(active.models),
    }


def update_catalog(client: httpx.Client | None = None) -> dict:
    """Fetch the project's current list, check it is well-formed, and use it if it is newer.
    The list that came with the app stays in place."""
    from datas import catalog

    own = client is None
    # no token here: the raw file server answers "not found" to tokens it does not expect
    client = client or httpx.Client(
        timeout=40, follow_redirects=True, headers={"User-Agent": f"datas.ar/{__version__}"}
    )
    try:
        r = client.get(CATALOG_URL)
        r.raise_for_status()
        text = r.text
    finally:
        if own:
            client.close()
    new = catalog.Catalog.model_validate_json(text)  # raises on anything malformed
    if not new.models:
        raise ValueError("the downloaded list is empty")
    before = catalog_info()
    if (new.generated or "") <= (before["active"] or ""):
        return {"changed": False, **before}
    write_text_safely(catalog.update_path(), text)
    catalog.reload()
    _record("catalog", action="update", to=new.generated, result="ok")
    return {"changed": True, **catalog_info()}


def rollback_catalog() -> dict:
    from datas import catalog

    catalog.update_path().unlink(missing_ok=True)
    catalog.reload()
    _record("catalog", action="rollback", result="ok")
    return catalog_info()


# ---------------------------------------------------------------------------
# everything at once, for the Settings screen
# ---------------------------------------------------------------------------


def installed(core) -> dict:  # noqa: ANN001
    """What is installed now. No network."""
    d = state()
    tools = []
    for a in core.apps.list():
        if a.get("installed"):
            tools.append(
                {
                    "id": a["id"],
                    "name": a["name"],
                    "installed_tag": a.get("installed_tag"),
                    "recipe_tag": a.get("tag"),
                    "update": a.get("installed_tag") != a.get("tag"),
                }
            )
    return {
        "app": {"version": __version__, "page": RELEASES_PAGE},
        "engine": engine_info(core),
        "images": images_info(core),
        "catalog": catalog_info(),
        "tools": tools,
        "checked": d.get("checked"),
        "history": list(reversed(d.get("history", [])))[:10],
    }


def check(core) -> dict:  # noqa: ANN001
    """Ask the project's pages what the newest versions are (only when the user asks)."""
    from datas.engines import images
    from datas.runtime import llamacpp

    out = installed(core)
    errors = []
    with httpx.Client(timeout=30, follow_redirects=True, headers=_headers()) as c:
        try:
            out["app"] = check_app(c)
        except Exception as e:  # noqa: BLE001
            errors.append(f"app: {e}")
        try:
            latest = llamacpp.latest_tag(c)
            out["engine"]["latest"] = latest
            cur = out["engine"]["tag"]
            out["engine"]["newer"] = bool(
                latest and cur and int(latest[1:]) > int(cur[1:])
            ) or bool(latest and not cur)
        except Exception as e:  # noqa: BLE001
            errors.append(f"engine: {e}")
        try:
            r = c.get(f"https://api.github.com/repos/{SD_REPO}/releases", params={"per_page": 5})
            r.raise_for_status()
            tag = next(
                (
                    x["tag_name"]
                    for x in r.json()
                    if re.fullmatch(r"master-\d+-[0-9a-f]{7}", x.get("tag_name", ""))
                    and x.get("assets")
                ),
                None,
            )
            out["images"]["latest"] = tag
            n = lambda t: int(t.split("-")[1])  # noqa: E731
            out["images"]["newer"] = bool(tag and n(tag) > n(images.active_tag()))
        except Exception as e:  # noqa: BLE001
            errors.append(f"images: {e}")
        try:
            r = httpx.get(
                CATALOG_URL,
                timeout=30,
                follow_redirects=True,
                headers={"User-Agent": f"datas.ar/{__version__}"},
            )
            r.raise_for_status()
            gen = json.loads(r.text).get("generated")
            out["catalog"]["latest"] = gen
            out["catalog"]["newer"] = bool(gen and gen > (out["catalog"]["active"] or ""))
        except Exception as e:  # noqa: BLE001
            errors.append(f"catalog: {e}")
    out["errors"] = errors
    d = state()
    d["checked"] = time.time()
    _save(d)
    out["checked"] = d["checked"]
    return out


# ---------------------------------------------------------------------------
# keeping up to date by itself
# ---------------------------------------------------------------------------

AUTO_EVERY = 12 * 3600


def updates_dir() -> Path:
    d = home() / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ready() -> dict | None:
    """The downloaded, checked installer of a newer Datas, if there is one."""
    r = state().get("ready")
    if not isinstance(r, dict) or not r.get("path"):
        return None
    if (
        version_tuple(str(r.get("version", ""))) <= version_tuple(__version__)
        or not Path(r["path"]).is_file()
    ):
        return None
    return r


def auto_run(core, force: bool = False) -> dict:  # noqa: ANN001
    """One round of keeping up to date; does nothing if switched off or done recently."""
    if not getattr(core.cfg, "auto_update", True):
        return {"skipped": "off"}
    d = state()
    if not force and time.time() - float(d.get("auto_checked") or 0) < AUTO_EVERY:
        return {"skipped": "recent"}
    d["auto_checked"] = time.time()
    _save(d)
    out: dict = {}
    with httpx.Client(timeout=30, follow_redirects=True, headers=_headers()) as c:
        try:
            latest = check_app(c)["latest"]
            asset = latest and latest["asset"]
            # unattended: only an installer whose checksum the release publishes
            if asset and str(asset.get("digest") or "").startswith("sha256:") and not ready():
                path = download_installer(asset, folder=updates_dir())
                d = state()
                d["ready"] = {
                    "version": latest["version"],
                    "path": str(path),
                    "page": latest["page"],
                }
                _save(d)
                _record("app", action="downloaded", to=latest["version"], result="ok")
            out["app"] = latest["version"] if latest else None
        except Exception as e:  # noqa: BLE001
            out["app_error"] = str(e)
        try:
            out["artcraft"] = _auto_artcraft()
        except Exception as e:  # noqa: BLE001
            out["artcraft_error"] = str(e)
        try:
            out["catalog"] = update_catalog()["changed"]
        except Exception as e:  # noqa: BLE001
            out["catalog_error"] = str(e)
    return out


def install_ready(relaunch: bool) -> str:
    """Start the downloaded installer. On Windows it runs without questions and, with
    ``relaunch``, opens Datas again when it is done; the caller then closes Datas."""
    r = ready()
    if not r:
        raise FileNotFoundError("No downloaded update is waiting.")
    path = Path(r["path"])
    if platform.system() == "Windows":
        args = [str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
        if relaunch:
            args.append("/relaunch=1")
        subprocess.Popen(args, creationflags=0x00000008 | 0x00000200, close_fds=True)
        _record("app", action="install", to=r["version"], result="started")
        return "started"
    return open_installer(path)


# The ArtCraft Launcher (getartcraft.com) installs and updates the Craft apps itself; Datas keeps
# the launcher current: once Datas has fetched it, a newer launcher is downloaded and checked
# here, and the person is offered to open its installer (another project's installer is never
# run without them).


def artcraft_got(version: str) -> None:
    d = state()
    d["artcraft"] = {"version": version}
    d.pop("artcraft_ready", None)
    _save(d)


def artcraft_ready() -> dict | None:
    d = state()
    r, have = d.get("artcraft_ready"), (d.get("artcraft") or {}).get("version", "")
    if not isinstance(r, dict) or not Path(str(r.get("path", ""))).is_file():
        return None
    return r if version_tuple(str(r.get("version", ""))) > version_tuple(have) else None


def _auto_artcraft() -> str | None:
    from datas import programs

    have = (state().get("artcraft") or {}).get("version")
    if not have:  # the person never got it through Datas
        return None
    asset = programs.artcraft_launcher_asset()
    new = asset.get("version") or ""
    if version_tuple(new) <= version_tuple(have) or artcraft_ready():
        return None
    if not str(asset.get("digest") or "").startswith("sha256:"):
        return None
    path = download_installer(asset, folder=updates_dir())
    d = state()
    d["artcraft_ready"] = {"version": new, "path": str(path)}
    _save(d)
    _record("artcraft", action="downloaded", to=new, result="ok")
    return new


def open_artcraft_ready() -> str:
    r = artcraft_ready()
    if not r:
        raise FileNotFoundError("No downloaded ArtCraft update is waiting.")
    how = open_installer(Path(r["path"]))
    artcraft_got(r["version"])
    return how
