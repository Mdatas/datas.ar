## Which file is for my device?

| Your device | Download this file | How to install |
|---|---|---|
| **Windows 10 or 11** (64-bit, Intel or AMD) | `Datas-Setup-{version}.exe` | Open it and follow the steps. Windows may say "unrecognized app" (the file is not signed yet): *More info → Run anyway*. |
| **Android phone or tablet** (Android 8 or newer, 64-bit ARM — almost every phone since 2017) | `Datas-{version}-android.apk` | Open it on the phone; allow "install unknown apps" for your browser or file manager when asked. |
| **Mac with Apple chip** (M1, M2, M3, M4…) | `Datas-{version}.dmg` | Open it and drag Datas to Applications. The first time: right-click Datas → *Open*. Not for Intel Macs. |
| **Linux PC: Ubuntu, Debian, Mint, Pop!_OS** (64-bit Intel/AMD) | `datas_{version}_amd64.deb` | `sudo apt install ./datas_{version}_amd64.deb` |
| **Raspberry Pi 4/5, ARM servers, NAS** (64-bit ARM Linux: Raspberry Pi OS 64-bit, Ubuntu, Debian) | `datas_{version}_arm64.deb` | `sudo apt install ./datas_{version}_arm64.deb` — see docs/SMALL_COMPUTERS.md |
| **Arch Linux, Manjaro, EndeavourOS** (64-bit Intel/AMD) | `datas-bin-{version}-1-x86_64.pkg.tar.zst` | `sudo pacman -U datas-bin-{version}-1-x86_64.pkg.tar.zst` |
| **Any other Linux** (64-bit Intel/AMD) | `datas-{version}-linux-x64.tar.gz` | Unpack it and run `Datas/Datas`. |
| **Any other ARM Linux** (64-bit ARM) | `datas-{version}-linux-arm64.tar.gz` | Unpack it and run `Datas/datas-cli serve`. |
| **iPhone or iPad** | — (no file) | Apple only allows apps signed with an Apple account; see `ios/README.md`. |

Each file has a `.sha256` file next to it with its checksum, and a public record of where it
was built (`gh attestation verify <file> --repo Mdatas/datas.ar`). You do not need either to
install Datas. The **Source code** files at the bottom are for developers, not for installing.

---
