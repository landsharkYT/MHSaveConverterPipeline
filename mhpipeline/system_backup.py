"""Write the ``(system, system_backup)`` pair correctly for each platform.

Verified empirically from real saves (see SPEC.md §1.3):

* **3DS**: ``system`` and ``system_backup`` are byte-for-byte identical.
* **Switch**: identical except a fixed 4-byte role marker at offset ``0x14``
  (a constant tag, not a checksum):

      system        -> 74 ee b2 36
      system_backup -> 92 9b 81 d0

The converter's output already carries the *system* marker (it is copied from
``blank[:40]``), so for Switch we only need to flip those 4 bytes to produce a
valid ``system_backup``.
"""

import os

MARKER_OFFSET = 0x14
SYSTEM_MARKER = b"\x74\xee\xb2\x36"
BACKUP_MARKER = b"\x92\x9b\x81\xd0"
MARKER_END = MARKER_OFFSET + len(SYSTEM_MARKER)  # 0x18

SYSTEM_NAME = "system"
BACKUP_NAME = "system_backup"


def switch_backup_bytes(system_data):
    """Derive Switch ``system_backup`` bytes from ``system`` bytes.

    Identical to ``system`` except the 4-byte role marker at ``0x14``.
    """
    if len(system_data) < MARKER_END:
        raise ValueError(
            "Switch system data too small (%d bytes) for the role marker at 0x14"
            % len(system_data))
    buf = bytearray(system_data)
    buf[MARKER_OFFSET:MARKER_END] = BACKUP_MARKER
    return bytes(buf)


def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def write_pair_3ds(dest_dir, system_data):
    """Write identical ``system`` / ``system_backup`` into ``dest_dir`` (3DS)."""
    os.makedirs(dest_dir, exist_ok=True)
    _write(os.path.join(dest_dir, SYSTEM_NAME), system_data)
    _write(os.path.join(dest_dir, BACKUP_NAME), system_data)


def write_pair_switch(dest_dir, system_data):
    """Write ``system`` (as-is) and ``system_backup`` (role marker swapped)."""
    os.makedirs(dest_dir, exist_ok=True)
    _write(os.path.join(dest_dir, SYSTEM_NAME), system_data)
    _write(os.path.join(dest_dir, BACKUP_NAME), switch_backup_bytes(system_data))
