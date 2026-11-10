"""FFmpeg fetched once and checked: the right file is unpacked, a wrong one is refused."""

from __future__ import annotations

import hashlib
import io
import os
import threading
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from datas import programs


@pytest.fixture
def shelf(tmp_path):
    """A folder served over HTTP on this computer; returns (folder, address)."""
    folder = tmp_path / "served"
    folder.mkdir()

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a):  # noqa: ANN002
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(folder)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield folder, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def build(key: str, extra: dict[str, bytes] | None = None) -> bytes:
    exe = ".exe" if programs.SYSTEM == "Windows" else ""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{key}/ffmpeg{exe}", b"#!/bin/sh\necho ffmpeg\n")
        z.writestr(f"{key}/ffprobe{exe}", b"#!/bin/sh\necho ffprobe\n")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


def test_the_pinned_builds_cover_every_desktop_and_are_fully_described():
    assert programs.ffmpeg_key("Windows", "AMD64") == "win32"
    assert programs.ffmpeg_key("Darwin", "arm64") == "darwin_arm64"
    assert programs.ffmpeg_key("Darwin", "x86_64") == "darwin"
    assert programs.ffmpeg_key("Linux", "x86_64") == "linux"
    assert programs.ffmpeg_key("Linux", "aarch64") == "linux_arm64"
    assert programs.ffmpeg_key("Windows", "ARM64") is None  # no build: the person is told
    assert programs.ffmpeg_key("FreeBSD", "amd64") is None
    for key, (size, sha) in programs.FFMPEG_BUILDS.items():
        assert size > 10_000_000 and len(sha) == 64 and int(sha, 16), key
    assert len(programs.FFMPEG_COMMIT) == 40  # one exact commit, never "main"
    dl = programs.ffmpeg_download()
    if dl:  # this computer has a build
        assert dl["url"].startswith(programs.FFMPEG_REPO + "/raw/" + programs.FFMPEG_COMMIT + "/")
        assert dl["url"].endswith(f"/{dl['key']}.zip")


def test_a_checked_copy_is_unpacked_and_found_again(tmp_path, monkeypatch, shelf):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "home"))
    key = programs.ffmpeg_key()
    if not key:
        pytest.skip("no FFmpeg build for this kind of computer")
    folder, base = shelf
    # the archive also tries to write outside its folder: that entry must be ignored
    data = build(key, {"../../evil.txt": b"x", f"{key}/readme.txt": b"y", "/abs/ffmpeg.sh": b"z"})
    (folder / "f.zip").write_bytes(data)
    monkeypatch.setitem(programs.FFMPEG_BUILDS, key, (len(data), hashlib.sha256(data).hexdigest()))
    assert programs.ffmpeg_fetched() is None
    seen = []
    exe = programs.fetch_ffmpeg(
        lambda done, total: seen.append((done, total)), source=base + "/f.zip"
    )
    target = programs.ffmpeg_dir() / key
    assert exe == programs.ffmpeg_fetched() and os.path.dirname(exe) == str(target)
    assert sorted(p.name for p in target.iterdir()) == sorted(
        ["checked", os.path.basename(exe), os.path.basename(exe).replace("ffmpeg", "ffprobe")]
    )
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path / "home" / "evil.txt").exists()
    assert not list(programs.ffmpeg_dir().glob("*.zip"))  # the archive is not kept
    assert seen and seen[-1][0] == len(data)
    if programs.SYSTEM != "Windows":
        assert os.access(exe, os.X_OK)
    # a second call does not download again (the address now points nowhere)
    assert programs.fetch_ffmpeg(source=base + "/gone.zip") == exe
    # and the list of programs shows it when the system has none of its own
    monkeypatch.setattr(programs, "_find", lambda names, paths: None)
    assert programs.find("ffmpeg") == exe and programs.ffmpeg() == exe


def test_a_file_that_is_not_the_expected_one_is_refused(tmp_path, monkeypatch, shelf):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "home"))
    key = programs.ffmpeg_key()
    if not key:
        pytest.skip("no FFmpeg build for this kind of computer")
    folder, base = shelf
    good = build(key)
    (folder / "f.zip").write_bytes(build(key, {f"{key}/extra": b"tampered"}))
    monkeypatch.setitem(programs.FFMPEG_BUILDS, key, (len(good), hashlib.sha256(good).hexdigest()))
    with pytest.raises(RuntimeError) as e:
        programs.fetch_ffmpeg(source=base + "/f.zip")
    assert "not the one Datas expects" in str(e.value)
    assert programs.ffmpeg_fetched() is None and not (programs.ffmpeg_dir() / key).exists()
    assert not list(programs.ffmpeg_dir().glob("*"))  # nothing left behind
    # no connection: a sentence, not a crash
    with pytest.raises(RuntimeError) as e:
        programs.fetch_ffmpeg(source="http://127.0.0.1:9/none.zip")
    assert "could not be downloaded" in str(e.value)
    # with fetch=True the caller just gets "none" and can say so
    monkeypatch.setattr(programs, "_find", lambda names, paths: None)
    monkeypatch.setattr(
        programs, "fetch_ffmpeg", lambda progress=None: (_ for _ in ()).throw(RuntimeError("x"))
    )
    assert programs.ffmpeg(fetch=True) is None
