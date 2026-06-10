"""Filesystem locations for the wrapper.

Everything the wrapper persists lives under one XDG config dir
(``~/.config/mhsaveconverter`` by default): the profile, the chat-tail sidecar
+ cache (so round trips are stable regardless of working directory), backups,
and scratch space.
"""

import os
import time

APP_NAME = "mhsaveconverter"


def config_dir():
    """Base config directory.

    Windows: ``%APPDATA%\\mhsaveconverter``. Elsewhere: ``$XDG_CONFIG_HOME`` (or
    ``~/.config``) ``/mhsaveconverter``.
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME)


def ensure_config_dir():
    os.makedirs(config_dir(), exist_ok=True)
    return config_dir()


def profile_path():
    return os.path.join(config_dir(), "profile.json")


def cache_path():
    """Content-addressed chat-tail cache (round-trip fallback)."""
    return os.path.join(config_dir(), "sidecar_cache", "tails.bin")


def sidecar_path():
    """Adjacent chat-tail sidecar, kept in the config dir (not next to saves)."""
    return os.path.join(config_dir(), "system.mhsidecar")


def backups_dir():
    return os.path.join(config_dir(), "backups")


def work_dir():
    """Scratch directory for extract/convert/import staging."""
    return os.path.join(config_dir(), "tmp_work")


def timestamp():
    return time.strftime("%Y%m%d-%H%M%S")


def new_backup_dir(label):
    """Create and return a fresh timestamped backup dir, e.g. ``3ds-20260610-153012``."""
    path = os.path.join(backups_dir(), "%s-%s" % (label, timestamp()))
    os.makedirs(path, exist_ok=True)
    return path
