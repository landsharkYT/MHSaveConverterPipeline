import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mhpipeline import paths


def test_config_dir_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert paths.config_dir() == str(tmp_path / "mhsaveconverter")


def test_config_dir_default(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    expected = os.path.join(os.path.expanduser("~"), ".config", "mhsaveconverter")
    assert paths.config_dir() == expected


def test_derived_paths_under_config(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = paths.config_dir()
    assert paths.profile_path() == os.path.join(cfg, "profile.json")
    assert paths.cache_path().startswith(cfg)
    assert paths.sidecar_path().startswith(cfg)
    assert paths.backups_dir().startswith(cfg)
    assert paths.work_dir().startswith(cfg)


def test_new_backup_dir_created_and_labelled(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    d = paths.new_backup_dir("3ds")
    assert os.path.isdir(d)
    assert os.path.basename(d).startswith("3ds-")


def test_ensure_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    paths.ensure_config_dir()
    assert os.path.isdir(paths.config_dir())
