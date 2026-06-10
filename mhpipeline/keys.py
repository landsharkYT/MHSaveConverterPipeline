"""Resolve console keys (boot9 + movable.sed) from a GodMode9 output directory.

The directory is supplied by the user (profile ``gm9_out_dir``) — never
hardcoded. Key files carry a console/dump-specific prefix that varies (e.g.
``SW13517844_``), so they are discovered by their stable suffixes:

    *_boot9_00.bin   (65536 bytes)
    *_movable_00.sed (288 or 320 bytes)

A boot9 and a movable.sed sharing the same prefix form one console's key set.
"""

import glob
import os
from dataclasses import dataclass
from typing import Callable, List, Optional

BOOT9_SUFFIX = "_boot9_00.bin"
MOVABLE_SUFFIX = "_movable_00.sed"

BOOT9_SIZE = 65536
MOVABLE_SIZES = (288, 320)


class KeyResolutionError(Exception):
    """No usable key set, or a key file has an unexpected size."""


class AmbiguousKeysError(KeyResolutionError):
    """More than one console key set present; the caller must choose."""

    def __init__(self, message, key_sets):
        super().__init__(message)
        self.key_sets = key_sets


@dataclass
class KeySet:
    prefix: str
    boot9: str
    movable: str


def find_key_sets(gm9_out_dir):
    """Return every (boot9, movable) pair sharing a prefix in ``gm9_out_dir``."""
    sets = []
    for boot9 in sorted(glob.glob(os.path.join(gm9_out_dir, "*" + BOOT9_SUFFIX))):
        prefix = os.path.basename(boot9)[:-len(BOOT9_SUFFIX)]
        movable = os.path.join(gm9_out_dir, prefix + MOVABLE_SUFFIX)
        if os.path.isfile(movable):
            sets.append(KeySet(prefix, boot9, movable))
    return sets


def validate_key_sizes(key_set):
    boot9_size = os.path.getsize(key_set.boot9)
    if boot9_size != BOOT9_SIZE:
        raise KeyResolutionError(
            "boot9 '%s' has unexpected size %d (expected %d)"
            % (key_set.boot9, boot9_size, BOOT9_SIZE))
    movable_size = os.path.getsize(key_set.movable)
    if movable_size not in MOVABLE_SIZES:
        raise KeyResolutionError(
            "movable.sed '%s' has unexpected size %d (expected one of %s)"
            % (key_set.movable, movable_size, MOVABLE_SIZES))


def resolve_keys(gm9_out_dir, picker=None):
    """Resolve the single console key set in ``gm9_out_dir``.

    ``picker(key_sets) -> KeySet`` disambiguates when several consoles are
    present; without it, ambiguity raises :class:`AmbiguousKeysError`.
    """
    if not os.path.isdir(gm9_out_dir):
        raise KeyResolutionError("gm9 output dir does not exist: %s" % gm9_out_dir)

    sets = find_key_sets(gm9_out_dir)
    if not sets:
        raise KeyResolutionError(
            "No key pair in %s (need a *%s and a matching *%s)"
            % (gm9_out_dir, BOOT9_SUFFIX, MOVABLE_SUFFIX))
    if len(sets) == 1:
        key_set = sets[0]
    elif picker is not None:
        key_set = picker(sets)
    else:
        raise AmbiguousKeysError(
            "Multiple console key sets in %s: %s"
            % (gm9_out_dir, ", ".join(s.prefix for s in sets)),
            sets)

    validate_key_sizes(key_set)
    return key_set
