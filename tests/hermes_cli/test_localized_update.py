from __future__ import annotations

import subprocess

import pytest

from hermes_cli import localized_update as lu


def _cp(cmd, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)


class GitSim:
    def __init__(
        self,
        *,
        branch="main",
        dirty="",
        has_origin=True,
        has_upstream=True,
        behind_upstream=1,
        ahead_upstream=0,
        behind_origin=0,
        ahead_origin=0,
        merge_returncode=0,
        push_returncode=0,
    ):
        self.branch = branch
        self.dirty = dirty
        self.has_origin = has_origin
        self.has_upstream = has_upstream
        self.behind_upstream = behind_upstream
        self.ahead_upstream = ahead_upstream
        self.behind_origin = behind_origin
        self.ahead_origin = ahead_origin
        self.merge_returncode = merge_returncode
        self.push_returncode = push_returncode
        self.calls: list[list[str]] = []

    def __call__(self, args, *, check=False):
        self.calls.append(list(args))

        if args[:3] == ["remote", "get-url", "origin"]:
            return _cp(args, 0 if self.has_origin else 2)
        if args[:3] == ["remote", "get-url", "upstream"]:
            return _cp(args, 0 if self.has_upstream else 2)
        if args[:2] == ["rev-parse", "--is-inside-work-tree"]:
            return _cp(args, stdout="true\n")
        if args[:3] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return _cp(args, stdout=f"{self.branch}\n")
        if args[:3] == ["rev-parse", "--short", "HEAD"]:
            return _cp(args, stdout="local123\n")
        if args[:2] == ["rev-parse", "HEAD"]:
            return _cp(args, stdout="local123full\n")
        if args[:2] == ["rev-parse", "origin/main"]:
            return _cp(args, 0 if self.has_origin else 128, stdout="origin123full\n" if self.has_origin else "")
        if args[:3] == ["rev-parse", "--short", "origin/main"]:
            return _cp(args, 0 if self.has_origin else 128, stdout="origin123\n" if self.has_origin else "")
        if args[:3] == ["rev-parse", "--short", "upstream/main"]:
            return _cp(args, 0 if self.has_upstream else 128, stdout="upstream123\n" if self.has_upstream else "")
        if args[:2] == ["status", "--porcelain"]:
            return _cp(args, stdout=self.dirty)
        if args[:3] == ["status", "--short", "--branch"]:
            return _cp(args, stdout=f"## {self.branch}\n{self.dirty}")
        if args[:2] == ["rev-list", "--count"]:
            expr = args[2]
            value = {
                "HEAD..upstream/main": self.behind_upstream,
                "upstream/main..HEAD": self.ahead_upstream,
                "HEAD..origin/main": self.behind_origin,
                "origin/main..HEAD": self.ahead_origin,
            }.get(expr, 0)
            return _cp(args, stdout=f"{value}\n")
        if args[:2] == ["fetch", "upstream"]:
            return _cp(args, 0 if self.has_upstream else 128)
        if args[:2] == ["fetch", "origin"]:
            return _cp(args, 0 if self.has_origin else 128)
        if args[:3] == ["merge", "--ff-only", "origin/main"]:
            self.behind_origin = 0
            return _cp(args, stdout="Fast-forward\n")
        if args[:3] == ["merge", "--no-edit", "upstream/main"]:
            if self.merge_returncode:
                return _cp(args, self.merge_returncode, stdout="Auto-merging file\n", stderr="CONFLICT\n")
            self.behind_upstream = 0
            return _cp(args, stdout="Merge made by ort.\n")
        if args[:3] == ["push", "origin", "main"]:
            return _cp(args, self.push_returncode, stderr="push failed\n" if self.push_returncode else "")
        return _cp(args)


@pytest.fixture
def no_build(monkeypatch):
    monkeypatch.setattr(lu, "_install_and_build", lambda: None)


def test_check_dirty_repo_blocks_update_and_reports_status(monkeypatch):
    sim = GitSim(dirty=" M uv.lock\n?? scratch.txt\n")
    monkeypatch.setattr(lu, "_git", sim)

    status = lu._check_merge_update_status(fetch=True)

    assert status.can_update is False
    assert status.dirty is True
    assert "uv.lock" in status.reason
    assert "scratch.txt" in status.reason


