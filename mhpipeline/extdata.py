"""Locate the MHXX SD extdata under a user-supplied SD root (never hardcoded).

The SD root comes from the profile. We don't assume a specific console ID0/ID1
or region — instead we detect the extdata by content: the leaf directory that
holds ``00000003`` and ``00000004`` subfiles at the encrypted size. The 16-digit
extdata id is read back from the path (``extdata/<high8>/<low8>``).
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
    path: str   # leaf directory holding the numbered subfiles
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


def _id_words(directory):
    """Best-effort (high, low) from ``.../extdata/<high>/<low>`` layout."""
    low = os.path.basename(directory)
    parent = os.path.basename(os.path.dirname(directory))
    high = parent if _is_hex8(parent) else "00000000"
    if not _is_hex8(low):
        low = "00000000"
    return high, low


def find_mhxx_extdata(sd_root):
    """Return all MHXX-extdata leaf locations found under ``sd_root``.

    Tries the standard SD layout first, then a couple of looser patterns so a
    user can point ``sd_root`` slightly deeper. Matching is by content, so the
    looser patterns can't produce false positives.
    """
    if not os.path.isdir(sd_root):
        raise ExtdataError("SD root does not exist: %s" % sd_root)

    patterns = [
        os.path.join(sd_root, "Nintendo 3DS", "*", "*", "extdata", "*", "*"),
        os.path.join(sd_root, "extdata", "*", "*"),
        os.path.join(sd_root, "*", "*"),
    ]
    seen = set()
    found = []
    for pattern in patterns:
        for directory in sorted(glob.glob(pattern)):
            real = os.path.realpath(directory)
            if real in seen:
                continue
            seen.add(real)
            if _looks_like_mhxx_extdata(directory):
                high, low = _id_words(directory)
                found.append(ExtdataLocation(directory, high, low))
    # Allow sd_root itself to be the leaf (e.g. a loose numbered-file folder).
    if _looks_like_mhxx_extdata(sd_root):
        high, low = _id_words(sd_root)
        found.append(ExtdataLocation(sd_root, high, low))
    return found
