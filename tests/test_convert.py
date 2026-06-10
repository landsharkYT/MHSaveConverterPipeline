import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mhpipeline import convert, converter_bridge, formats, system_backup as sb
from conftest import make_file

API = converter_bridge.load_api()
BLANK_3DS = converter_bridge.blank_3ds_system()
BLANK_MHGU = converter_bridge.blank_switch_system(formats.SWITCH_GAME_MHGU)


def _read(p):
    with open(p, "rb") as f:
        return f.read()


class FakeSave3ds:
    """Models an SD extdata holding a cleartext 'user/system'.

    extract() writes the held state into <dest>/user/system (+ icon, boss/);
    import_() reads <src>/user/system back into the held state. ``corrupt``
    forces import_ to store wrong bytes (to exercise the verify+restore path).
    """

    def __init__(self, initial_system, corrupt=False):
        self.state = initial_system
        self.corrupt = corrupt
        self.imported = 0

    def extract(self, sd_root, extdata_id, key_set, dest_dir):
        user = os.path.join(dest_dir, "user")
        os.makedirs(os.path.join(dest_dir, "boss"), exist_ok=True)
        make_file(os.path.join(dest_dir, "icon"), 14016)
        sb.write_pair_3ds(user, self.state)  # system + system_backup
        return dest_dir

    def import_(self, sd_root, extdata_id, key_set, src_dir):
        data = _read(os.path.join(src_dir, "user", "system"))
        self.state = b"\x00" * len(data) if self.corrupt else data
        self.imported += 1
        return True


def _ctx(tmp_path, switch_dir=None, leaf=None):
    return convert.Context(
        sd_root=str(tmp_path / "sd"),
        extdata_id="0000000000001971",
        extdata_leaf=str(leaf) if leaf else str(tmp_path / "leaf"),
        key_set=object(),
        switch_save_dir=str(switch_dir) if switch_dir else str(tmp_path / "switch"),
        switch_game=formats.SWITCH_GAME_MHGU,
        three_ds_blank=BLANK_3DS,
        switch_blank=BLANK_MHGU,
        sidecar_path=str(tmp_path / "cfg" / "system.mhsidecar"),
        cache_path=str(tmp_path / "cfg" / "cache" / "tails.bin"),
    )


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch, tmp_path):
    # Keep backups / work dirs inside the test's tmp.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def test_to_switch_writes_valid_pair(tmp_path):
    switch_dir = tmp_path / "switch"
    switch_dir.mkdir()
    # Pre-existing switch save (so there is something to back up).
    make_file(str(switch_dir / "system"), formats.SIZE_MHGU, b"\x11")
    make_file(str(switch_dir / "system_backup"), formats.SIZE_MHGU, b"\x11")

    fake = FakeSave3ds(initial_system=_read(BLANK_3DS))  # a valid 3DS cleartext
    ctx = _ctx(tmp_path, switch_dir=switch_dir)
    outcome = convert.to_switch(ctx, s3=fake, api=API, confirm=lambda d: True, log=lambda *_: None)

    system = _read(str(switch_dir / "system"))
    backup = _read(str(switch_dir / "system_backup"))
    assert len(system) == formats.SIZE_MHGU
    assert backup[sb.MARKER_OFFSET:sb.MARKER_END] == sb.BACKUP_MARKER
    assert backup[:sb.MARKER_OFFSET] == system[:sb.MARKER_OFFSET]
    assert os.path.isdir(outcome.backup_dir)
    assert outcome.verified


def test_to_switch_abort_does_not_write(tmp_path):
    switch_dir = tmp_path / "switch"
    switch_dir.mkdir()
    make_file(str(switch_dir / "system"), formats.SIZE_MHGU, b"\x11")
    before = _read(str(switch_dir / "system"))
    fake = FakeSave3ds(initial_system=_read(BLANK_3DS))
    ctx = _ctx(tmp_path, switch_dir=switch_dir)
    with pytest.raises(convert.ConvertError):
        convert.to_switch(ctx, s3=fake, api=API, confirm=lambda d: False, log=lambda *_: None)
    # Original untouched.
    assert _read(str(switch_dir / "system")) == before


def test_to_3ds_success_and_verify(tmp_path):
    switch_dir = tmp_path / "switch"
    switch_dir.mkdir()
    # Real MHGU input.
    with open(BLANK_MHGU, "rb") as f:
        make_file(str(switch_dir / "system"), 0)
        with open(str(switch_dir / "system"), "wb") as g:
            g.write(f.read())

    leaf = tmp_path / "leaf"
    leaf.mkdir()
    for n in ("00000001", "00000002", "00000003", "00000004"):
        make_file(str(leaf / n), 1000, b"\xAB")  # stand-in raw subfiles for backup

    fake = FakeSave3ds(initial_system=_read(BLANK_3DS))
    ctx = _ctx(tmp_path, switch_dir=switch_dir, leaf=leaf)
    outcome = convert.to_3ds(ctx, s3=fake, api=API, confirm=lambda d: True, log=lambda *_: None)

    assert outcome.verified
    assert fake.imported == 1
    # State now holds the converted 3DS cleartext of correct size.
    assert len(fake.state) == formats.SIZE_3DS
    assert os.path.isdir(outcome.backup_dir)


def test_to_3ds_corrupt_import_restores_backup(tmp_path):
    switch_dir = tmp_path / "switch"
    switch_dir.mkdir()
    with open(BLANK_MHGU, "rb") as f:
        with open(str(switch_dir / "system"), "wb") as g:
            g.write(f.read())

    leaf = tmp_path / "leaf"
    leaf.mkdir()
    original_raw = {}
    for n in ("00000001", "00000002", "00000003", "00000004"):
        make_file(str(leaf / n), 1000, b"\xAB")
        original_raw[n] = _read(str(leaf / n))

    fake = FakeSave3ds(initial_system=_read(BLANK_3DS), corrupt=True)
    ctx = _ctx(tmp_path, switch_dir=switch_dir, leaf=leaf)

    with pytest.raises(convert.ConvertError):
        convert.to_3ds(ctx, s3=fake, api=API, confirm=lambda d: True, log=lambda *_: None)

    # Raw leaf restored byte-exact from the backup.
    for n, data in original_raw.items():
        assert _read(str(leaf / n)) == data
