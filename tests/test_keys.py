import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mhpipeline import keys
from conftest import make_file


def write_set(directory, prefix, boot9_size=keys.BOOT9_SIZE, movable_size=320):
    make_file(os.path.join(directory, prefix + keys.BOOT9_SUFFIX), boot9_size)
    make_file(os.path.join(directory, prefix + keys.MOVABLE_SUFFIX), movable_size)


def test_single_set_resolves(tmp_path):
    write_set(str(tmp_path), "SW13517844")
    ks = keys.resolve_keys(str(tmp_path))
    assert ks.prefix == "SW13517844"
    assert ks.boot9.endswith(keys.BOOT9_SUFFIX)
    assert ks.movable.endswith(keys.MOVABLE_SUFFIX)


def test_missing_dir_raises(tmp_path):
    with pytest.raises(keys.KeyResolutionError):
        keys.resolve_keys(str(tmp_path / "nope"))


def test_no_keys_raises(tmp_path):
    with pytest.raises(keys.KeyResolutionError):
        keys.resolve_keys(str(tmp_path))


def test_boot9_without_movable_is_ignored(tmp_path):
    make_file(os.path.join(str(tmp_path), "SW1" + keys.BOOT9_SUFFIX), keys.BOOT9_SIZE)
    with pytest.raises(keys.KeyResolutionError):
        keys.resolve_keys(str(tmp_path))


def test_multiple_sets_are_ambiguous(tmp_path):
    write_set(str(tmp_path), "SW111")
    write_set(str(tmp_path), "SW222")
    with pytest.raises(keys.AmbiguousKeysError) as ei:
        keys.resolve_keys(str(tmp_path))
    assert len(ei.value.key_sets) == 2


def test_multiple_sets_with_picker(tmp_path):
    write_set(str(tmp_path), "SW111")
    write_set(str(tmp_path), "SW222")
    chosen = keys.resolve_keys(str(tmp_path), picker=lambda s: s[1])
    assert chosen.prefix in ("SW111", "SW222")


def test_wrong_boot9_size_raises(tmp_path):
    write_set(str(tmp_path), "SW1", boot9_size=1234)
    with pytest.raises(keys.KeyResolutionError):
        keys.resolve_keys(str(tmp_path))


def test_movable_288_accepted(tmp_path):
    write_set(str(tmp_path), "SW1", movable_size=288)
    assert keys.resolve_keys(str(tmp_path)).prefix == "SW1"


def test_wrong_movable_size_raises(tmp_path):
    write_set(str(tmp_path), "SW1", movable_size=500)
    with pytest.raises(keys.KeyResolutionError):
        keys.resolve_keys(str(tmp_path))
