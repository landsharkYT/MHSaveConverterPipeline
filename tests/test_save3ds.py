import os
import stat
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mhpipeline import save3ds

# The fake binary below is a POSIX shell script; the argv-assembly tests that
# execute it are skipped on Windows (the wrapper logic itself is identical).
posix_only = pytest.mark.skipif(os.name == "nt",
                                reason="fake binary is a /bin/sh script")


class FakeKeys:
    boot9 = "/keys/boot9.bin"
    movable = "/keys/movable.sed"


def make_fake_binary(path, exit_code=0, argdump=None):
    """A fake save3ds_fuse that records its argv and exits with ``exit_code``."""
    script = "#!/bin/sh\n"
    if argdump:
        # Write each argument on its own line to a known file.
        script += 'printf "%s\\n" "$@" > "{}"\n'.format(argdump)
    script += "exit {}\n".format(exit_code)
    with open(path, "w") as f:
        f.write(script)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def read_args(argdump):
    with open(argdump) as f:
        return [line.rstrip("\n") for line in f if line.strip() != ""]


def test_not_built_raises(tmp_path):
    missing = str(tmp_path / "nope")
    with pytest.raises(save3ds.Save3dsNotBuilt):
        save3ds.touch("/sd", "id", FakeKeys(), binary=missing)


@posix_only
def test_touch_argv(tmp_path):
    bin_path = str(tmp_path / "save3ds_fuse")
    dump = str(tmp_path / "args.txt")
    make_fake_binary(bin_path, 0, dump)
    assert save3ds.touch("/sd/root", "0000000000001a6c", FakeKeys(), binary=bin_path)
    args = read_args(dump)
    assert args == [
        "--sdext", "0000000000001a6c", "--touch",
        "--sd", "/sd/root", "--boot9", "/keys/boot9.bin",
        "--movable", "/keys/movable.sed",
    ]


@posix_only
def test_extract_argv_and_creates_dest(tmp_path):
    bin_path = str(tmp_path / "save3ds_fuse")
    dump = str(tmp_path / "args.txt")
    make_fake_binary(bin_path, 0, dump)
    dest = str(tmp_path / "out" / "extract")
    save3ds.extract("/sd", "ID", FakeKeys(), dest, binary=bin_path)
    assert os.path.isdir(dest)
    args = read_args(dump)
    assert args[:4] == ["--sdext", "ID", dest, "--extract"]
    assert "--sd" in args and "--boot9" in args and "--movable" in args


@posix_only
def test_import_argv(tmp_path):
    bin_path = str(tmp_path / "save3ds_fuse")
    dump = str(tmp_path / "args.txt")
    make_fake_binary(bin_path, 0, dump)
    src = str(tmp_path / "src")
    os.makedirs(src)
    save3ds.import_("/sd", "ID", FakeKeys(), src, binary=bin_path)
    args = read_args(dump)
    assert args[:4] == ["--sdext", "ID", src, "--import"]


@posix_only
def test_nonzero_exit_raises(tmp_path):
    bin_path = str(tmp_path / "save3ds_fuse")
    make_fake_binary(bin_path, exit_code=2)
    with pytest.raises(save3ds.Save3dsError):
        save3ds.touch("/sd", "id", FakeKeys(), binary=bin_path)


def test_binary_path_env_override(monkeypatch):
    monkeypatch.setenv("SAVE3DS_FUSE", "/custom/save3ds_fuse")
    assert save3ds.binary_path() == "/custom/save3ds_fuse"


def test_binary_path_explicit_wins(monkeypatch):
    monkeypatch.setenv("SAVE3DS_FUSE", "/env/one")
    assert save3ds.binary_path("/explicit/two") == "/explicit/two"
