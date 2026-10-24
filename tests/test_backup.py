from datetime import datetime

from freeagent.backup import make_backup, restore_latest


def _homes(tmp_path):
    hh, oh = tmp_path / "hermes", tmp_path / "omh"
    (oh / "routing").mkdir(parents=True)
    hh.mkdir()
    (hh / "config.yaml").write_bytes(b"model:\r\n  default: a\r\n")
    (hh / ".env").write_text("K=1\n")
    (oh / "routing" / "model-chains.json").write_text('{"a": 1}')
    return hh, oh


def test_backup_then_restore_roundtrip(tmp_path):
    hh, oh = _homes(tmp_path)
    make_backup(hh, oh, datetime(2026, 1, 2, 3, 4, 5))
    (hh / "config.yaml").write_text("broken")
    (oh / "routing" / "model-chains.json").write_text("{}")
    assert restore_latest(hh, oh) is not None
    assert (hh / "config.yaml").read_bytes() == b"model:\r\n  default: a\r\n"
    assert (oh / "routing" / "model-chains.json").read_text() == '{"a": 1}'


def test_restore_without_backup_returns_none(tmp_path):
    hh, oh = _homes(tmp_path)
    assert restore_latest(hh, oh) is None


def test_backup_skips_missing_files(tmp_path):
    hh, oh = _homes(tmp_path)
    path = make_backup(hh, oh, datetime(2026, 1, 2, 3, 4, 5))
    assert (path / "config.yaml").exists() and not (path / "auth.json").exists()


def test_latest_is_newest_timestamp(tmp_path):
    hh, oh = _homes(tmp_path)
    make_backup(hh, oh, datetime(2026, 1, 2, 3, 4, 5))
    (hh / "config.yaml").write_text("second")
    make_backup(hh, oh, datetime(2026, 1, 3, 0, 0, 0))
    (hh / "config.yaml").write_text("third")
    restore_latest(hh, oh)
    assert (hh / "config.yaml").read_text() == "second"
