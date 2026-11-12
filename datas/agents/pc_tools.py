"""The agent's "configure my PC" tools: which apps are installed, open an app or a page of the
system settings, change a short list of everyday settings (and undo them), and hand a sign-in
over to the person.

Its own switch in the agent window ("May configure this computer"). What it will not do, on
purpose:

- **Passwords.** The agent never asks for, reads, stores or types a password. To sign in to
  an app it opens the app and asks the person to type their user and password themselves
  (``sign_in_by_you``). A password given to an AI would sit in its conversation and logs.
- **Settings outside the list.** Only the settings in ``SETTINGS`` are changed directly; each
  is a per-user setting (no administrator rights), its previous value is kept, and
  ``undo_pc_changes`` puts every one back. Anything else: ``open_settings`` opens the right
  page and the person changes it, or — with the mouse-and-keyboard switch — the agent does it
  on screen, asking before every click.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

SYSTEM = platform.system()
# asked about before they run; sign_in_by_you asks on its own (it waits for the person)
ACTS = {"open_app", "open_settings", "change_pc_setting", "undo_pc_changes"}

SYSTEM_HINT = (
    " The user also let you configure this computer: list_apps shows the installed apps, "
    "open_app opens one, open_settings opens a page of the system settings, pc_settings and "
    "change_pc_setting read and change a few everyday settings (undo_pc_changes puts them all "
    "back). NEVER ask for, read or type a password, code or card number: to sign in to an app "
    "or an account, open it and call sign_in_by_you so the person types it themselves. "
    "Change only what the person asked for, one thing at a time, and say what changed."
)

S = {"type": "string"}


# ---------------------------------------------------------------------------
# installed apps
# ---------------------------------------------------------------------------


def _start_menu_dirs() -> list[Path]:
    out = []
    for env in ("APPDATA", "PROGRAMDATA"):
        base = os.environ.get(env)
        if base:
            out.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return out


def installed_apps() -> list[dict]:
    """[{name, open}] — what can be opened, from the places each system lists its apps."""
    apps: dict[str, str] = {}
    if SYSTEM == "Windows":
        for d in _start_menu_dirs():
            for p in d.rglob("*.lnk") if d.is_dir() else []:
                low = p.stem.lower()
                if "uninstall" in low or "desinstalar" in low:
                    continue
                apps.setdefault(p.stem, str(p))
    elif SYSTEM == "Darwin":
        for d in (
            Path("/Applications"),
            Path("/System/Applications"),
            Path.home() / "Applications",
        ):
            for p in d.glob("*.app") if d.is_dir() else []:
                apps.setdefault(p.stem, str(p))
    else:
        dirs = [
            Path.home() / ".local/share/applications",
            Path("/usr/share/applications"),
            Path("/var/lib/flatpak/exports/share/applications"),
            Path.home() / ".local/share/flatpak/exports/share/applications",
        ]
        for d in dirs:
            for p in d.glob("*.desktop") if d.is_dir() else []:
                name, hidden = p.stem, False
                try:
                    for line in p.read_text("utf-8", "replace").splitlines():
                        if line.startswith("Name=") and name == p.stem:
                            name = line[5:].strip()
                        elif line.strip() in ("NoDisplay=true", "Hidden=true"):
                            hidden = True
                except OSError:
                    continue
                if not hidden:
                    apps.setdefault(name, str(p))
    return [{"name": k, "open": v} for k, v in sorted(apps.items(), key=lambda kv: kv[0].lower())]


def _find_app(name: str) -> dict | None:
    want = name.strip().lower()
    apps = installed_apps()
    return next((a for a in apps if a["name"].lower() == want), None) or next(
        (a for a in apps if want and want in a["name"].lower()), None
    )


def _launch(target: str) -> None:
    if SYSTEM == "Windows":
        os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606
    elif SYSTEM == "Darwin":
        subprocess.Popen(["open", target])
    elif target.endswith(".desktop") and shutil.which("gtk-launch"):
        subprocess.Popen(
            ["gtk-launch", Path(target).stem], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    else:
        subprocess.Popen(
            [shutil.which("xdg-open") or "xdg-open", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def list_apps(ctx, search: str = "") -> str:  # noqa: ANN001
    apps = installed_apps()
    if search:
        apps = [a for a in apps if search.lower() in a["name"].lower()]
    if not apps:
        return "No apps found" + (f" matching {search!r}." if search else ".")
    names = [a["name"] for a in apps[:400]]
    return f"{len(apps)} apps:\n" + "\n".join(names)


def open_app(ctx, name: str) -> str:  # noqa: ANN001
    app = _find_app(name)
    if not app:
        return f"No installed app called {name!r}. Use list_apps to see the names."
    _launch(app["open"])
    return f"Opened {app['name']}."


# ---------------------------------------------------------------------------
# pages of the system settings
# ---------------------------------------------------------------------------

# Windows: the ms-settings: addresses documented by Microsoft ("Launch the Windows Settings app").
# Linux: the panels of GNOME Settings (gnome-control-center <panel>).
PAGES: dict[str, dict[str, str]] = {
    "display": {"Windows": "ms-settings:display", "Linux": "display"},
    "sound": {"Windows": "ms-settings:sound", "Linux": "sound"},
    "bluetooth": {"Windows": "ms-settings:bluetooth", "Linux": "bluetooth"},
    "network": {"Windows": "ms-settings:network", "Linux": "network"},
    "wifi": {"Windows": "ms-settings:network-wifi", "Linux": "wifi"},
    "printers": {"Windows": "ms-settings:printers", "Linux": "printers"},
    "mouse": {"Windows": "ms-settings:mousetouchpad", "Linux": "mouse"},
    "keyboard": {"Windows": "ms-settings:typing", "Linux": "keyboard"},
    "default_apps": {"Windows": "ms-settings:defaultapps", "Linux": "default-apps"},
    "apps": {"Windows": "ms-settings:appsfeatures", "Linux": "applications"},
    "startup_apps": {"Windows": "ms-settings:startupapps"},
    "accounts": {"Windows": "ms-settings:emailandaccounts", "Linux": "online-accounts"},
    "sign_in_options": {"Windows": "ms-settings:signinoptions", "Linux": "users"},
    "date_time": {"Windows": "ms-settings:dateandtime", "Linux": "datetime"},
    "language_region": {"Windows": "ms-settings:regionlanguage", "Linux": "region"},
    "privacy": {"Windows": "ms-settings:privacy", "Linux": "privacy"},
    "updates": {"Windows": "ms-settings:windowsupdate"},
    "power": {"Windows": "ms-settings:powersleep", "Linux": "power"},
    "notifications": {"Windows": "ms-settings:notifications", "Linux": "notifications"},
    "colors": {"Windows": "ms-settings:colors", "Linux": "background"},
    "background": {"Windows": "ms-settings:personalization-background", "Linux": "background"},
    "backup": {"Windows": "ms-settings:backup"},
}


def open_settings(ctx, page: str = "") -> str:  # noqa: ANN001
    page = (page or "").strip().lower().replace(" ", "_").replace("-", "_")
    if page and page not in PAGES:
        return f"Unknown page {page!r}. Pages: {', '.join(PAGES)}"
    where = PAGES.get(page, {}).get(SYSTEM) if page else None
    if SYSTEM == "Windows":
        os.startfile(where or "ms-settings:")  # type: ignore[attr-defined]  # noqa: S606
    elif SYSTEM == "Darwin":
        # System Settings itself; its inner pages have no stable public address across versions
        subprocess.Popen(["open", "-b", "com.apple.systempreferences"])
        if page:
            return (
                f"Opened System Settings. Find '{page.replace('_', ' ')}' in its list on the left."
            )
        return "Opened System Settings."
    else:
        prog = shutil.which("gnome-control-center")
        if not prog:
            return "No settings app found that Datas knows how to open (GNOME Settings)."
        subprocess.Popen(
            [prog, *([where] if where else [])],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    if page and not where:
        return f"This system has no '{page}' page; opened the settings at the start."
    return f"Opened the settings{(' at ' + page.replace('_', ' ')) if page else ''}."


# ---------------------------------------------------------------------------
# everyday settings that are changed directly — per user, reversible
# ---------------------------------------------------------------------------

_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_ADVANCED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"


def _reg_get(key: str, name: str) -> int | None:
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return int(winreg.QueryValueEx(k, name)[0])
    except OSError:
        return None


def _reg_set(key: str, name: str, value: int) -> None:
    import winreg  # noqa: PLC0415

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, int(value))


def _win_tell_others(area: str) -> None:
    """Tell open windows a setting changed (WM_SETTINGCHANGE), so most take it at once."""
    try:
        import ctypes  # noqa: PLC0415

        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, area, 0x2, 3000, None)
    except Exception:  # noqa: BLE001
        pass


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"{cmd[0]} failed")
    return r.stdout.strip()


def _bool(s: str) -> bool:
    return s.strip().lower() in ("1", "true", "yes", "on")


def _win_dark_get() -> bool | None:
    v = _reg_get(_PERSONALIZE, "AppsUseLightTheme")
    return None if v is None else v == 0


def _win_dark_set(on: bool) -> None:
    for n in ("AppsUseLightTheme", "SystemUsesLightTheme"):
        _reg_set(_PERSONALIZE, n, 0 if on else 1)
    _win_tell_others("ImmersiveColorSet")


def _mac_dark_get() -> bool:
    return _bool(
        _run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to tell appearance preferences to get dark mode',
            ]
        )
    )


def _mac_dark_set(on: bool) -> None:
    _run(
        [
            "osascript",
            "-e",
            f'tell application "System Events" to tell appearance preferences to set dark mode to {str(on).lower()}',
        ]
    )


def _gs_get(schema: str, key: str) -> str:
    return _run(["gsettings", "get", schema, key]).strip("'")


def _gs_set(schema: str, key: str, value: str) -> None:
    _run(["gsettings", "set", schema, key, value])


def _defaults_get(domain: str, key: str) -> bool:
    try:
        return _bool(_run(["defaults", "read", domain, key]))
    except RuntimeError:
        return False  # not set = the system default, which is off for these


def _defaults_set(domain: str, key: str, on: bool, then: list[str] | None = None) -> None:
    _run(["defaults", "write", domain, key, "-bool", "true" if on else "false"])
    if then:
        subprocess.run(then, capture_output=True, timeout=20, check=False)


# name -> {what, per system: (get() -> bool|None, set(bool))}
SETTINGS: dict[str, dict] = {
    "dark_mode": {
        "what": "Dark colours for windows and apps",
        "Windows": (_win_dark_get, _win_dark_set),
        "Darwin": (_mac_dark_get, _mac_dark_set),
        "Linux": (
            lambda: _gs_get("org.gnome.desktop.interface", "color-scheme") == "prefer-dark",
            lambda on: _gs_set(
                "org.gnome.desktop.interface", "color-scheme", "prefer-dark" if on else "default"
            ),
        ),
    },
    "show_file_extensions": {
        "what": "Show the ending of file names (.pdf, .docx…)",
        "Windows": (
            lambda: (lambda v: None if v is None else v == 0)(_reg_get(_ADVANCED, "HideFileExt")),
            lambda on: (
                _reg_set(_ADVANCED, "HideFileExt", 0 if on else 1),
                _win_tell_others("ShellState"),
            ),
        ),
        "Darwin": (
            lambda: _defaults_get("NSGlobalDomain", "AppleShowAllExtensions"),
            lambda on: _defaults_set(
                "NSGlobalDomain", "AppleShowAllExtensions", on, ["killall", "Finder"]
            ),
        ),
    },
    "show_hidden_files": {
        "what": "Show hidden files in the file manager",
        "Windows": (
            lambda: (lambda v: None if v is None else v == 1)(_reg_get(_ADVANCED, "Hidden")),
            lambda on: (
                _reg_set(_ADVANCED, "Hidden", 1 if on else 2),
                _win_tell_others("ShellState"),
            ),
        ),
        "Darwin": (
            lambda: _defaults_get("com.apple.finder", "AppleShowAllFiles"),
            lambda on: _defaults_set(
                "com.apple.finder", "AppleShowAllFiles", on, ["killall", "Finder"]
            ),
        ),
        "Linux": (
            lambda: _gs_get("org.gtk.Settings.FileChooser", "show-hidden") == "true",
            lambda on: _gs_set(
                "org.gtk.Settings.FileChooser", "show-hidden", "true" if on else "false"
            ),
        ),
    },
    "taskbar_on_the_left": {
        "what": "Windows 11: taskbar buttons on the left instead of the centre",
        "Windows": (
            lambda: (lambda v: None if v is None else v == 0)(_reg_get(_ADVANCED, "TaskbarAl")),
            lambda on: (
                _reg_set(_ADVANCED, "TaskbarAl", 0 if on else 1),
                _win_tell_others("TraySettings"),
            ),
        ),
    },
}


def _undo_path(ctx) -> Path:  # noqa: ANN001
    from datas.config import home  # noqa: PLC0415

    p = home() / "agent" / "pc-changes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _changes(ctx) -> list[dict]:  # noqa: ANN001
    try:
        return json.loads(_undo_path(ctx).read_text("utf-8"))
    except (OSError, ValueError):
        return []


def pc_settings(ctx) -> str:  # noqa: ANN001
    lines = []
    for name, s in SETTINGS.items():
        if SYSTEM not in s:
            continue
        try:
            cur = s[SYSTEM][0]()
            now = "unknown" if cur is None else ("on" if cur else "off")
        except Exception as e:  # noqa: BLE001
            now = f"cannot read ({e})"
        lines.append(f"{name}: {now} — {s['what']}")
    lines.append("Other settings: open_settings(page) with one of " + ", ".join(PAGES))
    return "\n".join(lines)


def change_pc_setting(ctx, name: str, on: bool | str) -> str:  # noqa: ANN001
    s = SETTINGS.get(name)
    if not s or SYSTEM not in s:
        return f"{name!r} cannot be changed directly here. Use open_settings instead."
    want = on if isinstance(on, bool) else _bool(str(on))
    get, put = s[SYSTEM]
    try:
        before = get()
    except Exception:  # noqa: BLE001
        before = None
    if before == want:
        return f"{name} is already {'on' if want else 'off'}."
    put(want)
    log = _changes(ctx)
    log.append({"name": name, "before": before, "after": want, "when": time.time()})
    _undo_path(ctx).write_text(json.dumps(log, indent=1), "utf-8")
    return f"{name} is now {'on' if want else 'off'} (was {'unknown' if before is None else ('on' if before else 'off')}). undo_pc_changes puts it back."


def undo_pc_changes(ctx) -> str:  # noqa: ANN001
    log = _changes(ctx)
    if not log:
        return "Nothing to undo."
    done, first = [], {}
    for c in log:  # the earliest value of each setting is the one to return to
        first.setdefault(c["name"], c["before"])
    for name, before in first.items():
        if before is None:
            done.append(f"{name}: its earlier value was unknown, left as is")
            continue
        try:
            SETTINGS[name][SYSTEM][1](before)
            done.append(f"{name}: back to {'on' if before else 'off'}")
        except Exception as e:  # noqa: BLE001
            done.append(f"{name}: could not undo ({e})")
    _undo_path(ctx).write_text("[]", "utf-8")
    return "\n".join(done)


def sign_in_by_you(ctx, app: str, account: str = "") -> str:  # noqa: ANN001
    """Open the app (if found) and wait until the person has typed their own sign-in."""
    found = _find_app(app)
    if found:
        _launch(found["open"])
    ask: Callable[[str], bool] | None = getattr(ctx, "sign_in_wait", None)
    if ask is None:
        return (
            f"Tell the person: please sign in to {app}{' as ' + account if account else ''} "
            "yourself; the agent does not handle passwords. Then continue."
        )
    ok = ask(
        f"Please sign in to {found['name'] if found else app}"
        f"{' with ' + account if account else ''} yourself — type your user and password there. "
        "The agent never sees or types passwords. Press Allow when you are done, Deny to skip."
    )
    return "The person signed in." if ok else "The person skipped the sign-in."


def confirm_text(name: str, args: dict, lang: str) -> str | None:
    es = lang == "es"
    if name == "open_app":
        return f"Abrir la app {args.get('name')}" if es else f"Open the app {args.get('name')}"
    if name == "open_settings":
        p = args.get("page") or ("inicio" if es else "start")
        return (
            f"Abrir la configuración del sistema: {p}" if es else f"Open the system settings: {p}"
        )
    if name == "change_pc_setting":
        on = _bool(str(args.get("on")))
        what = SETTINGS.get(args.get("name", ""), {}).get("what", args.get("name"))
        state = ("activar" if on else "desactivar") if es else ("turn on" if on else "turn off")
        return f"{state.capitalize()}: {what}"
    if name == "undo_pc_changes":
        return (
            "Deshacer todos los cambios de configuración del agente"
            if es
            else "Undo every setting the agent changed"
        )
    return None


def _schema(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


TOOLS: dict[str, tuple[Callable[..., str], dict]] = {
    "list_apps": (
        list_apps,
        _schema("list_apps", "Names of the apps installed on this computer.", {"search": S}, []),
    ),
    "open_app": (
        open_app,
        _schema("open_app", "Open an installed app by its name.", {"name": S}, ["name"]),
    ),
    "open_settings": (
        open_settings,
        _schema(
            "open_settings",
            "Open a page of the system settings: " + ", ".join(PAGES) + ".",
            {"page": S},
            [],
        ),
    ),
    "pc_settings": (
        pc_settings,
        _schema(
            "pc_settings",
            "Everyday settings the agent can change directly, with their current values.",
            {},
            [],
        ),
    ),
    "change_pc_setting": (
        change_pc_setting,
        _schema(
            "change_pc_setting",
            "Turn one setting from pc_settings on or off. Its earlier value is kept.",
            {"name": {"type": "string", "enum": list(SETTINGS)}, "on": {"type": "boolean"}},
            ["name", "on"],
        ),
    ),
    "undo_pc_changes": (
        undo_pc_changes,
        _schema("undo_pc_changes", "Put back every setting the agent changed.", {}, []),
    ),
    "sign_in_by_you": (
        sign_in_by_you,
        _schema(
            "sign_in_by_you",
            "Open an app and ask the person to sign in to it themselves; waits "
            "until they are done. Use for every sign-in: never handle passwords.",
            {"app": S, "account": S},
            ["app"],
        ),
    ),
}


def schemas(ctx) -> list[dict]:  # noqa: ANN001
    return [s for _, s in TOOLS.values()] if getattr(ctx, "allow_setup", False) else []
