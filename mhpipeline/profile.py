"""User profile: persisted configuration + deep validation.

The profile holds only user-supplied locations (SD root, Switch save dir, the
GodMode9 key dir, optional DLC-blank overrides) and the chosen Switch game.
Nothing is hardcoded; everything is entered during setup. ``validate`` performs
the deep checks from SPEC.md §4.3, including a save3ds ``--touch`` decrypt probe
when a probe callable is injected (wired in Phase 3).
"""

import json
import os
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from mhpipeline import extdata as extdata_mod
from mhpipeline import formats
from mhpipeline import keys as keys_mod
from mhpipeline import paths

REQUIRED_FIELDS = ("sd_root", "switch_save_dir", "gm9_out_dir", "switch_game")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    pending: bool = False  # couldn't be run yet (e.g. save3ds not built)


@dataclass
class ValidationResult:
    checks: List[Check] = field(default_factory=list)

    def add(self, name, ok, detail="", pending=False):
        self.checks.append(Check(name, ok, detail, pending))
        return ok

    @property
    def hard_failures(self):
        return [c for c in self.checks if not c.ok and not c.pending]

    @property
    def pendings(self):
        return [c for c in self.checks if c.pending]

    @property
    def ok(self):
        """Usable: no hard failures (pending checks are tolerated)."""
        return not self.hard_failures

    @property
    def fully_validated(self):
        """Everything passed, including the save3ds key probe."""
        return all(c.ok for c in self.checks)


@dataclass
class Profile:
    sd_root: Optional[str] = None
    switch_save_dir: Optional[str] = None
    gm9_out_dir: Optional[str] = None
    switch_game: Optional[str] = None
    blank_3ds_system: Optional[str] = None
    blank_switch_system: Optional[str] = None
    mhxx_extdata: Optional[dict] = None  # {"extdata_id": ..., "path": ...}

    # ------------------------------------------------------------------ #
    # persistence
    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, path=None):
        path = path or paths.profile_path()
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return cls()
        known = {k: data.get(k) for k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self, path=None):
        path = path or paths.profile_path()
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)
        return path

    # ------------------------------------------------------------------ #
    # status
    # ------------------------------------------------------------------ #
    def has_required(self):
        return all(getattr(self, k) for k in REQUIRED_FIELDS)

    def is_ready(self):
        return self.validate(deep=True).ok

    # ------------------------------------------------------------------ #
    # validation
    # ------------------------------------------------------------------ #
    def validate(self, deep=True, save3ds_touch=None):
        """Validate the profile.

        ``save3ds_touch(sd_root, extdata_id, key_set) -> bool`` runs the decrypt
        probe; if omitted, that check is recorded as *pending* (so a profile can
        be configured before dependencies are installed).
        """
        result = ValidationResult()

        missing = [k for k in REQUIRED_FIELDS if not getattr(self, k)]
        if not result.add("required fields", not missing,
                          ("missing: " + ", ".join(missing)) if missing else "all set"):
            return result

        result.add("switch_game valid", self.switch_game in formats.SWITCH_GAMES,
                   str(self.switch_game))

        if not deep:
            return result

        result.add("sd_root exists", os.path.isdir(self.sd_root), str(self.sd_root))
        self._check_switch_save(result)
        key_set = self._check_keys(result)
        extdata = self._resolve_extdata(result)
        self._check_touch(result, save3ds_touch, key_set, extdata)
        self._check_blank(result, "blank_3ds_system", self.blank_3ds_system, formats.SIZE_3DS)
        self._check_blank(result, "blank_switch_system", self.blank_switch_system,
                          formats.switch_system_size(self.switch_game)
                          if self.switch_game in formats.SWITCH_GAMES else None)
        return result

    def _check_switch_save(self, result):
        system = os.path.join(self.switch_save_dir, "system")
        if not os.path.isfile(system):
            result.add("switch save present", False,
                       "no 'system' in %s" % self.switch_save_dir)
            return
        if self.switch_game not in formats.SWITCH_GAMES:
            return  # already flagged
        want = formats.switch_system_size(self.switch_game)
        size = os.path.getsize(system)
        result.add("switch system size", size == want,
                   "%d (expected %d for %s)" % (size, want, self.switch_game))

    def _check_keys(self, result):
        try:
            key_set = keys_mod.resolve_keys(self.gm9_out_dir)
            result.add("keys resolve", True,
                       "boot9=%s movable=%s" % (os.path.basename(key_set.boot9),
                                                os.path.basename(key_set.movable)))
            return key_set
        except keys_mod.KeyResolutionError as error:
            result.add("keys resolve", False, str(error))
            return None

    def _resolve_extdata(self, result):
        try:
            found = extdata_mod.find_mhxx_extdata(self.sd_root)
        except extdata_mod.ExtdataError as error:
            result.add("MHXX extdata found", False, str(error))
            return None
        if not found:
            result.add("MHXX extdata found", False, "none under %s" % self.sd_root)
            return None
        # Honour a previously chosen extdata if it is still present.
        if self.mhxx_extdata:
            for f in found:
                if f.extdata_id == self.mhxx_extdata.get("extdata_id"):
                    result.add("MHXX extdata found", True, f.extdata_id)
                    return self.mhxx_extdata
        if len(found) == 1:
            result.add("MHXX extdata found", True, found[0].extdata_id)
            return {"extdata_id": found[0].extdata_id, "path": found[0].path}
        result.add("MHXX extdata found", False,
                   "%d candidates; choose one during setup" % len(found))
        return None

    def _check_touch(self, result, save3ds_touch, key_set, extdata):
        if save3ds_touch is None:
            result.add("save3ds key test", False,
                       "save3ds not available yet (run Install Dependencies)",
                       pending=True)
            return
        if key_set is None or extdata is None:
            result.add("save3ds key test", False,
                       "skipped (keys/extdata unresolved)", pending=True)
            return
        try:
            ok = save3ds_touch(self.sd_root, extdata["extdata_id"], key_set)
            result.add("save3ds key test", bool(ok),
                       "decrypt probe %s" % ("passed" if ok else "FAILED"))
        except Exception as error:  # noqa: BLE001 - surface any probe failure
            result.add("save3ds key test", False, "probe error: %s" % error)

    def _check_blank(self, result, name, path, want):
        if not path:
            return  # bundled blank will be used
        if not os.path.isfile(path):
            result.add(name, False, "missing: %s" % path)
            return
        if want is None:
            return
        size = os.path.getsize(path)
        result.add(name, size == want, "%d (expected %d)" % (size, want))
