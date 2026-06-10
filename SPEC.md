# MH Save Converter Pipeline — Specification

Status: design agreed (grilled 2026-06-10). Not yet implemented.

A CLI wrapper that automates converting Monster Hunter XX / Generations Ultimate
save data between **3DS (MHXX)** and **Switch (MHGU / MHXX-Switch-Version)**,
by orchestrating two existing tools:

- **save3ds** (`save3ds/save3ds/`) — Rust tool; decrypts/encrypts the 3DS side.
- **MHGU-MHXX-Save-Converter-Script** (`MHXXGUSaveConvert/.../`) — Python; does the
  cleartext `system` ↔ `system` byte conversion.

---

## 1. Problem context (established facts)

### 1.1 The two sides

| Side | Format | Encrypted? | Cleartext `system` size |
|------|--------|------------|--------------------------|
| 3DS (MHXX) | SD **extdata** | **Yes** (SD-layer AES, console-unique) | 4 726 152 |
| Switch (MHGU) | plain files | No | 5 159 100 |
| Switch (MHXX-Switch-Version) | plain files | No | 4 726 188 |

### 1.2 The 3DS encrypted save ("the 4 file")

On the SD card the MHXX save is extdata: a folder of numbered subfiles.
Verified from `Example files/3DS sample encrypted/`:

- `00000001` (40 960 B), `00000002` (30 400 B) — metadata.
- `00000003`, `00000004` (4 824 456 B each) — the encrypted `system` /
  `system_backup`. Each = `system` (4 726 152) wrapped in a DIFF container
  (+0x18000) then SD-AES encrypted.

All four files are full-entropy AES (no `DISA`/`DIFF` magic in cleartext) →
**decryption requires console-unique keys** (`boot9.bin` + `movable.sed`).
There is no keyless path.

#### Verified against real hardware (2026-06-10)

Built save3ds and ran it against the real SD; findings that corrected the
design:

- **On-SD layout nests a device dir.** The numbered subfiles live at
  `Nintendo 3DS/<ID0>/<ID1>/extdata/<high>/<low>/00000000/0000000{1..4}` — note
  the extra `00000000` between `<low>` and the files (the loose `Example files`
  folder had them flat). The detector must scan one level deeper.
- **extdata id** = `<high><low>` from the path (e.g. `00000000` + `00001971` =
  `0000000000001971`). Passed to `save3ds --sdext`.
- **`--touch` with the gm9 keys succeeded** → keys decrypt this SD; the whole
  decrypt premise is proven.
- **`--extract` internal tree:** `icon` (14 016 B), `boss/` (empty), and
  `user/system` + `user/system_backup` (4 726 152 each). **The cleartext
  `system` is at `user/system`** — extract/import must use that subpath and
  preserve `icon` + `boss/`.

### 1.3 `system` vs `system_backup` (verified empirically)

