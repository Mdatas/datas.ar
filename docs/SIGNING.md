# Signatures: what is signed today, and what needs the owner

"Signed" means three different things. This page says which ones Datas has, which ones are
wired and waiting for a certificate, and exactly what the owner of the project has to obtain —
because certificates are issued to a person or a company after an identity check, nobody else
can get them for you.

## 1. Proof of where a file was built — in place

Every installer attached to a release comes with:

- a **checksum file** (`<file>.sha256`), to check that a download is complete and unchanged;
- a **signed provenance statement**: a public record, signed through
  [Sigstore](https://www.sigstore.dev) with GitHub's identity for this repository, saying
  "this exact file was produced by the workflow in `Mdatas/datas.ar` from commit X". Nobody
  can produce that statement for a file built elsewhere.

Check a download (needs the [GitHub command line](https://cli.github.com)):

```bash
gh attestation verify Datas-Setup-0.3.0.exe -R Mdatas/datas.ar
sha256sum -c Datas-Setup-0.3.0.exe.sha256        # macOS: shasum -a 256 -c …
```

The app does its own check when it updates itself: it compares the installer with the
SHA-256 that GitHub publishes for the release file (see [UPDATES.md](UPDATES.md)).

This proves the file is the project's. It does **not** remove the warning Windows and macOS
show for programs without a paid certificate — that is the next two sections.

## 2. Windows: the "unknown publisher" warning

Needs a code-signing certificate. Options, cheapest first (checked in November 2026):

| Option | Cost | What it takes |
|---|---|---|
| **SignPath Foundation** (signpath.org) | free for open-source projects | Apply with the repository. The certificate belongs to SignPath Foundation, so Windows shows "SignPath Foundation" as the publisher. Conditions: an open-source licence, a public "code signing policy" page naming who may approve a release, and signing only this project's own programs. A draft of that page is in [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md). |
| **Azure Artifact Signing** (Microsoft; called Trusted Signing until 2026) | US$9.99 a month | An Azure account and an identity check. Offered to people and companies in the USA, Canada and Europe — check whether your country is covered before counting on it. |
| A certificate from a certificate authority | roughly US$200–600 a year | Since June 2023 the key must live on a hardware token or a cloud signing service, which makes signing from an automatic build harder. |

What is wired: if the repository has the secrets `WINDOWS_CERT_PFX_BASE64` and
`WINDOWS_CERT_PASSWORD` (a certificate exported as a `.pfx` file), the `windows-installer`
workflow signs `Datas.exe`, `datas-cli.exe` and the installer with it and timestamps them.
**Written, not yet run** — there is no certificate to run it with. SignPath and Azure Artifact
Signing use their own workflow steps instead of a `.pfx`; once you are accepted by one of
them, the workflow gets that step.

Even with a certificate, Windows SmartScreen keeps warning for a while on a new publisher
(reputation builds with downloads), except with EV certificates.

## 3. macOS: "cannot be opened because the developer cannot be verified"

Needs an **Apple Developer account** (US$99 a year, in your name or your company's), then a
"Developer ID Application" certificate and Apple's check of each build (notarization).

What is wired: add these secrets and the `desktop-installers` workflow signs every program
inside `Datas.app` (hardened runtime, `installer/macos/entitlements.plist`), signs the disk
image, sends it to Apple and attaches Apple's ticket:

| Secret | What it is |
|---|---|
| `APPLE_CERT_P12_BASE64` | the Developer ID Application certificate with its key, exported from Keychain as `.p12`, then `base64` |
| `APPLE_CERT_PASSWORD` | the password chosen when exporting |
| `APPLE_SIGN_IDENTITY` | its name, e.g. `Developer ID Application: Your Name (TEAMID)` |
| `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD` | your Apple ID, team id, and an app-specific password made at appleid.apple.com |

**Written, not yet run**, for the same reason.

## 4. Android

An Android app must always be signed, and every update must be signed with the **same key**,
so the key has to be yours and kept safe. Until you add one, the build signs the APK with a
throw-away "debug" key: it installs, but a later build signed with your real key will not
install over it (uninstall first).

Make your key once, on your own computer (needs Java):

```bash
keytool -genkeypair -v -keystore datas-release.keystore -alias datas \
        -keyalg RSA -keysize 4096 -validity 10000
base64 -w0 datas-release.keystore        # macOS: base64 -i datas-release.keystore
```

Add four repository secrets (*Settings → Secrets and variables → Actions*):
`KEYSTORE_BASE64` (the long line printed above), `KEYSTORE_PASSWORD`, `KEY_ALIAS` (`datas`),
`KEY_PASSWORD`. From then on `Datas-release.apk` is signed with your key. **Keep a copy of
the keystore file and its passwords somewhere safe; if they are lost, existing installs can
never be updated.** This path is already used by the workflow; it only needs the secrets.

Publishing on Google Play additionally needs a Play Console account (US$25 once).

## 5. iPhone

Any app on a real iPhone must be signed with an Apple Developer account (the same one as in
section 3) and distributed through TestFlight or the App Store. See [MOBILE.md](MOBILE.md).

## 6. The catalog and the AI files

- AI files are checked against the SHA-256 that Hugging Face publishes for each file.
- The AI engine (llama.cpp) is a tested version, checked against the SHA-256 GitHub publishes.
- Signing the catalog itself (so a community catalog can be trusted) is on the roadmap.
