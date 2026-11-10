"""Saving files: never half-written, and several savers at once do not collide."""


def test_many_savers_at_once_never_trip_over_each_other(tmp_path, monkeypatch):
    """The window asks several things at once when it opens, and more than one of them saves
    the settings. That used to fail now and then ("Internal Server Error" on the first
    screen): both wrote the same temporary file."""
    import threading

    from datas.config import Config, write_text_safely

    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    cfg = Config.load()
    errors = []

    def save_many(n):
        try:
            for i in range(40):
                cfg.context = 2048 + n * 100 + i
                cfg.save()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=save_many, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert Config.load().context >= 2048  # the file on disk is whole
    assert not list(tmp_path.glob("*.tmp"))  # nothing left behind
    assert (tmp_path / "config.json.bak").exists()
    # the same helper for any file: private ones are readable by this user only
    p = write_text_safely(tmp_path / "secret.json", "{}", private=True)
    import sys

    if sys.platform != "win32":
        assert p.stat().st_mode & 0o077 == 0
    assert write_text_safely(p, '{"a": 1}').read_text(encoding="utf-8") == '{"a": 1}'
