# Cameras, printers and other hardware

Datas can use the things around your computer when **you** ask it to:

| What | In plain words | Where you use it |
|---|---|---|
| **Camera** | Take one photo and show it to the AI ("what plant is this?") | Chat, agent |
| **Screen** | Take a picture of what is on your screen ("what does this error mean?") | Chat, agent |
| **Printer** | Print an answer or a file on paper | Chat, agent |
| **Boards and instruments** | Read from, and write to, an Arduino, an ESP32, a 3D printer, a lab scale — anything on a USB/serial cable | Tools, agent |
| **Smart home** | Read sensors and switch lights, plugs, heating through your own hub | Agent |
| **Industrial equipment** | Read and write values of PLCs, solar inverters, meters | Agent |
| **Mouse and keyboard** | Let the agent click and type for you (experimental) | Agent |
| **What is on my network** | List printers, shared disks (NAS), Raspberry Pi and other computers, TVs | Tools, agent |

Nothing here works by itself. Datas does not watch the camera, read the screen or listen to
your network in the background. A photo is taken at the moment you press the button, or when
the agent asks you and you say yes.

Words used on this page: an **AI that understands pictures** is one that was downloaded with
its "vision" part (in *Add an AI* they are marked *understands pictures*). A **hub** is the
box or program in your home that all the smart devices report to. The **agent** is the AI
working step by step with tools (see [AGENTS.md](AGENTS.md)).

## In a chat

The camera button, next to the paper clip:

- **A photo from the camera** — takes one picture and attaches it to your message.
- **A picture of my screen** — the Datas window steps aside for a moment, the picture is
  taken, the window comes back with the picture attached. (If Datas is open in a browser
  instead of its own window, it waits three seconds so you can bring up what you want to
  show.)

Both need an AI that understands pictures. If the one running does not, Datas says so and
nothing is taken.

**Print on paper** is the last entry of *Save as* under each answer. The answer becomes a PDF
(kept in your Documents/Datas folder) and is sent to your usual printer.

On Windows, which cannot print a PDF by itself, the answer is printed with its full layout
when the free program LibreOffice is installed, and as plain text when it is not. Text files
and pictures always print there, with nothing to install.

## In Tools

*Tools → Cameras, printers and other hardware* shows what Datas found: cameras, the screen,
printers, boards on serial ports, and whether the mouse and keyboard can be used. Buttons
there let you take a test photo, a test picture of the screen, and listen for three seconds
to what a board is saying. *Look again* refreshes the list after you plug something in.

### FFmpeg

Cameras are read with **FFmpeg**, a free program that reads and writes almost every sound
and video format. Linux usually has it. On Windows and macOS Datas offers to fetch it the
first time it is needed (40 to 140 MB, once). The same copy also lets *Recording to text*
read MP3, M4A and video files.

