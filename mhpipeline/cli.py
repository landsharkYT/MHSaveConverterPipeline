"""Interactive CLI: the 4-option menu, Setup Profile flow, and convert gating.

Convert actions ([1]/[2]) are blocked until dependencies are installed and the
profile is fully validated. The only destructive operations happen inside the
convert flows, behind a loud overwrite warning + confirmation + auto-backup.
"""

import os

from mhpipeline import convert
from mhpipeline import deps
from mhpipeline import extdata as extdata_mod
from mhpipeline import formats
from mhpipeline import keys as keys_mod
from mhpipeline import paths
from mhpipeline import save3ds
from mhpipeline import ui
from mhpipeline.profile import Profile


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _prompt_path(label, current):
    shown = " [%s]" % current if current else ""
    value = ui.prompt("%s%s:" % (label, shown)).strip()
    return value or current


def _key_picker(key_sets):
    idx = ui.menu("Multiple console key sets found — choose one:",
                  [s.prefix for s in key_sets])
    return key_sets[idx - 1]


def _extdata_picker(locations):
    idx = ui.menu("Multiple MHXX extdata found — choose one:",
                  ["%s  (%s)" % (l.extdata_id, l.path) for l in locations])
    return locations[idx - 1]


def _print_validation(result):
    for c in result.checks:
        tag = "OK  " if c.ok else ("PEND" if c.pending else "FAIL")
        line = "[%s] %s%s" % (tag, c.name, (" — %s" % c.detail) if c.detail else "")
        (ui.info if c.ok else (ui.warn if c.pending else ui.error))(line)


def _print_deps(report):
    for item in report.items:
        line = "%s%s" % (item.name, (" — %s" % item.detail) if item.detail else "")
        (ui.info if item.ok else ui.warn)(line)


def _confirm_overwrite(target_desc):
    ui.overwrite_warning(target_desc)
    return ui.confirm("Proceed with the overwrite?", default=False)


# --------------------------------------------------------------------------- #
# [3] Setup Profile
# --------------------------------------------------------------------------- #
def setup_profile(profile):
    ui.info("Setting up your profile. Press Enter to keep the [current] value.")
    profile.sd_root = _prompt_path("SD card / emulator SD root", profile.sd_root)
    profile.switch_save_dir = _prompt_path(
        "Switch save folder (the one containing 'system')", profile.switch_save_dir)
    profile.gm9_out_dir = _prompt_path(
        "GodMode9 output folder (holds *_boot9_00.bin / *_movable_00.sed)",
        profile.gm9_out_dir)

    choice = ui.menu("Which Switch game do you convert to/from?",
                     ["MHGU", "MHXX Switch Version"])
    profile.switch_game = (formats.SWITCH_GAME_MHGU if choice == 1
                           else formats.SWITCH_GAME_MHXX_SWITCH)

    has_override = bool(profile.blank_3ds_system or profile.blank_switch_system)
    if ui.confirm("Use custom DLC-bearing blank templates?", default=has_override):
        profile.blank_3ds_system = _prompt_path("  3DS blank 'system'",
                                                profile.blank_3ds_system) or None
        profile.blank_switch_system = _prompt_path("  Switch blank 'system'",
                                                   profile.blank_switch_system) or None
    else:
        profile.blank_3ds_system = None
        profile.blank_switch_system = None

    _detect_extdata_into(profile)

    touch = save3ds.touch if save3ds.is_built() else None
    result = profile.validate(deep=True, save3ds_touch=touch)
    ui.info("Validation:")
    _print_validation(result)

    profile.save()
    ui.info("Profile saved to %s" % paths.profile_path())
    if result.fully_validated:
        ui.info("Profile is fully validated and ready to convert.")
    elif result.ok:
        ui.warn("Profile is usable but some checks are pending "
                "(run [4] Install Dependencies to finish the key test).")
    else:
        ui.error("Fix the failing checks above before converting.")
    return profile


