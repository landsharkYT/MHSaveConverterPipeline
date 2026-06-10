# Implementation Plan — MH Save Converter Pipeline

Build sequence for the wrapper specified in [SPEC.md](SPEC.md). Ordered so each
phase is independently testable; the risky 3DS encrypt/decrypt is isolated last
behind interfaces that can be unit-tested without console keys.

---

## Project layout

New top-level Python package alongside the two existing tool dirs:

```
MHSaveConverterPipeline/
├── SPEC.md
├── PLAN.md
├── mhpipeline/
│   ├── __init__.py
│   ├── __main__.py          # `python -m mhpipeline` entry → cli.main()
│   ├── cli.py               # menu loop, 4 options, gating
│   ├── profile.py           # load/save/validate profile JSON
│   ├── keys.py              # gm9_out_dir suffix-glob key resolution
│   ├── save3ds.py           # subprocess wrapper: extract/import/touch
│   ├── extdata.py           # SD extdata auto-detect; backup/restore
│   ├── convert.py           # orchestration: the two flows (§7)
│   ├── system_backup.py     # role-marker rule (§1.3)
│   ├── deps.py              # [4] bootstrap: rust/save3ds/py deps
│   ├── ui.py                # banner, colors, prompts, warnings (reuse art/colorama)
│   └── paths.py             # XDG config dir, tmp/backup dirs
├── tests/
│   ├── test_system_backup.py
│   ├── test_profile.py
│   ├── test_keys.py
│   └── test_convert_cleartext.py   # uses Example files/
└── requirements.txt         # art, colorama, sshkeyboard
```

The converter stays where it is; we import its refactored API
(`MHXXGUSaveConvert/.../modules`). Make it importable via a path shim or a small
`pyproject`/`sys.path` insert in `convert.py`.

---

## Phase 0 — Converter API refactor (no wrapper code yet)

Goal: pure, non-interactive conversion functions; existing menu unchanged for
direct users.

1. In `modules/mhxx_to_mhguxx.py` and `modules/mhguxx_to_mhxx.py`, extract the
   byte-slicing core into:
   - `convert_3ds_to_switch(in_path, out_path, target, blank_path, sidecar_dir, cache_path) -> Stats`
   - `convert_switch_to_3ds(in_path, out_path, blank_path, sidecar_dir, cache_path) -> Stats`
   No `tprint`, no `custom_input`, no `keyHandler().run()`, no hardcoded paths.
   Return a small dataclass (restored/zeroed counts, detected source format).
2. Rewrite the original menu functions (`mhxx_to_mhguxx()`, `mhguxx_to_mhxx()`)
   to gather inputs interactively then call the new core — behaviour preserved.
3. Length validation stays, but raises a typed exception
   (`ConversionError`) instead of logging + waiting for a keypress.
4. Sidecar/cache paths become parameters (no module-level `CACHE_PATH`).

**Test:** `test_convert_cleartext.py` round-trips `Example files/3DS sample
files/system` → Switch → 3DS and asserts byte-equality where expected, plus
MHGU chat-tail preservation via the sidecar. Runs with **no keys** — pure
cleartext.

**Checkpoint:** existing `mhgu_mhxx_save_converter.py` menu still works manually.

---

## Phase 1 — Foundations (pure, no external tools)

1. `paths.py`: resolve `~/.config/mhsaveconverter/` (respect `XDG_CONFIG_HOME`);
   helpers for backup dir + tmp work dir.
2. `system_backup.py`:
   - `write_pair_3ds(dir, data)` → `system` and `system_backup` identical.
   - `write_pair_switch(dir, data)` → `system` = data; `system_backup` = data
     with `[0x14:0x18] = b"\x92\x9b\x81\xd0"`.
   - Constants `SYSTEM_MARKER = 74 ee b2 36`, `BACKUP_MARKER = 92 9b 81 d0`.
3. `ui.py`: banner, colored prompts, yes/no confirm, the overwrite warning block.

**Test:** `test_system_backup.py` — assert markers + body equality against the
`Example files` Switch pair.

---

## Phase 2 — Profile + keys (deep validation, the testable parts)

