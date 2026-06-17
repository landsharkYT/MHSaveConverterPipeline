"""Dependency detection and bootstrap for menu option [4] Install Dependencies.

``check()`` reports readiness (cargo, the built save3ds_fuse binary, the Python
packages). ``install()`` performs the bootstrap: install Rust via rustup if
missing, build save3ds_fuse (no-FUSE, release, hardware AES), and pip-install
the Python deps into the running interpreter.

Subprocess execution is injected so it can be exercised without touching the
real system.
"""

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from typing import List

from mhpipeline import save3ds


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SAVE3DS_FUSE_DIR = os.path.join(_repo_root(), "save3ds", "save3ds", "save3ds_fuse")
REQUIREMENTS = os.path.join(_repo_root(), "requirements.txt")
SUBMODULES_LOCK = os.path.join(_repo_root(), "submodules.lock")
PARENT_REPO_URL = "https://github.com/landsharkYT/MHSaveConverterPipeline"
PYTHON_DEPS = ("art", "colorama", "sshkeyboard")

RUSTUP_URL = "https://sh.rustup.rs"
AES_RUSTFLAGS = "-C target-feature=+aes"


class DepError(Exception):
    """A bootstrap step failed."""


# --------------------------------------------------------------------------- #
# source submodules (fetched WITHOUT git, so ZIP downloads work)
# --------------------------------------------------------------------------- #
def read_submodule_lock(path=SUBMODULES_LOCK):
    """Return [(rel_path, url, commit), ...] from submodules.lock."""
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) == 3:
                entries.append((parts[0], parts[1], parts[2]))
    return entries


def _submodule_present(rel_path):
    full = os.path.join(_repo_root(), rel_path)
    return os.path.isdir(full) and any(os.scandir(full))


def sources_present():
    try:
        entries = read_submodule_lock()
    except OSError:
        return False
    return all(_submodule_present(p) for p, _, _ in entries)


def _archive_url(url, commit):
    base = url[:-4] if url.endswith(".git") else url
    return "%s/archive/%s.zip" % (base, commit)


def _open_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": "mhpipeline"})
    return urllib.request.urlopen(request)


def _fetch_one(rel_path, url, commit, log, opener):
    full = os.path.join(_repo_root(), rel_path)
    log("Downloading %s @ %s ..." % (rel_path, commit[:10]))
    with opener(_archive_url(url, commit)) as resp:
        data = resp.read()
    tmp = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(tmp)
        roots = [os.path.join(tmp, n) for n in os.listdir(tmp)
                 if os.path.isdir(os.path.join(tmp, n))]
        if len(roots) != 1:
            raise DepError("unexpected archive layout for %s" % rel_path)
        os.makedirs(full, exist_ok=True)
        for name in os.listdir(roots[0]):
            src = os.path.join(roots[0], name)
            dst = os.path.join(full, name)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            elif os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def fetch_sources(log=print, opener=_open_url, force=False):
    """Populate missing source submodules from submodules.lock (no git needed)."""
    for rel_path, url, commit in read_submodule_lock():
        if force or not _submodule_present(rel_path):
            _fetch_one(rel_path, url, commit, log, opener)
        else:
            log("%s already present." % rel_path)


@dataclass
class DepStatus:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class DepReport:
    items: List[DepStatus] = field(default_factory=list)

    @property
    def ok(self):
        return all(i.ok for i in self.items)

    @property
    def missing(self):
        return [i for i in self.items if not i.ok]


def check():
    """Report whether every dependency the converters need is present."""
    report = DepReport()
    report.items.append(DepStatus("source submodules", sources_present(),
                                  "present" if sources_present() else
                                  "missing (will be fetched by Install Dependencies)"))
    cargo = shutil.which("cargo")
    report.items.append(DepStatus("cargo (Rust toolchain)", cargo is not None,
                                  cargo or "not found"))
    report.items.append(DepStatus("save3ds_fuse built", save3ds.is_built(),
                                  save3ds.binary_path()))
    for mod in PYTHON_DEPS:
        present = importlib.util.find_spec(mod) is not None
        report.items.append(DepStatus("python: %s" % mod, present,
                                      "importable" if present else "missing"))
    return report


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #
def install(run=subprocess.run, log=print):
    """Install Rust (if needed), build save3ds_fuse, and pip-install Python deps.

    Returns a fresh :func:`check` report. ``run`` is injectable for testing.
    """
    if not sources_present():
        log("Source submodules missing (e.g. ZIP download) — fetching ...")
        try:
            fetch_sources(log=log)
        except (OSError, DepError, zipfile.BadZipFile) as error:
            raise DepError(
                "Could not fetch the source submodules automatically (%s). "
                "Install Git and run:\n  git clone --recurse-submodules %s"
                % (error, PARENT_REPO_URL))

    if shutil.which("cargo") is None:
        _install_rust(run, log)
    else:
        log("cargo already present; skipping Rust install.")

    _build_save3ds(run, log)
    _install_python_deps(run, log)
    return check()


def _install_rust(run, log):
    if os.name == "nt":
        raise DepError(
            "Automatic Rust install isn't supported on Windows. Install Rust "
            "from https://rustup.rs (run rustup-init.exe), then re-run Install "
            "Dependencies — the rest of the bootstrap works on Windows.")
    log("Installing Rust via rustup (%s) ..." % RUSTUP_URL)
    # Download the installer and run it non-interactively.
    script = run(["curl", "--proto", "=https", "--tlsv1.2", "-sSf", RUSTUP_URL],
                 capture_output=True, text=True)
    if script.returncode != 0:
        raise DepError("failed to download rustup: %s" % (script.stderr or "").strip())
    completed = run(["sh", "-s", "--", "-y"], input=script.stdout, text=True)
    if completed.returncode != 0:
        raise DepError("rustup installation failed")
    log("Rust installed. You may need to restart your shell / source "
        "~/.cargo/env so 'cargo' is on PATH.")


def _build_save3ds(run, log):
    if not os.path.isfile(os.path.join(SAVE3DS_FUSE_DIR, "Cargo.toml")):
        raise DepError(
            "save3ds source is missing at %s — the submodule wasn't fetched. "
            "Re-run Install Dependencies (it fetches sources), or clone with "
            "git clone --recurse-submodules %s" % (SAVE3DS_FUSE_DIR, PARENT_REPO_URL))
    cargo = shutil.which("cargo") or os.path.expanduser("~/.cargo/bin/cargo")
    log("Building save3ds_fuse (release, no-FUSE, hardware AES) ...")
    env = dict(os.environ)
    env["RUSTFLAGS"] = AES_RUSTFLAGS
    completed = run([cargo, "build", "--release", "--no-default-features"],
                    cwd=SAVE3DS_FUSE_DIR, env=env)
    if completed.returncode != 0:
        raise DepError("save3ds_fuse build failed")
    if not save3ds.is_built():
        raise DepError("build reported success but binary not found at %s"
                       % save3ds.binary_path())
    log("Built save3ds_fuse -> %s" % save3ds.binary_path())


def _install_python_deps(run, log):
    log("Installing Python dependencies into %s ..." % sys.executable)
    args = [sys.executable, "-m", "pip", "install"]
    if os.path.isfile(REQUIREMENTS):
        args += ["-r", REQUIREMENTS]
    else:
        args += list(PYTHON_DEPS)
    completed = run(args)
    if completed.returncode != 0:
        raise DepError("pip install failed")
    log("Python dependencies installed.")
