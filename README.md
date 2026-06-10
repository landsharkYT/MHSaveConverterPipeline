# MH Save Converter Pipeline

A CLI wrapper that automates converting **Monster Hunter XX / Generations
Ultimate** saves between **3DS (MHXX)** and **Switch (MHGU / MHXX-Switch)**.

It orchestrates two tools so you don't have to run them by hand:

- **[save3ds](save3ds/save3ds)** — decrypts/encrypts the 3DS side (the SD
  extdata, using your console keys).
- **[MHGU-MHXX-Save-Converter-Script](MHXXGUSaveConvert/MHGU-MHXX-Save-Converter-Script)**
  — does the cleartext `system` ↔ `system` byte conversion (including lossless
  MHGU chat-tail preservation).

Both live here as **git submodules** (forks). The wrapper itself is the
`mhpipeline/` Python package.

> ⚠️ **Back up your saves before using this.** The Switch→3DS direction
> overwrites your SD extdata in place. The tool takes its own timestamped
> backup and verifies every write, but keep your own copy too.

---

## How it works

| Direction | What happens |
|-----------|--------------|
| **3DS → Switch** | `save3ds` **extracts** (decrypts) your SD extdata → the converter turns `user/system` into a Switch `system` → written to your Switch save folder (`system` + `system_backup`). Read-only on the SD. |
| **Switch → 3DS** | The converter turns your Switch `system` into a 3DS `system` → spliced into a freshly extracted extdata tree → `save3ds` **imports** (re-encrypts) it back onto the SD → **re-extracted and byte-compared**; on any mismatch the original is restored from a byte-exact backup. |

Everything is profile-driven: configure your locations once, then convert.

## Requirements

- Linux (save3ds is built in no-FUSE mode; extract/import only).
- Your console keys, dumped with **GodMode9**: `*_boot9_00.bin` and
  `*_movable_00.sed` (in a `gm9/out` folder). These are required — 3DS SD
  extdata cannot be decrypted without them.
- Python 3.8+ and a Rust toolchain (the app can install Rust for you).

## Install

```bash
git clone --recurse-submodules <this-repo>
cd MHSaveConverterPipeline

python -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -r requirements.txt         # or: pip install -e .
```

(If you cloned without `--recurse-submodules`: `git submodule update --init`.)

### Platform notes

- **Linux/macOS:** `[4] Install Dependencies` can install Rust for you.
- **Windows:** auto-installing Rust isn't supported — install it once from
  <https://rustup.rs> (run `rustup-init.exe`), then run `[4]`; it builds
  `save3ds_fuse.exe` and installs the Python deps. save3ds uses no FUSE here
  (extract/import only), so Windows is supported. Config/backups live under
  `%APPDATA%\mhsaveconverter`.

## Usage

```bash
python -m mhpipeline        # or the `mhsaveconvert` command if pip-installed
```

You get a menu:

```
[1] Convert to Switch
[2] Convert to 3DS
[3] Setup Profile
[4] Install Dependencies
[5] Exit
```

First run, in order:

1. **[4] Install Dependencies** — installs Rust (if missing), builds
   `save3ds_fuse`, and installs the Python packages.
2. **[3] Setup Profile** — you'll be asked for:
   - your **SD root** (e.g. the mounted SD card / emulator SD),
   - your **Switch save folder** (the one containing `system`),
   - your **GodMode9 output folder** (where the `*_boot9_00.bin` /
     `*_movable_00.sed` live),
   - which **Switch game** you use (MHGU or MHXX Switch Version),
   - optionally, **custom DLC-bearing blank templates** (otherwise the bundled
     DLC-free blanks are used; you can re-download DLC in-game instead).

   Setup deep-validates everything, including an actual `save3ds --touch`
   decrypt test with your keys, before marking the profile ready.
3. **[1] / [2]** — convert. These are blocked until the profile is fully
   validated and dependencies are installed. Each destructive write shows a
   warning, takes a backup, and (for 3DS) verifies the result.

Config, backups, and the chat-tail sidecar/cache live under
`~/.config/mhsaveconverter/` (override with `$XDG_CONFIG_HOME`). **Nothing about
your machine is hardcoded** — every location comes from your profile.

## Development

```bash
# wrapper tests (no console keys needed)
python -m pytest

# converter submodule tests
cd "MHXXGUSaveConvert/MHGU-MHXX-Save-Converter-Script" && python -m pytest
```

The key-dependent surface is isolated behind `mhpipeline/save3ds.py`, so the
conversion math, backups, marker logic, profile, and verify orchestration all
have real automated coverage without any hardware.

See [SPEC.md](SPEC.md) for the design (and the hardware-verified format notes)
and [PLAN.md](PLAN.md) for the implementation phases.

## Layout

```
mhpipeline/        the wrapper package
  cli.py           menu, Setup Profile, gating
  profile.py       config + deep validation
  keys.py          gm9 key resolution (by suffix)
  extdata.py       MHXX extdata detection
  save3ds.py       save3ds_fuse subprocess wrapper
  convert.py       the two orchestrated flows
  system_backup.py system / system_backup pair writer
  deps.py          [4] bootstrap
tests/             wrapper test suite
save3ds/                 submodule (3DS decrypt/encrypt)
MHXXGUSaveConvert/...     submodule (cleartext converter)
```