def test_check_missing_upstream_blocks_update(monkeypatch):
    sim = GitSim(has_upstream=False)
    monkeypatch.setattr(lu, "_git", sim)

    status = lu._check_merge_update_status(fetch=True)

    assert status.can_update is False
    assert "Missing upstream remote" in status.reason


def test_dashboard_check_uses_origin_without_mutating(monkeypatch):
    sim = GitSim(behind_origin=2, behind_upstream=9)
    monkeypatch.setattr(lu, "_git", sim)

    status = lu.check_update_status(fetch=True)

    assert status.can_update is True
    assert status.behind_upstream == 2
    assert status.upstream_commit == "origin123ful"
    commands = [" ".join(call) for call in sim.calls]
    assert "merge --no-edit upstream/main" not in commands
    assert "push origin main" not in commands


def test_check_container_deployment_reports_new_remote_commit(monkeypatch):
    monkeypatch.setattr(lu, "_git", lambda args, *, check=False: _cp(args, 128))
    monkeypatch.setattr(lu, "_is_container_deployment", lambda: True)
    monkeypatch.setattr(lu, "_read_build_commit", lambda: "aaa111")
    monkeypatch.setattr(lu, "_remote_commit", lambda: "bbb222")

    status = lu.check_update_status(fetch=True)

    assert status.current_branch == "container"
    assert status.can_update is True
    assert status.behind_upstream == 1
    assert status.local_commit == "aaa111"
    assert status.upstream_commit == "bbb222"
    assert "Rebuild" in status.reason


def test_check_non_git_install_reports_current_remote_commit(monkeypatch):
    monkeypatch.setattr(lu, "_git", lambda args, *, check=False: _cp(args, 128))
    monkeypatch.setattr(lu, "_is_container_deployment", lambda: False)
    monkeypatch.setattr(lu, "_read_build_commit", lambda: "same123")
    monkeypatch.setattr(lu, "_remote_commit", lambda: "same123")

    status = lu.check_update_status(fetch=True)

    assert status.current_branch == "deployed"
    assert status.can_update is False
    assert status.behind_upstream == 0
    assert "up to date" in status.reason


def test_localized_update_never_calls_reset_hard(monkeypatch, no_build):
    sim = GitSim(behind_upstream=2)
    monkeypatch.setattr(lu, "_git", sim)

    assert lu.run_localized_update() == 0

    joined = [" ".join(call) for call in sim.calls]
    assert not any("reset --hard" in call for call in joined)
    assert "merge --no-edit upstream/main" in joined
    assert "push origin main" in joined


def test_localized_update_fast_forwards_origin_before_upstream_merge(monkeypatch, no_build):
    sim = GitSim(behind_origin=2, behind_upstream=3)
    monkeypatch.setattr(lu, "_git", sim)

    assert lu.run_localized_update() == 0

    commands = [" ".join(call) for call in sim.calls]
    ff_index = commands.index("merge --ff-only origin/main")
    merge_index = commands.index("merge --no-edit upstream/main")
    assert ff_index < merge_index


def test_merge_conflict_exits_nonzero_and_does_not_push(monkeypatch, no_build, capsys):
    sim = GitSim(behind_upstream=1, merge_returncode=1)
    monkeypatch.setattr(lu, "_git", sim)

    assert lu.run_localized_update() == 1

    commands = [" ".join(call) for call in sim.calls]
    assert "push origin main" not in commands
    out = capsys.readouterr().out
    assert "Merge conflict" in out
    assert "git status" in out


def test_push_failure_exits_nonzero_after_successful_merge(monkeypatch, no_build, capsys):
    sim = GitSim(behind_upstream=1, push_returncode=1)
    monkeypatch.setattr(lu, "_git", sim)

    assert lu.run_localized_update() == 1

    out = capsys.readouterr().out
    assert "Push failed" in out
    assert "git push origin main" in out


def test_localized_update_rejects_dirty_before_merge(monkeypatch, no_build):
    sim = GitSim(dirty=" M uv.lock\n")
    monkeypatch.setattr(lu, "_git", sim)

    with pytest.raises(lu.LocalizedUpdateError):
        lu._ensure_clean_main()

    commands = [" ".join(call) for call in sim.calls]
    assert "merge --no-edit upstream/main" not in commands
    assert "push origin main" not in commands
