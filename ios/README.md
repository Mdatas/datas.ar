# Datas for iPhone and iPad

A small app that links the phone to **your own computers** and shows their Datas: the same
window, the computer's AIs, chats, helpers, documents and Learn. The computer does the
thinking; the phone is the door. It runs no AI on the phone itself.

It is the iPhone counterpart of *My computers* in the Android app.

## What it does

1. On the computer: *Datas → Devices → Show a code*.
2. On the phone: **Link a computer**. Computers with Datas on the same Wi-Fi are listed; tap
   yours, or type the address the computer shows, and type the code.
3. Tap the computer. Its Datas opens.

Swipe a computer to the left to forget it on the phone. To turn the phone away for good —
for example if it is lost — press *Unlink* next to it on the computer's Devices screen.

What a linked phone may and may not do on the computer is decided by the computer:
[docs/DEVICES.md](../docs/DEVICES.md#phones-and-tablets).

## How it is protected

- The link is TLS 1.3. The first time, phone and computer prove to each other that both know
  the one-time code — the code itself never travels — and the phone remembers the computer's
  certificate. Afterwards **only that certificate** is accepted.
- The phone's secret for each computer is kept in the phone's own safe (the Keychain), for
  this device only: it is not copied to iCloud or to another phone.
- The web view keeps nothing on the phone (no cookies, no cache on disk).
- The app talks to nothing except the computers you linked. No account, no server in the
  middle, no statistics.

## Putting it on your iPhone

Apple does not let an app be installed from a file. There are three ways, all of which need
**your own Apple account** — the project cannot do this for you:

| Way | What you need | How long it lasts |
|---|---|---|
| From Xcode, with a free Apple ID | a Mac with Xcode, a cable | 7 days, then run it again from Xcode |
| From Xcode, with the Apple Developer Program (US$99 a year) | the same | a year |
| TestFlight or the App Store | the Developer Program, and Apple's review | until you remove it |

With a Mac:

```
brew install xcodegen                 # makes the Xcode project from its recipe (project.yml)
cd ios/App && xcodegen generate
open Datas.xcodeproj
```

In Xcode: choose the target **Datas → Signing & Capabilities**, pick your team (your Apple
ID), plug in the iPhone, choose it at the top, and press **Run**. The first time, the phone
asks you to trust yourself as a developer (*Settings → General → VPN & Device Management*),
and the app asks to use the local network — it needs that to reach your computer.

## What is in here

```
DatasLink/                 the link itself, without a screen (a Swift package)
  Sources/DatasLink/         LinkClient (pairing, pinned TLS), Door (the phone's local door),
                             Crypto, Computer, DoorCheck
  Sources/datas-link/        a tiny command line around it, for the tests
  Tests/DatasLinkTests/      known answers from the computer's code; a walk against a real Datas
App/
  project.yml                the recipe for the Xcode project (XcodeGen)
  Datas/                     the app: the list of computers, linking, the web view
```

Everything uses Apple's own libraries (Network, CryptoKit, CommonCrypto, WebKit, SwiftUI).
The same link is written in Python (`tests/phone.py`, the reference) and in Java (the Android
app); the computer's side is `datas/link/__init__.py`.

## How it is tested, and what is not

On every change (`.github/workflows/ios.yml`, on a Mac):

- the arithmetic of pairing gives the same answers as the computer's code;
- the library links to a **real Datas** started for the test: wrong code refused, pairing,
  the computer's window through the door, the things a phone is refused, a made-up secret
  and a different certificate turned away;
- the app is built for iPhone;
- the same walk runs **inside the iPhone simulator**, where the app's own kind of web view
  loads the computer's Datas through the door and the page draws its menu.

The unit tests of the whole project also run the link through its command line on macOS,
with the very same test the Android code goes through.

**Not tested:** a physical iPhone or iPad. The simulator shares the Mac's network, so the
phone's own "allow local network" question and real Wi-Fi are not exercised. Nobody at the
project has run this app on a phone yet — tell us what happens on yours.

## Not there yet

- An AI running on the iPhone itself (see [docs/MOBILE.md](../docs/MOBILE.md)).
- Voice from the phone, and saving an answer's file to the phone: files stay on the computer.
- Reaching the computer from outside your home needs a private network between your devices
  (WireGuard, Tailscale).
