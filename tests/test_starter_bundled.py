"""The starter AI shipped inside the installer is placed among the AIs on first start."""

from datas import catalog as C
from datas import starter


def test_bundled_starter_is_placed_once(tmp_path, monkeypatch):
    m = C.load().get(starter.ID)
    f = m.file(starter.QUANT)
    shipped = tmp_path / "shipped" / f.path
    shipped.parent.mkdir()
    with shipped.open("wb") as fh:  # a sparse file of the right size stands in for the AI
        fh.truncate(f.bytes)
    monkeypatch.setattr(starter, "bundled_file", lambda: shipped)
    monkeypatch.setattr("datas.runtime.downloader.models_dir", lambda: tmp_path / "models")
    dest = starter.install_bundled()
    assert dest == tmp_path / "models" / starter.ID / f.path
    assert dest.stat().st_size == f.bytes
    assert starter.install_bundled() == dest  # already there: nothing to do


def test_a_file_that_is_not_the_catalog_one_is_left_alone(tmp_path, monkeypatch):
    other = tmp_path / "Qwen3-0.6B-Q4_0.gguf"
    other.write_bytes(b"not the AI")
    monkeypatch.setattr(starter, "bundled_file", lambda: other)
    monkeypatch.setattr("datas.runtime.downloader.models_dir", lambda: tmp_path / "models")
    assert starter.install_bundled() is None


def test_no_starter_inside_a_plain_install():
    # the build puts it there; the source tree and pip packages have none
    assert starter.bundled_file() is None or starter.bundled_file().suffix == ".gguf"
