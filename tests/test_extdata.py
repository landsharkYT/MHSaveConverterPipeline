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


def make_extdata(sd_root, high="00000000", low="00001a6c", good=True):
    leaf = os.path.join(sd_root, "Nintendo 3DS", ID0, ID1, "extdata", high, low)
    size = SIZE_3DS_EXTDATA_ENCRYPTED if good else 1000
    for name in ("00000001", "00000002"):
        make_file(os.path.join(leaf, name), 40960)
    for name in extdata.SIGNATURE_SUBFILES:
        make_file(os.path.join(leaf, name), size)
    return leaf


def test_finds_single_extdata(tmp_path):
    make_extdata(str(tmp_path), low="00001a6c")
    found = extdata.find_mhxx_extdata(str(tmp_path))
    assert len(found) == 1
    assert found[0].low == "00001a6c"
    assert found[0].high == "00000000"
    assert found[0].extdata_id == "0000000000001a6c"


def test_wrong_size_not_matched(tmp_path):
    make_extdata(str(tmp_path), good=False)
    assert extdata.find_mhxx_extdata(str(tmp_path)) == []


def test_missing_sd_root_raises(tmp_path):
    with pytest.raises(extdata.ExtdataError):
        extdata.find_mhxx_extdata(str(tmp_path / "nope"))


def test_multiple_candidates(tmp_path):
    make_extdata(str(tmp_path), low="00001a6c")
    make_extdata(str(tmp_path), low="00002b7d")
    found = extdata.find_mhxx_extdata(str(tmp_path))
    assert len(found) == 2
    assert {f.low for f in found} == {"00001a6c", "00002b7d"}


def test_loose_extdata_layout(tmp_path):
    # sd_root pointed at .../extdata/<high>/<low> directly
    root = str(tmp_path)
    leaf = os.path.join(root, "extdata", "00000000", "00003c8e")
    for name in extdata.SIGNATURE_SUBFILES:
        make_file(os.path.join(leaf, name), SIZE_3DS_EXTDATA_ENCRYPTED)
    found = extdata.find_mhxx_extdata(root)
    assert len(found) == 1
    assert found[0].extdata_id == "0000000000003c8e"
