"""Canonical Monster Hunter save format constants (sizes and IDs only).

These are facts about the save *format*, not file locations — see SPEC.md §10.
No filesystem paths belong here.
"""

# Cleartext system sizes
SIZE_3DS = 4726152
SIZE_MHGU = 5159100
SIZE_MHXX_SWITCH = 4726188

# A 3DS extdata subfile (system / system_backup) after DIFF-wrap + SD-AES.
SIZE_3DS_EXTDATA_ENCRYPTED = 4824456

# Switch game selector (matches converter_api.TARGET_* string values)
SWITCH_GAME_MHGU = "MHGU"
SWITCH_GAME_MHXX_SWITCH = "MHXX_SWITCH"
SWITCH_GAMES = (SWITCH_GAME_MHGU, SWITCH_GAME_MHXX_SWITCH)


def switch_system_size(switch_game):
    """Expected cleartext ``system`` size for the configured Switch game."""
    if switch_game == SWITCH_GAME_MHGU:
        return SIZE_MHGU
    if switch_game == SWITCH_GAME_MHXX_SWITCH:
        return SIZE_MHXX_SWITCH
    raise ValueError("unknown switch_game: %r" % (switch_game,))
