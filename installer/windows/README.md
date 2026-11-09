# Datas.ar for Windows

## Install (this folder)

1. Double-click **`Install-Datas.cmd`**.
   - It finds Python 3.10+ on your PC or installs Python 3.12 for your user with `winget` (no admin).
   - Installs Datas into `%LOCALAPPDATA%\Datas\app` (a private virtual environment — nothing touches your other Python setups).
   - Creates **Datas.ar** shortcuts on the Desktop and Start Menu, and an entry in *Settings → Apps*.
   - Starts Datas: a console window stays open (close it to stop) and your browser opens `http://127.0.0.1:8420`.
2. In the browser: **Install & run** on the recommended model. First run also downloads llama.cpp
   for your GPU (CUDA build if an NVIDIA card is present, else Vulkan/CPU).

Windows SmartScreen may warn about an unsigned script the first time — *More info → Run anyway*.
The script is plain text; read `Install-Datas.ps1` if you want to see exactly what it does.

## Upgrades = clean install, data always kept

Both installers (`Install-Datas.cmd` and `Datas-Setup-<version>.exe`) do the same thing when a
Datas is already on the PC:

1. **Stop** any running Datas, `llama-server` or pool worker.
2. **Remove the old program** — whichever kind it was: a Setup.exe install in Program Files (it is
   uninstalled silently with `/KEEPDATA`) or a script install in `%LOCALAPPDATA%\Datas\app`
   (the virtual environment is deleted and rebuilt from scratch). Shortcuts and the
   *Settings → Apps* entry of the old copy are removed so there is never two.
3. **Keep the data** in `%LOCALAPPDATA%\Datas` untouched: downloaded AI models (`models\*.gguf`),
   chats, notes (`memory.md`), the llama.cpp engine, settings and logs.
4. **Tell you what was kept** — the installer reports "kept: N AI models, M chats, your notes", and
   the app shows the same notice on its first start, so you decide what to do with it from
   *My AIs* and *Settings* (keep using, delete, or forget).

Nothing is ever deleted by an install. Only the **uninstaller** asks whether to delete the data,
and it only asks when you run it yourself (`Uninstall-Datas.cmd`, or *Settings → Apps → Datas.ar →
Uninstall*). `Install-Datas.ps1 -Uninstall -Purge` deletes everything without asking.

Command line: open a new terminal and type `datas` (the venv's Scripts folder is added to your PATH).

## Where things are

| | |
|---|---|
| App (venv, launcher) | `%LOCALAPPDATA%\Datas\app` |
| Models, llama.cpp, config, logs | `%LOCALAPPDATA%\Datas` |
| UI | http://127.0.0.1:8420 |
| OpenAI-compatible API | http://127.0.0.1:8420/v1 (proxy) · http://127.0.0.1:8421/v1 (engine) |

## Setup.exe (CI)

`.github/workflows/windows-installer.yml` builds a classic **`Datas-Setup-<version>.exe`**
(PyInstaller bundle — no Python needed on the target — wrapped by Inno Setup, per-user, with a
clean uninstall) on every push and attaches it to tagged releases. Scripts: `datas.spec`,
`datas.iss`. That exe is unsigned until a code-signing certificate exists; SmartScreen will show
the usual warning for new publishers.

## GPU notes

- **NVIDIA**: only the normal GeForce/Studio driver is needed. The installer adds NVML support;
  Datas downloads the CUDA llama.cpp build plus its `cudart` DLLs.
- **AMD / Intel**: Vulkan build is used (works with the standard driver). ROCm builds exist for
  supported AMD cards; set `backend` to `rocm` in `%LOCALAPPDATA%\Datas\config.json` to prefer them.
- **No GPU / laptop iGPU**: CPU build; expect the small models.
