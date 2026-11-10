# Datas.ar for macOS

Download **`Datas-<version>.dmg`** from the [Releases](https://github.com/Mdatas/datas.ar/releases) page
(until a release exists: the `desktop-installers` GitHub Action builds it on every push).

1. Open the `.dmg` and drag **Datas** onto **Applications**.
2. First launch: **right-click Datas → Open → Open**. macOS shows an "unidentified developer" warning because
   the app is not signed with an Apple Developer certificate yet; right-click → Open is the once-only way
   around it. (If macOS says the app "is damaged", run `xattr -dr com.apple.quarantine /Applications/Datas.app`
   in Terminal once — same cause.)
3. Datas opens its own window. Apple Silicon Macs run the AI on the GPU through Metal automatically.

Upgrade: drag the new version over the old one. Your data is separate and kept.

Uninstall: drag Datas from Applications to the Trash. Your data stays in
`~/Library/Application Support/Datas` (AI models, chats, notes, engine, settings, logs); delete that folder,
or use *Settings → Forget everything* in the app, to remove it.

Command line: `/Applications/Datas.app/Contents/MacOS/datas-cli` (`scan`, `doctor`, `recommend`).

## Build it yourself

```
pip install ".[voice]" pyinstaller
installer/macos/make-icns.sh
pyinstaller --noconfirm installer/datas.spec
installer/macos/build-dmg.sh 0.4.0
```