1. `keys.py`: `resolve_keys(gm9_out_dir) -> Keys(boot9, movable)`:
   - glob `*_boot9_00.bin` / `*_movable_00.sed`;
   - 1 each → use; multiple → group by `SW\d+_` prefix, prompt; 0 → error;
   - size checks (65536 / 320).
2. `extdata.py`: `detect_mhxx_extdata(sd_root) -> (extdata_id, path)` by scanning
   `.../extdata/*/*` for a dir whose `00000003`/`00000004` are 4 824 456 B.
3. `profile.py`:
   - dataclass + JSON load/save at `paths.config/profile.json`;
   - `setup()` interactive flow (prompts, DLC-blank overrides, warning);
   - `validate(deep=True)` running checks §4.3 #1–#4 **plus** the `--touch` test
     (#5) delegated to `save3ds.py`;
   - `is_ready()` used by CLI gating.

**Test:** `test_keys.py` (synthetic gm9 dirs incl. multi-prefix), `test_profile.py`
(round-trip + validation error paths). The live `--touch` check is exercised
manually against the real SD (keys only exist at the user's runtime).

---

## Phase 3 — save3ds wrapper + dependency bootstrap

1. `save3ds.py`: locate the built binary
   (`save3ds/save3ds/target/release/save3ds_fuse`); functions:
   - `touch(sd_root, extdata_id, keys)` → bool (validation probe).
   - `extract(sd_root, extdata_id, keys, dest_dir)`.
   - `import_(sd_root, extdata_id, keys, src_dir)`.
   Raises `Save3dsError` with captured stderr.
2. `deps.py` ([4]): detect `cargo`; build
   `cargo build --release --no-default-features` (RUSTFLAGS aes); create venv +
   `pip install -r requirements.txt`. Each step idempotent, reports status.
   `check()` returns a structured readiness report the CLI surfaces.

**Test:** `touch()` against the real SD manually (proves keys+build). Unit-test
the argv assembly with a fake binary.

---

## Phase 4 — Orchestration (the two flows)

`convert.py`:

1. `to_switch()` (§7.1): `save3ds.extract` → tmp → `convert_3ds_to_switch` →
   backup `switch_save_dir` → `write_pair_switch`.
2. `to_3ds()` (§7.2): read Switch `system` → `convert_switch_to_3ds` → tmp tree
   via `write_pair_3ds` → backup extdata → `save3ds.import_` → **re-extract +
   byte-compare** vs intended → on mismatch restore backup and raise.
3. All destructive writes funnel through one `backup_then(path)` helper +
   the confirm prompt.

**Test:** `to_switch` is fully testable end-to-end *if* keys present; otherwise
mock `save3ds` and test the orchestration/backup/verify logic with the cleartext
converter real.

---

## Phase 5 — CLI wiring

`cli.py`: menu loop (reuse `ui`), the 4 options, gating:

- [1]/[2] → require `profile.is_ready()` AND `deps.check().ok`; else error →
  point at [3]/[4].
- [3] → `profile.setup()` + `validate(deep=True)`.
- [4] → `deps.install()`.

`__main__.py` → `cli.main()`. Add a console-script entry if desired.

**Checkpoint:** full manual run-through on the real SD by the user.

---

## Phase 6 — Docs & polish

- `README.md` for `mhpipeline/`: install, first-run ([4] then [3]), the swap
  flows, the loud "back up first" notice.
- Confirm `.gitignore` covers config/tmp/backups and the rust `target/`.

---

## Testing strategy summary

| Layer | Keys needed? | How |
|-------|-------------|-----|
| Converter API, system_backup, keys glob, profile JSON | No | pytest + `Example files/` |
| save3ds argv assembly, orchestration/verify logic | No | mocks + fakes |
| `--touch`, real extract/import, end-to-end swap | Yes | manual, user's SD |

The key-dependent surface is deliberately thin and isolated behind `save3ds.py`,
so everything else has real automated coverage.

---

## Build order (dependency-respecting)

Phase 0 → 1 → 2 → 3 → 4 → 5 → 6.
Phases 0–2 and the unit-testable parts of 3–4 need no console keys; the
remaining key-dependent verification is a single manual pass at the end.

## Open confirmations before coding

- Package name `mhpipeline` and `python -m mhpipeline` entry point — ok?
- Auto-`git init` the pipeline root (currently not a repo) for safe iteration?
