"""Locate the MHXX SD extdata under a user-supplied SD root (never hardcoded).

The SD root comes from the profile. We don't assume a specific console ID0/ID1
or region — instead we detect the extdata by content: the directory that holds
``00000003`` and ``00000004`` subfiles at the encrypted size. The 16-digit
extdata id is read from the path: the two components right after ``extdata``
(``extdata/<high8>/<low8>``).

Real SD layout nests the numbered subfiles one level deeper, under a device
directory:

    extdata/<high>/<low>/00000000/0000000{1..4}

so we look for the signature both directly in ``<low>`` and in its immediate
subdirectories.
"""

import glob
import os
import string
from dataclasses import dataclass

from mhpipeline.formats import SIZE_3DS_EXTDATA_ENCRYPTED

# The two subfiles that back system / system_backup; their encrypted size is the
# signature we match on.
SIGNATURE_SUBFILES = ("00000003", "00000004")
_HEX = set(string.hexdigits)


class ExtdataError(Exception):
    """The SD root is missing or unreadable."""


@dataclass
class ExtdataLocation:
    path: str   # directory holding the numbered subfiles
    high: str   # 8-hex high word of the extdata id
    low: str    # 8-hex low word of the extdata id

    @property
    def extdata_id(self):
        return (self.high + self.low).lower()


def _looks_like_mhxx_extdata(directory):
    if not os.path.isdir(directory):
        return False
    for name in SIGNATURE_SUBFILES:
        f = os.path.join(directory, name)
        if not os.path.isfile(f) or os.path.getsize(f) != SIZE_3DS_EXTDATA_ENCRYPTED:
            return False
    return True


def _is_hex8(value):
    return len(value) == 8 and all(c in _HEX for c in value)


def _subdirs(directory):
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    return [os.path.join(directory, n) for n in sorted(names)
            if os.path.isdir(os.path.join(directory, n))]


def _scan_extdata_dir(extdata_dir):
    """Yield ExtdataLocation for every MHXX extdata under one ``extdata`` dir."""
    for high_path in _subdirs(extdata_dir):
        high = os.path.basename(high_path)
        if not _is_hex8(high):
            continue
        for low_path in _subdirs(high_path):
            low = os.path.basename(low_path)
            if not _is_hex8(low):
                continue
            # Signature files may sit directly in <low> or one level deeper
            # (the device directory, e.g. <low>/00000000/).
            for leaf in [low_path] + _subdirs(low_path):
                if _looks_like_mhxx_extdata(leaf):
                    yield ExtdataLocation(leaf, high, low)
                    break  # one device dir per extdata


def find_mhxx_extdata(sd_root):
    """Return all MHXX-extdata locations found under ``sd_root``.

    Detection is by content, so the looser patterns can't yield false positives.
    """
    if not os.path.isdir(sd_root):
        raise ExtdataError("SD root does not exist: %s" % sd_root)

    extdata_dirs = []
    extdata_dirs += glob.glob(os.path.join(sd_root, "Nintendo 3DS", "*", "*", "extdata"))
    extdata_dirs += glob.glob(os.path.join(sd_root, "extdata"))  # sd_root pointed deeper

    found = []
    seen = set()
    for extdata_dir in sorted(set(extdata_dirs)):
        for loc in _scan_extdata_dir(extdata_dir):
            real = os.path.realpath(loc.path)
            if real not in seen:
                seen.add(real)
                found.append(loc)
    return found
