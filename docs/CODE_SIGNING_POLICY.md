# Code signing policy

**Status: no certificate yet.** This page is prepared for an application to the
[SignPath Foundation](https://signpath.org) programme for open-source projects, which asks
each project to publish who may sign what. Until the project is accepted, Windows files are
not signed with a certificate; every release file does carry a checksum and a signed record
of where it was built (see [SIGNING.md](SIGNING.md)).

## What would be signed

Only programs built from this repository by its own GitHub Actions workflows, for a release:
`Datas.exe`, `datas-cli.exe` and the installer `Datas-Setup-<version>.exe`. Programs made by
others that the installer contains or downloads later (the llama.cpp engine, AI files) are
not signed by this project.

## Who

| Role | Who |
|---|---|
| Committers and reviewers | people with write access to [Mdatas/datas.ar](https://github.com/Mdatas/datas.ar) |
| Approvers (each signed release needs one) | the repository owner, [@Mdatas](https://github.com/Mdatas) |

## Privacy

Datas does not collect or send any information about its users or their devices. What it
connects to, and when, is listed in [PRIVACY.md](PRIVACY.md).