- **3DS**: the two are **byte-for-byte identical** (0 bytes differ).
- **Switch**: identical **except 4 bytes at offset `0x14`** — a fixed
  role-marker constant (NOT a checksum; body CRC32 identical for both, and the
  same constants appear in real saves *and* the converter's blank templates):
  - `system`        → `74 ee b2 36`
  - `system_backup` → `92 9b 81 d0`

### 1.4 Chat-tail sidecar (already implemented in the converter)

MHGU stores 104-byte chat entries; 3DS keeps only the first 60. The converter's
`modules/sidecar.py` preserves the Switch-only 44-byte tails across a
Switch→3DS→Switch round trip (adjacent `.mhsidecar` file + content-addressed
cache). Only the **MHGU** path uses it; MHXX-Switch and 3DS-origin paths round
trip losslessly already.

---

## 2. Scope & goals

Full automation of the swap in both directions, profile-driven (configure once,
then convert with no path juggling). The wrapper owns: decryption, conversion,
re-encryption, `system_backup` handling, backups, and verification.

**Out of scope:** editing saves, the README's `FIX_SAVE` flow
(MHXXSwitchSaveEditor recovery), DLC re-download automation.

---

## 3. CLI

Interactive numbered menu (reuse the converter's `art` banner + `colorama`
styling). No flag/argument mode — everything runs from the profile.

```
[1] Convert to Switch
[2] Convert to 3DS
[3] Setup Profile
[4] Install Dependencies
```

- **[1] / [2]** refuse to run unless the profile is **ready** AND dependencies
  are present. Otherwise: a clear error pointing at [3] / [4]. (Graceful
  error-handling if the user ignores [4].)

---

## 4. Profile

Stored as JSON at `~/.config/mhsaveconverter/profile.json` (XDG).
The sidecar cache also lives in this config dir so round trips are stable
regardless of working directory.

### 4.1 Fields

| Field | Meaning | Source |
|-------|---------|--------|
| `sd_root` | Real SD / emulator SD root | user |
| `mhxx_extdata_id` | Detected MHXX extdata id under `.../extdata/` | auto-detected |
| `switch_save_dir` | Folder holding Switch `system`/`system_backup` | user |
| `gm9_out_dir` | GodMode9 output folder holding the keys | user |
| `switch_game` | `MHGU` or `MHXX_SWITCH` (fixes the [1] target) | user |
| `blank_3ds_system` | Optional DLC-bearing 3DS blank override | user (optional) |
| `blank_switch_system` | Optional DLC-bearing Switch blank override | user (optional) |

Keys are **not** stored as direct paths. They are auto-resolved from
`gm9_out_dir` by stable suffix glob (the `SW13517844_`-style prefix varies per
console/dump):

- `*_boot9_00.bin`  (expect 65 536 B)
- `*_movable_00.sed` (expect 320 B)

`boot11_00.bin` / `essential.exefs` are ignored — `--sdext` needs only boot9 +
movable.

### 4.2 Setup behaviour

- Prompt for: `sd_root`, `switch_save_dir`, `gm9_out_dir`, `switch_game`,
  and optional DLC blank overrides.
- Show a prominent **overwrite warning** + **"back up your save first"** notice.

### 4.3 Deep validation (must pass before profile is "ready")

1. Each path exists; key/save files are the expected sizes.
2. **Key resolution** in `gm9_out_dir`:
   - exactly one match each → use it;
   - multiple matches → group by shared `SW########_` prefix, prompt which
     console;
   - zero matches → clear error.
3. **MHXX extdata auto-detect**: scan `sd_root/.../extdata/` for the folder whose
   `00000003`/`00000004` are 4 824 456 B; store its id. Region-agnostic
   (JP/EU/US — don't hardcode).
4. `switch_save_dir/system` length ∈ {5 159 100, 4 726 188} and consistent with
   `switch_game`.
5. **`save3ds --touch`** decrypt test with the resolved keys — proves the keys
   actually decrypt this SD before any conversion is attempted. (This is also
   the one moment the keys are guaranteed present, so it's where the otherwise
   untestable decrypt pipeline gets validated.)

---

## 5. Dependency bootstrap ([4] Install Dependencies)

Run only when the user picks it (not silent/automatic on launch):

1. Install Rust via rustup (if `cargo` missing).
2. Build save3ds: `cargo build --release --no-default-features`
   (no FUSE — we only use `--extract` / `--import` / `--touch`), with
   `RUSTFLAGS="-C target-feature=+aes"` for hardware AES.
3. Python venv + install `art`, `colorama`, `sshkeyboard`.

Convert/Setup degrade gracefully (clear error) if deps are absent.

---

## 6. Converter integration

Refactor the converter's byte-slicing logic into a clean, **non-interactive
API** — no stdin prompts, no keypress-wait (`keyHandler().run()`), no hardcoded
relative paths:

```python
convert_3ds_to_switch(in_path, out_path, target, blank_path, sidecar_dir, cache_path)
convert_switch_to_3ds(in_path, out_path, blank_path, sidecar_dir, cache_path)
```

- The existing interactive menu becomes a thin caller of the same API (no
  behaviour change for direct users of the script).
- `convert_switch_to_3ds` auto-detects MHGU vs MHXX-Switch by input length
  (existing behaviour).
- Sidecar/cache paths point at the config dir.
- Blank template defaults to the bundled `Blank_*` files; overridden by the
  profile's `blank_*_system` when set (DLC preservation — README "Option A").

---

## 7. Conversion flows

### 7.1 Convert to Switch (3DS → Switch)  — read-only on the SD

1. `save3ds_fuse --sdext <id> --sd <sd_root> --boot9 <boot9> --movable <movable>
   --extract <tmp>` → cleartext 3DS `system`.
2. `convert_3ds_to_switch(..., target=switch_game)` → Switch cleartext `system`.
3. Auto-backup the destination `switch_save_dir` (timestamped).
4. Write into `switch_save_dir`:
   - `system` = converted bytes;
   - `system_backup` = converted bytes with `[0x14:0x18] = 92 9b 81 d0`.

### 7.2 Convert to 3DS (Switch → 3DS)  — in-place re-encrypt, highest risk

1. Read `switch_save_dir/system`.
2. `convert_switch_to_3ds(...)` → 3DS cleartext `system`
   (`system_backup` identical).
3. **Auto-backup** the SD extdata (timestamped).
4. `save3ds_fuse --sdext <id> ... --import <tree>` writing both `system` and
   `system_backup` (identical) back into the extdata (re-encrypt + re-sign).
5. **Round-trip verify**: immediately re-extract and byte-compare the decrypted
   result against what we intended to write.
   - match → done;
   - mismatch → **abort and restore the backup**.

---

## 8. Output / safety model

- **Write in place** on both sides (true swap), always preceded by a
  **timestamped auto-backup** of the destination.
- Loud overwrite warning + confirm before any destructive write.
- Switch→3DS additionally guarded by the §7.2 round-trip verify with auto-restore.

---

## 9. Assumptions & residual risk

- **Assumed:** save3ds `--sdext --import` correctly re-signs SD extdata with
  boot9+movable. The §7.2 round-trip verify exists precisely to catch this if
  the assumption is wrong.
- **Untestable in dev:** full 3DS encrypt/decrypt can't be exercised without the
  user's `boot9.bin`/`movable.sed`. Closed at the user's runtime by the
  §4.3 `--touch` test (setup) and §7.2 verify (convert).
- Decided without an explicit ask: Python 3, XDG config path, numbered-menu
  style, region-agnostic extdata detection.

---

## 10. Reference: file sizes

| File | Size (bytes) |
|------|--------------|
| 3DS cleartext `system` / `system_backup` | 4 726 152 |
| 3DS encrypted subfile `00000003` / `00000004` | 4 824 456 |
| MHGU Switch `system` | 5 159 100 |
| MHXX-Switch-Version `system` | 4 726 188 |
| `boot9_00.bin` | 65 536 |
| `movable_00.sed` | 320 |

Switch role marker @ `0x14`: `system` `74 ee b2 36`, `system_backup` `92 9b 81 d0`.
