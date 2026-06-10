import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mhpipeline import formats, keys
from mhpipeline.profile import Profile
from conftest import make_file
from test_extdata import make_extdata
from test_keys import write_set


def test_save_load_roundtrip(tmp_path):
    p = Profile(sd_root="/sd", switch_save_dir="/sw", gm9_out_dir="/gm9",
                switch_game=formats.SWITCH_GAME_MHGU,
                mhxx_extdata={"extdata_id": "abc", "path": "/x"})
    path = tmp_path / "profile.json"
    p.save(str(path))
    loaded = Profile.load(str(path))
    assert loaded == p


def test_load_missing_returns_empty(tmp_path):
    p = Profile.load(str(tmp_path / "nope.json"))
    assert p == Profile()
    assert not p.has_required()


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text('{"sd_root": "/sd", "bogus": 1}')
    p = Profile.load(str(path))
    assert p.sd_root == "/sd"


def test_validate_missing_fields_shallow():
    r = Profile().validate(deep=False)
    assert not r.ok
    assert any(c.name == "required fields" and not c.ok for c in r.checks)


def _valid_setup(tmp_path, switch_game=formats.SWITCH_GAME_MHGU):
    """Build a fully valid on-disk environment and return a Profile for it."""
    sd_root = tmp_path / "sd"
    sw_dir = tmp_path / "switch"
    gm9 = tmp_path / "gm9"

    make_extdata(str(sd_root), low="00001a6c")
    make_file(str(sw_dir / "system"), formats.switch_system_size(switch_game))
    write_set(str(gm9), "SW13517844")

    return Profile(sd_root=str(sd_root), switch_save_dir=str(sw_dir),
                   gm9_out_dir=str(gm9), switch_game=switch_game)


def test_deep_validate_ok_with_touch_pending(tmp_path):
    p = _valid_setup(tmp_path)
    r = p.validate(deep=True)  # no save3ds probe injected
    assert r.ok                       # usable
    assert not r.fully_validated      # touch still pending
    assert any(c.name == "save3ds key test" and c.pending for c in r.checks)
    assert r.hard_failures == []


def test_deep_validate_fully_validated_with_passing_touch(tmp_path):
    p = _valid_setup(tmp_path)
    seen = {}

    def touch(sd_root, extdata_id, key_set):
        seen["sd_root"] = sd_root
        seen["extdata_id"] = extdata_id
        seen["prefix"] = key_set.prefix
        return True

    r = p.validate(deep=True, save3ds_touch=touch)
    assert r.fully_validated
    assert seen["extdata_id"] == "0000000000001a6c"
    assert seen["prefix"] == "SW13517844"


def test_deep_validate_failing_touch_is_hard_failure(tmp_path):
    p = _valid_setup(tmp_path)
    r = p.validate(deep=True, save3ds_touch=lambda *a: False)
    assert not r.ok
    assert any(c.name == "save3ds key test" and not c.ok for c in r.checks)


def test_deep_validate_bad_switch_size(tmp_path):
    p = _valid_setup(tmp_path)
    # Truncate the switch system to the wrong size.
    make_file(os.path.join(p.switch_save_dir, "system"), 100)
    r = p.validate(deep=True)
    assert any(c.name == "switch system size" and not c.ok for c in r.checks)
    assert not r.ok


def test_deep_validate_no_keys(tmp_path):
    p = _valid_setup(tmp_path)
    for f in os.listdir(p.gm9_out_dir):
        os.remove(os.path.join(p.gm9_out_dir, f))
    r = p.validate(deep=True)
    assert any(c.name == "keys resolve" and not c.ok for c in r.checks)


def test_deep_validate_blank_override_size(tmp_path):
    p = _valid_setup(tmp_path)
    bad_blank = tmp_path / "blank3ds"
    make_file(str(bad_blank), 123)
    p.blank_3ds_system = str(bad_blank)
    r = p.validate(deep=True)
    assert any(c.name == "blank_3ds_system" and not c.ok for c in r.checks)
