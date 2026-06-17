import io
import os
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mhpipeline import deps


def test_archive_url_strips_dot_git():
    assert deps._archive_url("https://github.com/o/r.git", "abc123") == \
        "https://github.com/o/r/archive/abc123.zip"
    assert deps._archive_url("https://github.com/o/r", "abc123") == \
        "https://github.com/o/r/archive/abc123.zip"


def test_read_submodule_lock_real():
    entries = deps.read_submodule_lock()
    paths = {p for p, _, _ in entries}
    assert "save3ds/save3ds" in paths
    assert "MHXXGUSaveConvert/MHGU-MHXX-Save-Converter-Script" in paths
    for _p, url, commit in entries:
        assert url.startswith("https://github.com/")
        assert len(commit) == 40  # full SHA


def _zip_with_root(rootname, files):
    """Build an in-memory zip that extracts to a single <rootname>/ dir."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for rel, content in files.items():
            zf.writestr("%s/%s" % (rootname, rel), content)
    buf.seek(0)
    return buf.getvalue()


def test_fetch_one_extracts_into_path(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "_repo_root", lambda: str(tmp_path))
    payload = _zip_with_root("repo-deadbeef",
                             {"Cargo.toml": "[package]", "src/main.rs": "fn main(){}"})

    class FakeResp:
        def __init__(self, data): self._d = data
        def read(self): return self._d
        def __enter__(self): return self
        def __exit__(self, *a): return False

    captured = {}

    def fake_opener(url):
        captured["url"] = url
        return FakeResp(payload)

    deps._fetch_one("save3ds/save3ds", "https://github.com/o/save3ds.git",
                    "deadbeef" * 5, log=lambda *_: None, opener=fake_opener)

    base = tmp_path / "save3ds" / "save3ds"
    assert (base / "Cargo.toml").read_text() == "[package]"
    assert (base / "src" / "main.rs").read_text() == "fn main(){}"
    assert captured["url"].endswith("/archive/%s.zip" % ("deadbeef" * 5))


def test_sources_present_false_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "_repo_root", lambda: str(tmp_path))
    # lock points at paths that don't exist yet
    lock = tmp_path / "submodules.lock"
    lock.write_text("a/b https://github.com/o/r.git " + "0" * 40 + "\n")
    monkeypatch.setattr(deps, "SUBMODULES_LOCK", str(lock))
    assert deps.sources_present() is False


def test_install_fetches_when_sources_missing(monkeypatch):
    monkeypatch.setattr(deps, "sources_present", lambda: False)
    fetched = {"called": False}
    monkeypatch.setattr(deps, "fetch_sources",
                        lambda log=None: fetched.__setitem__("called", True))
    monkeypatch.setattr(deps.shutil, "which", lambda name: "/usr/bin/cargo")
    monkeypatch.setattr(deps.save3ds, "is_built", lambda override=None: True)

    class C:
        returncode = 0

    deps.install(run=lambda *a, **k: C(), log=lambda *_: None)
    assert fetched["called"] is True


def test_install_raises_clear_error_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(deps, "sources_present", lambda: False)

    def boom(log=None):
        raise OSError("no network")

    monkeypatch.setattr(deps, "fetch_sources", boom)
    with pytest.raises(deps.DepError) as ei:
        deps.install(run=lambda *a, **k: None, log=lambda *_: None)
    assert "recurse-submodules" in str(ei.value)


@pytest.mark.skipif(not os.path.exists(os.path.join(ROOT, ".git")),
                    reason="not a git checkout")
def test_lock_matches_git_submodule_state():
    """submodules.lock must stay in sync with the actual submodule pins."""
    import subprocess
    out = subprocess.run(["git", "submodule", "status"], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("git submodule status unavailable")
    # map path -> commit from git
    git_pins = {}
    for line in out.stdout.splitlines():
        parts = line.strip().lstrip("+-U").split()
        if len(parts) >= 2:
            git_pins[parts[1]] = parts[0]
    for path, _url, commit in deps.read_submodule_lock():
        assert git_pins.get(path) == commit, "submodules.lock out of sync for %s" % path
