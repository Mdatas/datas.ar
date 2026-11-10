# Small computers without a screen: Raspberry Pi, home servers, NAS

Datas can run on a small computer that sits in a corner with no screen, keyboard or mouse,
and be used from your phone or from your other computers. That computer then holds the AI,
the chats and the scheduled tasks, and is on all day.

Words used here: **ARM** is the kind of processor in phones, in the Raspberry Pi and in many
small servers ("arm64" or "aarch64" when it is 64-bit). A **NAS** (network-attached storage)
is a box of disks that shares folders on your network. A **service** is a program that
starts with the computer and runs without a window.

## What to expect

Datas does not pretend. A small computer runs small AIs, slowly. Before anything else:

```
datas-cli scan         what this computer has (memory, processor, graphics)
datas-cli recommend    which AIs fit, and which is the best one for it
```

The same plain verdicts as in the window: runs well, runs slowly, does not fit. A second,
stronger computer of yours can lend its AI through the link (see below) — then the small one
is the door and the big one does the thinking.

## Install

| Computer | File |
|---|---|
| Raspberry Pi 4 or 5 with a 64-bit system (Raspberry Pi OS "Bookworm" or newer), other 64-bit ARM boards and servers with Debian 12 / Ubuntu 22.04 or newer | `datas_<version>_arm64.deb` — `sudo apt install ./datas_<version>_arm64.deb` |
| The same, without administrator rights, or another Linux for 64-bit ARM | `datas-<version>-linux-arm64.tar.gz` — unpack, `./install.sh` |
| A small PC (Intel/AMD) used as a server | the normal `datas_<version>_amd64.deb` |

The ARM package has no window of its own inside (that keeps it small and lets it run on
systems without a desktop). On a Raspberry Pi *with* a desktop, the **Datas.ar** entry of the
menu opens Datas in the web browser of the Pi.

A 32-bit system (the old default of Raspberry Pi OS) is not supported.

## Five commands

```
datas-cli service install     Datas starts now and every time the computer starts
datas-cli run                 downloads the best AI for this computer and starts it
datas-cli link code           shows an address and a one-time code
```

Then, on your phone: *Datas app → My computers → Link a computer*, type the address and the
code, and **Open**. You are now using the Datas of the small computer: its chats, its AI,
Add an AI, helpers, documents, Learn.

Or on another computer of yours with Datas: *Devices → I have a code*. After that the chat's
AI menu offers the AI of the small computer, the two keep the same chats, and they can lend
each other memory. See [DEVICES.md](DEVICES.md).

To look after the small computer from that other computer — get it another AI, read what its
scheduled tasks wrote — let it open the small one's Datas. On the small computer, once:

```
datas-cli link window "Laptop" on     "Laptop" is the name of the other computer
```

Then on the laptop: *Devices → the small computer → Open its Datas*. It opens in a window of
its own and says at the bottom whose Datas it is.

```
datas-cli service status      is it installed, running, started with the computer?
datas-cli service remove      stop starting it; AIs, chats and settings stay
```

`datas-cli run` notices that Datas is already running as a service and starts the AI there,
so there is never a second engine beside it.

### On a Windows PC or a Mac

The same is in *Settings → Start Datas with the computer* (or `datas-cli service install`):
on **Windows** it is an entry in your own "Run" list (`HKEY_CURRENT_USER\…\Run`, where every
app that starts with Windows goes) that starts `Datas.exe serve --no-browser` with no window;
on **macOS** a LaunchAgent, `~/Library/LaunchAgents/ar.datas.service.plist`. Both start when
you log in, run as you, need no administrator, and are removed by switching it off (or
`datas-cli service remove`). Opening the Datas window then shows that same running Datas.

### Starting before anyone logs in

A computer without a screen has nobody logging in. `service install` asks the system to start
your services at boot. If the system refuses that to a normal user, Datas says so and shows
the one command that needs the administrator:

```
sudo loginctl enable-linger <your user name>
```

### What the service is

A *user* service of systemd (the part of Linux that starts programs): it runs as you, not as
the administrator. The file is `~/.config/systemd/user/datas.service` and contains one line
that matters: `ExecStart=… datas-cli serve --no-browser`. Nothing outside your own folders is
touched. After upgrading the package: `systemctl --user restart datas`.

## Who can reach it

- The service itself answers **only on the computer it runs on** (`127.0.0.1`). It is not
  open to your network.
- Your phone and your other computers reach it through the **link**: one port (8424),
  encrypted with TLS 1.3, only for the devices you paired with a one-time code.
  → [DEVICES.md](DEVICES.md), [SECURITY.md](SECURITY.md)
- A linked phone — or another computer showing this one's Datas — cannot use this computer's
  camera, printer or other hardware, cannot make the agent run commands, and cannot unlink
  or link devices. Those are done on the computer itself — here, from its command line.
- To use it from outside your home, put your devices on a private network of your own
  (WireGuard, Tailscale). Do not open the port to the internet.

`datas-cli serve --host 0.0.0.0` exists and puts the window on your network **without a
password and without encryption**; it is not needed for any of the above and is not
recommended.

## Hardware on a small computer

Everything in [HARDWARE.md](HARDWARE.md) works the same from the command line and for the
agent: USB cameras, printers the system knows, boards on USB/serial (Arduino, ESP32, Pico),
MQTT, Home Assistant, Modbus, the list of devices on the network.

```
datas-cli things list
datas-cli agent "read the temperature from the board on /dev/ttyACM0 and write it to today.txt" --devices
```

Not there yet, said plainly:

- the Raspberry Pi **camera module** on the ribbon cable (it is not a normal camera to the
  system; a USB camera is);
- the Pi's **GPIO pins** directly — connect a board by USB, or go through MQTT or Home
  Assistant;
- a ready-made app for **Synology, QNAP** or other NAS systems. Datas runs on a NAS where a
  Debian or Ubuntu system for 64-bit ARM or Intel/AMD can be installed (many allow a virtual
  machine or a container); the NAS's shared folders are used like any folder;
- a picture of the screen and the mouse and keyboard (there is no screen).

## How it was tested

Every change builds the ARM package on a 64-bit ARM machine with Ubuntu 22.04, runs the
app's self-test there, starts the service without a window, installs it as a systemd service,
asks it for a pairing code, removes it again, and installs the package on a clean Debian 12
(the system of Raspberry Pi OS "Bookworm"). The weekly test with a real AI also runs on ARM:
it downloads the engine and a small AI and checks a real answer.

**Not tested on the real thing**: a physical Raspberry Pi or NAS. The test machines are ARM
servers in a data centre, which have far more memory and no SD card.
