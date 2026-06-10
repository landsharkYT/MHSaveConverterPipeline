"""Bridge to the MHGU-MHXX converter submodule.

Loads its non-interactive ``converter_api`` and resolves the bundled blank
template saves. The submodule location is discovered (repo-relative or via
``$MH_CONVERTER_DIR``) — never a hardcoded user path.
"""

import importlib
import os
import sys

from mhpipeline import formats


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CONVERTER_DIR = os.environ.get("MH_CONVERTER_DIR") or os.path.join(
    _repo_root(), "MHXXGUSaveConvert", "MHGU-MHXX-Save-Converter-Script")


class ConverterNotFound(Exception):
    """The converter submodule is missing (did you init submodules?)."""


def _ensure_on_path():
    if not os.path.isdir(os.path.join(CONVERTER_DIR, "modules")):
        raise ConverterNotFound(
            "converter submodule not found at %s "
            "(run: git submodule update --init)" % CONVERTER_DIR)
    if CONVERTER_DIR not in sys.path:
        sys.path.insert(0, CONVERTER_DIR)


def load_api():
    """Import and return the converter's ``converter_api`` module."""
    _ensure_on_path()
    # Dynamic import: the ``modules`` package is only on sys.path at runtime
    # (added by _ensure_on_path), so a static import can't be resolved.
    return importlib.import_module("modules.converter_api")


def blank_3ds_system():
    return os.path.join(CONVERTER_DIR, "Blank_3DS_Save", "system")


def blank_switch_system(switch_game):
    if switch_game == formats.SWITCH_GAME_MHGU:
        return os.path.join(CONVERTER_DIR, "Blank_Switch_Save", "MHGU", "system")
    if switch_game == formats.SWITCH_GAME_MHXX_SWITCH:
        return os.path.join(CONVERTER_DIR, "Blank_Switch_Save",
                            "MHXX Switch Version", "system")
    raise ValueError("unknown switch_game: %r" % (switch_game,))
