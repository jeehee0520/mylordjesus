import pytest

import desktop


def test_selftest_imports_everything_app_uses():
    assert desktop.check_app_imports() > 10


def test_selftest_fails_when_a_module_is_missing(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("from core import storage, not_bundled_module\n", encoding="utf-8")
    monkeypatch.setattr(desktop, "base_dir", lambda: tmp_path)
    with pytest.raises(ModuleNotFoundError):
        desktop.check_app_imports()
