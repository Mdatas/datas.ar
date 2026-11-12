# Updates, and going back

Datas is made of pieces that change at different speeds. Each one updates on its own, and
each one can go back to the version before if something breaks.

## Up to date by itself

**Settings → Updates → Keep Datas up to date by itself** is on unless you switch it off. While
Datas runs it asks the project's Releases page at most every 12 hours (the first look waits a
minute and a half after Datas starts):

- **Datas.** A newer installer is downloaded into `<data>/updates/` and checked against the
  SHA-256 GitHub publishes for it; a release without a published checksum is never installed
  unattended. On **Windows** it installs, without questions, when you close Datas — or at once
  with **Install now** in the notice (Datas closes, updates and opens again). On macOS and Linux
  the notice offers to open the disk image or package, because installing there needs you.
- **List of AIs.** Refreshed the same way as the button below; going back is one click.
- **AI engine.** *Not* changed by itself: llama.cpp publishes new builds several times a day.
  The newest is offered below, with a way back.

With the switch off nothing is asked unless you press **Check for updates**.

| Piece | Update | Go back | What is kept |
|---|---|---|---|
| **Datas** (the app) | By itself (above), or: downloads the installer of the new version from the project's Releases page, checks its size and SHA-256, and opens it. | *Go back* lists earlier versions and installs the one you pick the same way. | AIs, chats, notes, settings. A copy of the settings is saved once per version in `backups/`. |
| **AI engine** (llama.cpp) | The new build is downloaded **beside** the current one (`llamacpp/<version>/`), tested, and only then used. If the test or the next start of your AI fails, Datas returns to the previous build by itself and says so. | *Go back to <version>* switches to the build that was in use before. *Delete old copies* frees the space. | Every AI you installed. |
| **Picture engine** (stable-diffusion.cpp) | Same idea: versions live side by side in `sdcpp/<version>/`. | *Go back to <version>*. | Picture models. |
| **List of AIs** (the catalog) | Downloads the newest list from the repository into `catalog.update.json` after checking it is well-formed and not older. | *Go back to the built-in list* deletes that file; the list shipped with the app is used again. | Installed AIs are not touched. |
| **AIs themselves** | Not updated in place. A newer AI is a new entry in the list; get it from *Add an AI* and remove the old one when you are happy. | Keep both until you decide. | — |
| **Bigger creative tools** | Each is pinned to a version Datas tested; *Open* installs that version in its own folder. | Remove and install again. | Their own downloads, until you remove the tool. |

*What changed before* (under the list) keeps the last changes with their dates.

## Installing over an earlier copy

The installer looks for an earlier copy first, removes the program files cleanly, and leaves
the data folder alone. On the first start afterwards Datas tells you what it found and kept
("Datas was updated from 0.3.0 to 0.4.0. Your AIs, chats and settings were kept."). A damaged
settings file is set aside (`config.json.damaged`) and replaced by the backup or by defaults,
so a bad file can never stop the app from opening.

## Tested versions

Datas ships knowing one engine build it was tested with (`KNOWN_GOOD_TAG` in
[`datas/runtime/llamacpp.py`](../datas/runtime/llamacpp.py) and
[`datas/engines/images.py`](../datas/engines/images.py)). A fresh install uses that build.
Newer builds are offered, never forced.

## For maintainers: publishing a version

1. Set the version in `pyproject.toml` and `datas/__init__.py`.
2. GitHub → **Actions → release → Run workflow**, give the version (for example `0.4.0`).
   The workflow creates the tag and the release, then starts the Windows, macOS/Linux and
   Android installer builds, which attach their files to that release.
3. *Check for updates* in an installed copy will then offer the new version: it reads the
   release list, picks the file for the user's system by name, and verifies the SHA-256
   GitHub publishes for it.

Every installer build runs `datas-cli selftest` on the finished app and stops if a part is
missing or broken, so a damaged build cannot be attached to a release.

The release workflow was written and reviewed but has not run yet; watch the first run.

Code: [`datas/updates.py`](../datas/updates.py). Tests: `tests/test_updates.py` (a real engine
switch, a missing build, a broken build that triggers the automatic return).