Where it comes from, exactly: the builds are the ones the open-source project
[static-ffmpeg](https://github.com/zackees/static_ffmpeg) uses, taken by its workflow from
the builders that ffmpeg.org links to (BtbN for Linux, gyan.dev for Windows, evermeet.cx and
osxexperts.net for macOS). Datas downloads from **one fixed commit** of
`github.com/zackees/ffmpeg_bins` and checks the file against the size and SHA-256 recorded
in that commit. A file that differs is deleted and not used. The copy lives in
`<Datas data folder>/programs/ffmpeg`; delete that folder to remove it.
`datas-cli things ffmpeg` fetches it from the command line.

If your system has its own FFmpeg, Datas uses that one and downloads nothing.

## With the agent

Open the agent (*Tools → Open the agent*). Two switches, both off until you turn them on,
and only for that task:

- **May use my camera, screen, printer and other hardware** — the agent gets the tools in
  the table below.
- **May use the mouse and keyboard (experimental — risky)** — see further down.

| The agent can… | Asks first? |
|---|---|
| list what is plugged in and which connections you set up | no |
| list what announces itself on your network | no |
| listen to a board on a serial port | no |
| read MQTT messages, Home Assistant states, Modbus values | no |
| take a photo, take a picture of the screen | **yes** |
| print a file | **yes** |
| write a line to a board | **yes** |
| send an MQTT message, ask Home Assistant to do something | **yes** |
| write a Modbus value | **yes** |
| move the mouse, click, type | **yes**, every single action |

"Asks first" follows the *Ask me* choice in the agent window: with the usual setting the
question appears in plain words — *Print report.pdf on paper (2 copies)*, *Ask Home Assistant
to do light.turn_on on light.kitchen* — and you allow or deny. If you choose *never*, it does
not ask; that is your decision for that task.

Pictures the agent takes are saved in its folder (`photos/`, `screens/`), shown in its window
as they are taken, and handed to the AI if it understands pictures. If it does not, the agent
is told so and tells you where the file is instead of pretending to have seen it. Only the
two newest pictures stay in the AI's working memory; older ones are replaced by a line of
text, because a picture takes much of a small AI's room.

A **task that runs by itself** (the scheduled tasks at the bottom of the agent window) may be
given the hardware switch — "every evening, take a photo of the porch" — and then runs
without asking, within the folders and switches it was given. It can **never** use the mouse
and keyboard.

### Boards on a serial port (Arduino, ESP32, 3D printers, instruments)

Plug the board in; it appears under *Tools* with a plain name when Datas recognises the maker
of its USB part (Arduino, Espressif, Raspberry Pi Pico, CH340, CP210x, FTDI and others).
*Listen for 3 seconds* shows what it is printing. The **speed** ("baud") must be the one set
in the board's program: Arduino examples use 9600, ESP32 and MicroPython boards 115200.

The agent can also write one line at a time and read the answer, which is all most boards
need: `LED ON`, `TEMP?`, a G-code line for a 3D printer. Opening the port restarts most
Arduino boards; Datas waits two seconds before writing. Datas does not upload programs to
boards — that stays with the Arduino program or PlatformIO.

On Linux your user must be allowed to use serial ports (usually: be in the `dialout` group).

### Smart home: MQTT and Home Assistant

Under *Tools → Cameras, printers and other hardware → Home and industrial devices* you give
Datas the address of your own hub once.

- **MQTT** is the way many smart plugs, sensors and small boards pass short messages; the
  **broker** is the program that carries them (Mosquitto, or the one inside Home Assistant).
  Zigbee2MQTT, Tasmota, ESPHome, Shelly and many robots speak it. Give the broker's address,
  and a user and password if it has them.
- **Home Assistant** is a free program that runs a smart home and already knows thousands of
  devices. In it, open your profile → Security, create a *long-lived access token*, and paste
  it into Datas together with the address (for example `http://homeassistant.local:8123`).

*Check* tries the connection and says in one sentence how it went.

### Industrial equipment: Modbus

**Modbus** is the common language of industrial equipment: PLCs (the small computers that run
machines), solar inverters, energy meters, heat pumps. Datas speaks Modbus TCP (over your
network). Add each device with a name, its address, its port (502 unless the manual says
otherwise) and its unit number (1 unless the manual says otherwise).

The agent can read holding and input registers, coils and discrete inputs, and write holding
registers and coils. Which address means what is in the device's manual; Datas does not
guess. Writing changes how a machine behaves, so every write asks first.

Not built in today: Modbus RTU over a serial cable, OPC UA, BACnet, KNX, Zigbee or Z-Wave
radios directly (use Home Assistant or Zigbee2MQTT for those — both are supported above).

### What is on my network

*Tools → … → What is on my network* lists the devices that **announce themselves** (the
"Bonjour"/mDNS and UPnP announcements printers, NAS boxes, Raspberry Pi, TVs and smart-home
devices send): name, address and what it says it is. Datas only listens to these
announcements. It does not scan addresses or try passwords.

A NAS that shows up as *shared folders* is used like any folder: connect it in your system's
file manager, then tick that folder for the agent.

### Mouse and keyboard (experimental)

With its own switch on, the agent can look at the screen, then move the mouse, click, type
and press keys. It is off unless you turn it on, and it is honest work in progress: the small
AIs that fit a normal computer often miss a button when they have to find it in a picture.

What keeps it in check:

- every action asks first (unless you chose *never*);
- **moving the mouse into a corner of the screen stops it at once**;
- the agent must look at the screen before it may click, and can only click inside the
  picture it was shown;
- it is never available to a task that runs by itself, nor from a linked phone.

It works on Windows, on macOS (the system asks you to allow Datas under *Privacy &
Security → Accessibility*) and on Linux with X11. It does not work on Linux with Wayland.

## What stays safe

- **Off by default, per task.** The agent has no hardware tool at all until you switch it on,
  and the switch does not carry over to the next task.
- **A linked phone cannot reach any of it.** Everything on this page is refused when Datas is
  opened from a phone (see [DEVICES.md](DEVICES.md)): a lost phone must not be a way to look
  through your computer's camera or switch things in your home. A phone also cannot give a
  scheduled task the hardware switch.
- **Nothing leaves the computer** unless the AI you chose is an online service: a photo
  attached to a chat goes where that chat goes. With an AI running on this device, it stays
  on this device.
- **Passwords and tokens** for your broker and Home Assistant are kept in
  `<Datas data folder>/things.json`, readable only by your user, and are never shown again in
  the window (it only says that one is saved). Leave the field empty to keep it; type `-` to
  remove it; save the connection with an empty address to forget it altogether.
- **Your system's own permissions still apply.** macOS asks before Datas may use the camera,
  record the screen or control the computer; say no and Datas simply reports that it could
  not.
- **Home Assistant and MQTT are trusted as you set them up.** Datas talks to the address you
  gave. If the broker is on another network, switch on *Encrypted connection (TLS)*.

## From the command line

```
datas-cli things list                 what is plugged in and which connections are set up
datas-cli things around               what announces itself on the network
datas-cli things ffmpeg               fetch FFmpeg now
datas-cli things photo out.jpg        one picture from the camera
datas-cli things screen out.jpg       a picture of the screen
datas-cli things print report.pdf     print a file
datas-cli things serial COM3 --send "LED ON" --baud 9600
datas-cli things check mqtt | home_assistant | modbus --name inverter
datas-cli agent "…" --devices [--control]
```

## How it was tested, and what was not

Tested automatically on Windows, macOS and Linux, on every change: the camera path with
FFmpeg's own test picture in place of a camera; the lists of cameras and printers against
recorded answers of each system; a board on a (pretend) serial port that answers like an
Arduino program; a real MQTT conversation with a small broker written for the tests; Home
Assistant's web interface; a Modbus device that keeps registers and coils; every mouse and
keyboard action against a stand-in; the questions the agent asks; the refusals from a phone.
The weekly test with a real AI also downloads FFmpeg from its fixed address on all three
systems, checks it, and has it read an MP3.

**Not tested with the real thing**, because the test machines have none: a physical camera,
a physical printer, a real Arduino, a real Home Assistant, a real PLC, and the mouse and
keyboard on a real desktop. Each speaks a public, stable protocol and the code follows it,
but the first time you try one, expect that something may need a fix — and please say so
(see [CONTRIBUTING.md](../CONTRIBUTING.md)).

## Open-source parts used

FFmpeg (camera and sound, LGPL/GPL builds as published by their builders),
[Pillow](https://python-pillow.org) (pictures, MIT-CMU), [pySerial](https://github.com/pyserial/pyserial)
(serial ports, BSD), [Eclipse Paho](https://github.com/eclipse-paho/paho.mqtt.python)
(MQTT, EPL-2.0 or BSD-3-Clause), [PyAutoGUI](https://github.com/asweigart/pyautogui) and the
small packages it brings (mouse and keyboard; BSD, MIT, and GPL for MouseInfo, PyMsgBox and
python-xlib), [python-zeroconf](https://github.com/python-zeroconf/python-zeroconf) (network
announcements, LGPL-2.1-or-later), your system's printing service (CUPS on Linux and macOS).
The Modbus part is a few dozen lines of Datas' own, following the public Modbus
specification. Licences are the ones each package states about itself. Full list:
[CREDITS.md](CREDITS.md).
