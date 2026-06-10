import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mhpipeline import system_backup as sb


def _with_system_marker(data):
    buf = bytearray(data)
    buf[sb.MARKER_OFFSET:sb.MARKER_END] = sb.SYSTEM_MARKER
    return bytes(buf)


def test_switch_backup_marker_set():
    data = _with_system_marker(b"\x00" * 5000)
    backup = sb.switch_backup_bytes(data)
    assert backup[sb.MARKER_OFFSET:sb.MARKER_END] == sb.BACKUP_MARKER


def test_switch_backup_differs_in_exactly_four_bytes():
    data = _with_system_marker(bytes(range(256)) * 40)
    backup = sb.switch_backup_bytes(data)
    diff = sum(1 for a, b in zip(data, backup) if a != b)
    assert diff == 4
    assert backup[:sb.MARKER_OFFSET] == data[:sb.MARKER_OFFSET]
    assert backup[sb.MARKER_END:] == data[sb.MARKER_END:]


def test_switch_backup_too_small_raises():
    with pytest.raises(ValueError):
        sb.switch_backup_bytes(b"\x00" * 4)  # smaller than 0x18


def test_write_pair_3ds_identical(tmp_path):
    data = b"\x01\x02\x03\x04" * 1000
    sb.write_pair_3ds(str(tmp_path), data)
    assert (tmp_path / "system").read_bytes() == data
    assert (tmp_path / "system_backup").read_bytes() == data


def test_write_pair_switch(tmp_path):
    data = _with_system_marker(b"\x07" * 5000)
    sb.write_pair_switch(str(tmp_path), data)
    assert (tmp_path / "system").read_bytes() == data
    backup = (tmp_path / "system_backup").read_bytes()
    assert backup[sb.MARKER_OFFSET:sb.MARKER_END] == sb.BACKUP_MARKER
    assert backup[:sb.MARKER_OFFSET] == data[:sb.MARKER_OFFSET]
    assert backup[sb.MARKER_END:] == data[sb.MARKER_END:]


def test_write_pair_creates_dir(tmp_path):
    dest = tmp_path / "a" / "b"
    sb.write_pair_3ds(str(dest), b"\x00" * 100)
    assert (dest / "system").exists()


# Strongest check: our rule must reproduce the real system_backup exactly.
_REAL = os.path.join(ROOT, "Example files", "Switch sample files")


@pytest.mark.skipif(
    not os.path.exists(os.path.join(_REAL, "system_backup")),
    reason="Example files/ not present (gitignored)")
def test_reproduces_real_switch_backup():
    with open(os.path.join(_REAL, "system"), "rb") as f:
        system = f.read()
    with open(os.path.join(_REAL, "system_backup"), "rb") as f:
        real_backup = f.read()
    assert sb.switch_backup_bytes(system) == real_backup
