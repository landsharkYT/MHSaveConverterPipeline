"""Thin subprocess wrapper around the ``save3ds_fuse`` binary.

Only the three operations the pipeline needs are exposed:

* :func:`touch`   — open+close the archive (key/decrypt validation probe).
* :func:`extract` — decrypt the SD extdata into a directory.
* :func:`import_` — re-encrypt a directory back into the SD extdata.

The binary location is discovered (built submodule path, ``$SAVE3DS_FUSE``
override, or an explicit argument) — never a hardcoded user path.
"""

import os
import subprocess


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Cargo appends .exe on Windows.
_EXE = ".exe" if os.name == "nt" else ""

# Where ``Install Dependencies`` builds the binary (workspace target dir).
DEFAULT_BINARY = os.path.join(
    _repo_root(), "save3ds", "save3ds", "target", "release", "save3ds_fuse" + _EXE)


class Save3dsError(Exception):
    """save3ds_fuse failed (non-zero exit or could not be launched)."""


class Save3dsNotBuilt(Save3dsError):
    """The save3ds_fuse binary does not exist / is not executable yet."""


def binary_path(override=None):
    if override:
        return override
    return os.environ.get("SAVE3DS_FUSE") or DEFAULT_BINARY


def is_built(override=None):
    path = binary_path(override)
    if not os.path.isfile(path):
        return False
    # On Windows the X_OK bit isn't meaningful for .exe files.
    return True if os.name == "nt" else os.access(path, os.X_OK)


def _key_args(sd_root, key_set):
    return ["--sd", sd_root, "--boot9", key_set.boot9, "--movable", key_set.movable]


def _run(args, binary=None):
    path = binary_path(binary)
    if not is_built(binary):
        raise Save3dsNotBuilt(
            "save3ds_fuse not built at %s (run Install Dependencies)" % path)
    try:
        proc = subprocess.run([path] + args, capture_output=True, text=True)
    except OSError as error:
        raise Save3dsError("could not launch save3ds_fuse: %s" % error)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise Save3dsError(
            "save3ds_fuse failed (exit %d): %s" % (proc.returncode, detail))
    return proc


def touch(sd_root, extdata_id, key_set, binary=None):
    """Open+close the SD extdata. Returns ``True`` on success; raises otherwise.

    Used as the profile's decrypt probe: success proves the keys decrypt this SD.
    """
    _run(["--sdext", extdata_id, "--touch"] + _key_args(sd_root, key_set), binary)
    return True


def extract(sd_root, extdata_id, key_set, dest_dir, binary=None):
    """Decrypt the SD extdata into ``dest_dir`` (created if needed)."""
    os.makedirs(dest_dir, exist_ok=True)
    _run(["--sdext", extdata_id, dest_dir, "--extract"] + _key_args(sd_root, key_set),
         binary)
    return dest_dir


def import_(sd_root, extdata_id, key_set, src_dir, binary=None):
    """Re-encrypt the contents of ``src_dir`` back into the SD extdata."""
    _run(["--sdext", extdata_id, src_dir, "--import"] + _key_args(sd_root, key_set),
         binary)
    return True
