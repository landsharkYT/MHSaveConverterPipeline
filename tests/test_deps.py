import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mhpipeline import deps


class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_check_reports_python_deps_present():
    # art/colorama/sshkeyboard are installed in the dev env.
    report = deps.check()
    names = {i.name: i for i in report.items}
    assert "cargo (Rust toolchain)" in names
    assert "save3ds_fuse built" in names
    for mod in deps.PYTHON_DEPS:
        assert ("python: %s" % mod) in names


def test_install_skips_rust_when_cargo_present(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return FakeCompleted(0)

    monkeypatch.setattr(deps.shutil, "which", lambda name: "/usr/bin/cargo")
    # Pretend the binary appears after the build step.
    monkeypatch.setattr(deps.save3ds, "is_built", lambda override=None: True)

    logs = []
    deps.install(run=fake_run, log=logs.append)

    flat = " ".join(str(a) for a, _ in calls)
    assert "rustup" not in flat.lower()
    # build + pip install happened
    assert any("build" in str(a) for a, _ in calls)
    assert any("pip" in str(a) for a, _ in calls)


def test_install_builds_rust_when_cargo_missing(monkeypatch):
    state = {"cargo": None}

    def fake_which(name):
        return state["cargo"] if name == "cargo" else "/usr/bin/" + name

    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        if args[:1] == ["curl"]:
            return FakeCompleted(0, stdout="#!/bin/sh\n")
        return FakeCompleted(0)

    monkeypatch.setattr(deps.shutil, "which", fake_which)
    monkeypatch.setattr(deps.save3ds, "is_built", lambda override=None: True)
    deps.install(run=fake_run, log=lambda *_: None)

    assert runs[0][:1] == ["curl"]  # downloaded rustup first


def test_install_raises_on_build_failure(monkeypatch):
    def fake_run(args, **kwargs):
        if "build" in args:
            return FakeCompleted(1)
        return FakeCompleted(0)

    monkeypatch.setattr(deps.shutil, "which", lambda name: "/usr/bin/cargo")
    try:
        deps.install(run=fake_run, log=lambda *_: None)
    except deps.DepError:
        return
    assert False, "expected DepError on build failure"
