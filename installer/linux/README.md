# Datas.ar for Linux

Pick the file for your distro family from the [Releases](https://github.com/Mdatas/datas.ar/releases) page
(until a release exists: the `desktop-installers` GitHub Action builds them on every push).

| Distro family | File | Install | Uninstall |
|---|---|---|---|
| **Debian, Ubuntu, Mint, Pop!_OS, elementary, Zorin** | `datas_<version>_amd64.deb` | double-click (Software Center) or `sudo apt install ./datas_<version>_amd64.deb` | Software Center, or `sudo apt remove datas` |
| **Arch, Manjaro, EndeavourOS, CachyOS, Garuda** | `datas-bin-<version>-1-x86_64.pkg.tar.zst` | `sudo pacman -U datas-bin-<version>-1-x86_64.pkg.tar.zst` (PKGBUILD in `installer/linux/arch/` for the AUR) | `sudo pacman -R datas-bin` |
| **Anything else** (Fedora, openSUSE, …) | `datas-<version>-linux-x64.tar.gz` | unpack, run `./install.sh` (no root; installs into `~/.local/opt/datas`) | `./install.sh --uninstall` (or `--purge` to delete data too) |

After installing, **Datas.ar** is in your applications menu; `datas-cli` is on the PATH for the terminal.

Upgrading is a clean install: the package manager replaces every program file; your data is never touched.

## Your data

`~/.local/share/Datas` — AI models, chats, notes, the llama.cpp engine, settings, logs
(`logs/datas.log` is the place to look if the window does not open).
Package removal **never** deletes it. To delete everything: *Settings → Forget everything* inside the app,
or `rm -rf ~/.local/share/Datas`.

## GPU

- **NVIDIA**: the normal driver is enough; Datas downloads llama.cpp's CUDA build and its `cudart` libs.
- **AMD / Intel**: Vulkan build (needs the distro's Vulkan driver: `mesa-vulkan-drivers` on the Debian family,
  `vulkan-radeon` / `vulkan-intel` on the Arch family). ROCm builds are used when `backend` is set to `rocm`
  in `~/.local/share/Datas/config.json`.
- **No GPU**: CPU build.

## Making images on Linux

The image engine (stable-diffusion.cpp) is downloaded from its upstream releases, which are built on
Ubuntu 24.04 (glibc 2.39). On older distros (Ubuntu 22.04, Debian 12) that binary may refuse to start
("GLIBC_2.38 not found" in `~/.local/share/Datas/logs/sd-server.log`); the fix is a newer distro
release or building stable-diffusion.cpp locally. Vulkan needs the distro's Vulkan driver
(`mesa-vulkan-drivers` / `vulkan-radeon` / `vulkan-intel`); without one, set the image engine to
"Processor only" in Settings.

## Window toolkit

The Linux build ships its own Qt WebEngine (that is why it is bigger than the Windows one): it does not depend
on your distro's WebKitGTK version, and works on Wayland and X11 alike. If the window still cannot open,
Datas falls back to your browser at http://127.0.0.1:8420.

## Build it yourself

```
pip install ".[qt,voice]" pyinstaller
pyinstaller --noconfirm installer/datas.spec
installer/linux/build-deb.sh 0.3.0            # needs dpkg-deb
```
