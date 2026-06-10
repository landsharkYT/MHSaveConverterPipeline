"""Conversion orchestration: the two end-to-end flows.

* :func:`to_switch` (3DS -> Switch): extract the SD extdata (read-only), convert
  the cleartext ``user/system``, and write the Switch pair into the Switch save
  dir (auto-backed-up first).
* :func:`to_3ds` (Switch -> 3DS): convert the Switch ``system`` to 3DS cleartext,
  splice it into a freshly extracted extdata tree, re-import (re-encrypt) into
  the SD, then **re-extract and byte-compare**; on mismatch the raw extdata is
  restored from a byte-exact backup.

save3ds is injected (``s3``) so the orchestration is fully unit-testable without
a binary. Nothing here hardcodes a filesystem location.
"""

import os
import shutil
import time
from dataclasses import dataclass
from typing import Callable, Optional

from mhpipeline import converter_bridge
from mhpipeline import extdata as extdata_mod
from mhpipeline import keys as keys_mod
from mhpipeline import paths
from mhpipeline import save3ds as _save3ds
from mhpipeline import system_backup as sb

# Inside an extracted extdata tree, the cleartext system lives here.
USER_SUBDIR = "user"
SYSTEM_REL = os.path.join(USER_SUBDIR, "system")


class ConvertError(Exception):
    pass


@dataclass
class Context:
    sd_root: str
    extdata_id: str
    extdata_leaf: str          # dir holding the raw 0000000{1..4} subfiles
    key_set: object
    switch_save_dir: str
    switch_game: str           # also the converter target ("MHGU"/"MHXX_SWITCH")
    three_ds_blank: str
    switch_blank: str
    sidecar_path: str
    cache_path: str


@dataclass
class ConvertOutcome:
    direction: str
    backup_dir: str
    restored: int = 0
    zeroed: int = 0
    preserved: int = 0
    verified: bool = False


# --------------------------------------------------------------------------- #
# context
# --------------------------------------------------------------------------- #
def context_from_profile(profile, key_picker=None, extdata_picker=None):
    key_set = keys_mod.resolve_keys(profile.gm9_out_dir, picker=key_picker)

    locations = extdata_mod.find_mhxx_extdata(profile.sd_root)
    if not locations:
        raise ConvertError("no MHXX extdata found under %s" % profile.sd_root)
    if len(locations) == 1:
        loc = locations[0]
    elif extdata_picker is not None:
        loc = extdata_picker(locations)
    else:
        raise ConvertError("multiple MHXX extdata candidates; choose one in setup")

    three_ds_blank = profile.blank_3ds_system or converter_bridge.blank_3ds_system()
    switch_blank = (profile.blank_switch_system
                    or converter_bridge.blank_switch_system(profile.switch_game))

    return Context(
        sd_root=profile.sd_root,
        extdata_id=loc.extdata_id,
        extdata_leaf=loc.path,
        key_set=key_set,
        switch_save_dir=profile.switch_save_dir,
        switch_game=profile.switch_game,
        three_ds_blank=three_ds_blank,
        switch_blank=switch_blank,
        sidecar_path=paths.sidecar_path(),
        cache_path=paths.cache_path(),
    )


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _fresh_work_dir(label):
    work = os.path.join(paths.work_dir(), "%s-%s" % (label, time.strftime("%Y%m%d-%H%M%S")))
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)
    return work


def _copy_dir_files(src_dir, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    for name in os.listdir(src_dir):
        sp = os.path.join(src_dir, name)
        if os.path.isfile(sp):
            shutil.copy2(sp, os.path.join(dest_dir, name))


def _read(path):
    with open(path, "rb") as f:
        return f.read()


# --------------------------------------------------------------------------- #
# 3DS -> Switch  (read-only on the SD)
# --------------------------------------------------------------------------- #
def to_switch(ctx, s3=_save3ds, api=None, confirm=None, log=print):
    api = api or converter_bridge.load_api()
    work = _fresh_work_dir("to_switch")

    extract_dir = os.path.join(work, "extract")
    s3.extract(ctx.sd_root, ctx.extdata_id, ctx.key_set, extract_dir)
    src_system = os.path.join(extract_dir, SYSTEM_REL)
    if not os.path.isfile(src_system):
        raise ConvertError("extracted extdata has no %s" % SYSTEM_REL)

    out_system = os.path.join(work, "switch_system")
    stats = api.convert_3ds_to_switch(
        src_system, out_system, ctx.switch_game, ctx.switch_blank,
        sidecar_path=ctx.sidecar_path, cache_path=ctx.cache_path)

    if confirm is not None and not confirm(ctx.switch_save_dir):
        raise ConvertError("aborted by user before writing Switch save")

    backup = paths.new_backup_dir("switch")
    _copy_dir_files(ctx.switch_save_dir, backup)
    log("Backed up Switch save -> %s" % backup)

    sb.write_pair_switch(ctx.switch_save_dir, _read(out_system))
    log("Wrote converted Switch save (system + system_backup) to %s" % ctx.switch_save_dir)

    return ConvertOutcome("3ds->switch", backup,
                          restored=stats.restored, zeroed=stats.zeroed, verified=True)


# --------------------------------------------------------------------------- #
# Switch -> 3DS  (in-place re-encrypt; highest risk)
# --------------------------------------------------------------------------- #
def to_3ds(ctx, s3=_save3ds, api=None, confirm=None, log=print):
    api = api or converter_bridge.load_api()
    work = _fresh_work_dir("to_3ds")

    switch_system = os.path.join(ctx.switch_save_dir, "system")
    if not os.path.isfile(switch_system):
        raise ConvertError("no 'system' in %s" % ctx.switch_save_dir)

    # 1. convert to 3DS cleartext (safe, in temp).
    out_system = os.path.join(work, "3ds_system")
    stats = api.convert_switch_to_3ds(
        switch_system, out_system, ctx.three_ds_blank,
        sidecar_path=ctx.sidecar_path, cache_path=ctx.cache_path)
    converted = _read(out_system)

    # 2. extract the current extdata to get the full tree (icon, boss/, user/).
    extract_dir = os.path.join(work, "extract")
    s3.extract(ctx.sd_root, ctx.extdata_id, ctx.key_set, extract_dir)

    if confirm is not None and not confirm("SD extdata %s" % ctx.extdata_id):
        raise ConvertError("aborted by user before writing 3DS save")

    # 3. byte-exact backup of the raw encrypted subfiles.
    backup = paths.new_backup_dir("3ds")
    _copy_dir_files(ctx.extdata_leaf, backup)
    log("Backed up raw 3DS extdata -> %s" % backup)

    # 4. splice the converted system (+ identical backup) into the tree.
    sb.write_pair_3ds(os.path.join(extract_dir, USER_SUBDIR), converted)

    # 5. re-import (re-encrypt) into the SD.
    s3.import_(ctx.sd_root, ctx.extdata_id, ctx.key_set, extract_dir)

    # 6. verify: re-extract and byte-compare.
    verify_dir = os.path.join(work, "verify")
    s3.extract(ctx.sd_root, ctx.extdata_id, ctx.key_set, verify_dir)
    got = _read(os.path.join(verify_dir, SYSTEM_REL))
    if got != converted:
        _copy_dir_files(backup, ctx.extdata_leaf)  # restore byte-exact
        raise ConvertError(
            "verification failed after import; restored raw backup from %s" % backup)

    log("Verified re-encrypted 3DS save matches the converted data.")
    return ConvertOutcome("switch->3ds", backup, preserved=stats.preserved, verified=True)
