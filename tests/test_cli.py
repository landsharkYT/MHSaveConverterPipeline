import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# cli -> ui -> art/colorama; skip cleanly when those aren't installed.
pytest.importorskip("art")
pytest.importorskip("colorama")

from mhpipeline import cli, formats, profile as profile_mod
from conftest import make_file
from test_extdata import make_extdata
from test_keys import write_set


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


class UIDriver:
    """Feeds scripted answers to ui.prompt / ui.menu / ui.confirm."""

    def __init__(self, monkeypatch, prompts=(), menus=(), confirms=()):
        self.prompts = list(prompts)
        self.menus = list(menus)
        self.confirms = list(confirms)
        monkeypatch.setattr(cli.ui, "prompt", self._prompt)
        monkeypatch.setattr(cli.ui, "menu", self._menu)
        monkeypatch.setattr(cli.ui, "confirm", self._confirm)
        monkeypatch.setattr(cli.ui, "banner", lambda *a, **k: None)
        monkeypatch.setattr(cli.ui, "info", lambda *a, **k: None)
        monkeypatch.setattr(cli.ui, "warn", lambda *a, **k: None)
        monkeypatch.setattr(cli.ui, "error", lambda *a, **k: None)
        monkeypatch.setattr(cli.ui, "overwrite_warning", lambda *a, **k: None)

    def _prompt(self, msg):
        return self.prompts.pop(0)

    def _menu(self, title, options):
        return self.menus.pop(0)

    def _confirm(self, msg, default=False):
        return self.confirms.pop(0) if self.confirms else default


def _valid_env(tmp_path):
    sd = tmp_path / "sd"
    sw = tmp_path / "switch"
    gm9 = tmp_path / "gm9"
    make_extdata(str(sd), low="00001971", nested=True)
    make_file(str(sw / "system"), formats.SIZE_MHGU)
    write_set(str(gm9), "SW13517844")
    return str(sd), str(sw), str(gm9)


def test_setup_profile_writes_valid_profile(monkeypatch, tmp_path):
    sd, sw, gm9 = _valid_env(tmp_path)
    UIDriver(monkeypatch,
             prompts=[sd, sw, gm9],
             menus=[1],          # MHGU
             confirms=[False])   # no custom blanks

    p = cli.setup_profile(profile_mod.Profile())
    assert p.sd_root == sd
    assert p.switch_game == formats.SWITCH_GAME_MHGU
    assert p.mhxx_extdata["extdata_id"] == "0000000000001971"

    # Persisted and reloadable.
    reloaded = profile_mod.Profile.load()
    assert reloaded.gm9_out_dir == gm9


def test_setup_profile_validation_usable_with_pending_touch(monkeypatch, tmp_path):
    sd, sw, gm9 = _valid_env(tmp_path)
    # save3ds not built in the test env -> touch pending, but profile usable.
    monkeypatch.setattr(cli.save3ds, "is_built", lambda override=None: False)
    UIDriver(monkeypatch, prompts=[sd, sw, gm9], menus=[1], confirms=[False])
    p = cli.setup_profile(profile_mod.Profile())
    result = p.validate(deep=True)
    assert result.ok
    assert not result.fully_validated  # touch pending


def test_convert_blocked_when_deps_missing(monkeypatch, tmp_path):
    sd, sw, gm9 = _valid_env(tmp_path)
    p = profile_mod.Profile(sd_root=sd, switch_save_dir=sw, gm9_out_dir=gm9,
                            switch_game=formats.SWITCH_GAME_MHGU)

    class Report:
        ok = False
        missing = []

    monkeypatch.setattr(cli.deps, "check", lambda: Report())
    called = {"convert": False}
    monkeypatch.setattr(cli.convert, "to_switch",
                        lambda *a, **k: called.__setitem__("convert", True))
    UIDriver(monkeypatch)

    cli.convert_to_switch(p)
    assert called["convert"] is False  # gated out before converting


def test_convert_blocked_when_profile_incomplete(monkeypatch, tmp_path):
    class Report:
        ok = True
        missing = []

    monkeypatch.setattr(cli.deps, "check", lambda: Report())
    called = {"convert": False}
    monkeypatch.setattr(cli.convert, "to_3ds",
                        lambda *a, **k: called.__setitem__("convert", True))
    UIDriver(monkeypatch)

    cli.convert_to_3ds(profile_mod.Profile())  # nothing configured
    assert called["convert"] is False
