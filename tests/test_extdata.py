import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mhpipeline import extdata
from mhpipeline.formats import SIZE_3DS_EXTDATA_ENCRYPTED
from conftest import make_file

ID0 = "0123456789abcdef0123456789abcdef"
ID1 = "fedcba9876543210fedcba9876543210"


def make_extdata(sd_root, high="00000000", low="00001971", good=True, nested=True,
                 variant=("00000003", "00000004")):
    """Build a realistic SD extdata tree.

    Real SD nests the numbered subfiles under a device dir
    (extdata/<high>/<low>/00000000/...); ``nested=False`` puts them directly in
    <low> for the flatter variant some dumps use.
    """
    base = os.path.join(sd_root, "Nintendo 3DS", ID0, ID1, "extdata", high, low)
    leaf = os.path.join(base, "00000000") if nested else base
    size = SIZE_3DS_EXTDATA_ENCRYPTED if good else 1000
    for name in ("00000001", "00000002"):
        make_file(os.path.join(leaf, name), 40960)
    for name in variant:
        make_file(os.path.join(leaf, name), size)
    return leaf


def test_finds_nested_real_layout(tmp_path):
    make_extdata(str(tmp_path), low="00001971", nested=True)
    found = extdata.find_mhxx_extdata(str(tmp_path))
    assert len(found) == 1
    assert found[0].high == "00000000"
    assert found[0].low == "00001971"
    assert found[0].extdata_id == "0000000000001971"


def test_finds_flat_layout(tmp_path):
    make_extdata(str(tmp_path), low="00001a6c", nested=False)
    found = extdata.find_mhxx_extdata(str(tmp_path))
    assert len(found) == 1
    assert found[0].extdata_id == "0000000000001a6c"


def test_finds_alternate_real_layout(tmp_path):
    make_extdata(str(tmp_path), low="00001971", nested=True,
                 variant=("00000002", "00000003"))
    found = extdata.find_mhxx_extdata(str(tmp_path))
    assert len(found) == 1
    assert found[0].extdata_id == "0000000000001971"


def test_finds_non_adjacent_payloads(tmp_path):
    # Real SD seen with the two payloads at 00000002 + 00000004 (not adjacent).
    make_extdata(str(tmp_path), low="00001971", nested=True,
                 variant=("00000002", "00000004"))
    found = extdata.find_mhxx_extdata(str(tmp_path))
    assert len(found) == 1
    assert found[0].extdata_id == "0000000000001971"


def test_wrong_size_not_matched(tmp_path):
    make_extdata(str(tmp_path), good=False)
    assert extdata.find_mhxx_extdata(str(tmp_path)) == []


def test_missing_sd_root_raises(tmp_path):
    with pytest.raises(extdata.ExtdataError):
        extdata.find_mhxx_extdata(str(tmp_path / "nope"))


def test_multiple_candidates(tmp_path):
    make_extdata(str(tmp_path), low="00001971", nested=True)
    make_extdata(str(tmp_path), low="00002b7d", nested=True)
    found = extdata.find_mhxx_extdata(str(tmp_path))
    assert {f.low for f in found} == {"00001971", "00002b7d"}


def test_sd_root_pointed_at_extdata_parent(tmp_path):
    # User points at a dir that directly contains "extdata/..."
    inner = str(tmp_path / "inner")
    leaf = os.path.join(inner, "extdata", "00000000", "00003c8e", "00000000")
    for name in ("00000003", "00000004"):
        make_file(os.path.join(leaf, name), SIZE_3DS_EXTDATA_ENCRYPTED)
    found = extdata.find_mhxx_extdata(inner)
    assert len(found) == 1
    assert found[0].extdata_id == "0000000000003c8e"