def _detect_extdata_into(profile):
    if not profile.sd_root or not os.path.isdir(profile.sd_root):
        return
    try:
        locations = extdata_mod.find_mhxx_extdata(profile.sd_root)
    except extdata_mod.ExtdataError as error:
        ui.error(str(error))
        return
    if not locations:
        ui.warn("No MHXX extdata found under the SD root yet.")
        profile.mhxx_extdata = None
        return
    chosen = locations[0] if len(locations) == 1 else _extdata_picker(locations)
    profile.mhxx_extdata = {"extdata_id": chosen.extdata_id, "path": chosen.path}
    ui.info("MHXX extdata detected: %s" % chosen.extdata_id)


# --------------------------------------------------------------------------- #
# [4] Install Dependencies
# --------------------------------------------------------------------------- #
def install_dependencies():
    ui.warn("This may install Rust, compile save3ds, and pip-install packages. "
            "It can take several minutes.")
    if not ui.confirm("Continue?", default=True):
        return
    try:
        report = deps.install(log=ui.info)
    except deps.DepError as error:
        ui.error(str(error))
        return
    ui.info("Dependency status:")
    _print_deps(report)


# --------------------------------------------------------------------------- #
# [1]/[2] Convert
# --------------------------------------------------------------------------- #
def _ready_for_convert(profile):
    report = deps.check()
    if not report.ok:
        ui.error("Dependencies are missing — run [4] Install Dependencies:")
        for item in report.missing:
            ui.warn("  - %s (%s)" % (item.name, item.detail))
        return False
    if not profile.has_required():
        ui.error("Profile is incomplete — run [3] Setup Profile.")
        return False
    result = profile.validate(deep=True, save3ds_touch=save3ds.touch)
    if not result.fully_validated:
        ui.error("Profile validation failed — run [3] Setup Profile:")
        _print_validation(result)
        return False
    return True


def _build_context(profile):
    return convert.context_from_profile(
        profile, key_picker=_key_picker, extdata_picker=_extdata_picker)


def convert_to_switch(profile):
    if not _ready_for_convert(profile):
        return
    try:
        ctx = _build_context(profile)
        outcome = convert.to_switch(ctx, confirm=_confirm_overwrite, log=ui.info)
    except (convert.ConvertError, keys_mod.KeyResolutionError,
            extdata_mod.ExtdataError, save3ds.Save3dsError) as error:
        ui.error(str(error))
        return
    ui.info("Converted to Switch. Restored %d chat tails, zeroed %d."
            % (outcome.restored, outcome.zeroed))
    ui.info("Backup of previous Switch save: %s" % outcome.backup_dir)


def convert_to_3ds(profile):
    if not _ready_for_convert(profile):
        return
    try:
        ctx = _build_context(profile)
        outcome = convert.to_3ds(ctx, confirm=_confirm_overwrite, log=ui.info)
    except (convert.ConvertError, keys_mod.KeyResolutionError,
            extdata_mod.ExtdataError, save3ds.Save3dsError) as error:
        ui.error(str(error))
        return
    ui.info("Converted to 3DS and verified (%s). Preserved %d chat tails."
            % (outcome.verified, outcome.preserved))
    ui.info("Byte-exact backup of previous 3DS extdata: %s" % outcome.backup_dir)


# --------------------------------------------------------------------------- #
# main loop
# --------------------------------------------------------------------------- #
def _status_line(profile):
    prof = "ready" if profile.has_required() else "not set up"
    dps = "ok" if deps.check().ok else "missing"
    return "profile: %s | deps: %s" % (prof, dps)


def main():
    ui.banner()
    while True:
        profile = Profile.load()
        choice = ui.menu(
            "Main menu  (%s)" % _status_line(profile),
            ["Convert to Switch", "Convert to 3DS", "Setup Profile",
             "Install Dependencies", "Exit"])
        if choice == 1:
            convert_to_switch(profile)
        elif choice == 2:
            convert_to_3ds(profile)
        elif choice == 3:
            setup_profile(profile)
        elif choice == 4:
            install_dependencies()
        else:
            ui.info("Bye.")
            return
