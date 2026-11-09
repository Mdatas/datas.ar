# Datas.ar for Windows — one file

The download is **`Datas-Setup-<version>.exe`**. Double-click it and a small window opens:

| Button | What it does |
|---|---|
| **Install** | Installs Datas. If a Datas is already on the PC (any version, any kind of install) it is removed first and a clean copy goes in. Your downloaded AIs, chats, notes and settings are **always kept** and connected to the new install; the finish screen lists what was kept. |
| **Repair** | Same as Install, for when Datas stopped opening: program files and icons are put back; data untouched. |
| **Uninstall** | Removes the program, then asks one thing: *keep my AIs, chats and notes* or *delete everything*. |
| **Exit** | Closes the window, changes nothing. |
| Read me | This text, in the app's language (Spanish or English). |

No other questions are asked. There is no Next/Next/Finish wizard, no folder to pick, no
administrator password: Datas installs into the user's own Programs folder
(`%LOCALAPPDATA%\Programs\Datas`, the per-user equivalent of Program Files that Windows
recommends for apps such as VS Code or Zoom). Desktop icon + Start Menu entry + *Settings → Apps*
entry are created automatically; each AI you install gets its own Desktop icon, and the
uninstaller removes those too.

Windows SmartScreen will warn about an unknown publisher until the exe is code-signed:
*More info → Run anyway*.

## Where things are

| | |
|---|---|
| Program | `%LOCALAPPDATA%\Programs\Datas` (`Datas.exe`, `datas-cli.exe`) |
| Your data: AI models, chats, notes, engine, settings, logs | `%LOCALAPPDATA%\Datas` |
| Log of the last start (if something went wrong) | `%LOCALAPPDATA%\Datas\logs\datas.log` |
| OpenAI-compatible API (for other apps) | `http://127.0.0.1:8420/v1` |

## For power users / IT

- `Datas-Setup.exe /ALLUSERS` installs into `C:\Program Files\Datas` for every account (asks for admin once).
- `Datas-Setup.exe /VERYSILENT` installs without any window (clean install, data kept).
- `unins000.exe /VERYSILENT /KEEPDATA` or `/PURGEDATA` uninstalls without questions.
- `datas-cli.exe` is added to the user PATH: `datas-cli scan`, `datas-cli doctor`, `datas-cli recommend`.
- Developers install from source instead: `pip install -e ".[dev]"` (see CONTRIBUTING.md).

## How it is built

`.github/workflows/windows-installer.yml`: PyInstaller (`datas.spec`) freezes the app so no Python
is needed on the target, a smoke test runs the frozen exe, then Inno Setup compiles `datas.iss`
(the launcher window, clean-install logic and uninstaller live in its `[Code]` section).
Every push produces the exe as a build artifact; tags `v*` attach it to the GitHub Release.

## GPU notes

- **NVIDIA**: only the normal GeForce/Studio driver is needed; Datas downloads the CUDA llama.cpp
  build plus its `cudart` DLLs.
- **AMD / Intel**: Vulkan build (works with the standard driver). ROCm builds exist for supported
  AMD cards; set `backend` to `rocm` in `%LOCALAPPDATA%\Datas\config.json` to prefer them.
- **No GPU / laptop iGPU**: CPU build; expect the small models.
