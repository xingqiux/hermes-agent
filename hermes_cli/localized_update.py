"""Localized-fork update flow for Chinese-enhanced Hermes builds.

This module intentionally does not reuse ``hermes update``'s git mutation
path. The standard updater may reset to ``origin/main`` when history diverges;
that is appropriate for stock installs, but unsafe for a fork whose ``main``
contains local localization commits.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).parent.parent.resolve()
LOCALIZED_REMOTE = os.environ.get(
    "HERMES_LOCALIZED_REMOTE",
    "https://github.com/xingqiux/hermes-agent.git",
)
LOCALIZED_REF = os.environ.get("HERMES_LOCALIZED_REF", "main")
BUILD_INFO_PATH = PROJECT_ROOT / "hermes_cli" / "build_info.json"


@dataclass
class UpdateCheck:
    current_branch: str
    local_commit: str | None
    origin_commit: str | None
    upstream_commit: str | None
    behind_upstream: int
    ahead_upstream: int
    dirty: bool
    can_update: bool
    reason: str
    last_checked_at: str


class LocalizedUpdateError(RuntimeError):
    """Raised for expected update blockers with a user-facing message."""


def _is_container_deployment() -> bool:
    try:
        from hermes_constants import is_container

        return is_container()
    except Exception:
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _git_out(args: list[str]) -> str | None:
    result = _git(args)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git_required(args: list[str], message: str) -> subprocess.CompletedProcess[str]:
    result = _git(args)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise LocalizedUpdateError(f"{message}\n{detail}".strip())
    return result


def _format_status_for_log(status: str) -> str:
    result = _git(["status", "--short", "--branch"])
    detail = (result.stdout or result.stderr or "").strip()
    return detail or status


def _remote_exists(name: str) -> bool:
    return _git(["remote", "get-url", name]).returncode == 0


def _remote_commit() -> str | None:
    result = subprocess.run(
        ["git", "ls-remote", LOCALIZED_REMOTE, f"refs/heads/{LOCALIZED_REF}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    first = result.stdout.strip().split()
    return first[0] if first else None


def _read_build_commit() -> str | None:
    if BUILD_INFO_PATH.exists():
        try:
            data = json.loads(BUILD_INFO_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        commit = data.get("commit") or data.get("git_commit")
        if commit and str(commit) != "unknown":
            return str(commit)
    return _git_out(["rev-parse", "HEAD"])


def _is_git_checkout() -> bool:
    result = _git(["rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def _count_range(expr: str) -> int:
    out = _git_out(["rev-list", "--count", expr])
    if out is None:
        return -1
    try:
        return int(out)
    except ValueError:
        return -1


def _is_dirty() -> bool:
    status = _git_out(["status", "--porcelain"])
    return bool(status)


def _check_deployed_image_status(*, fetch: bool) -> UpdateCheck:
    local_commit = _read_build_commit()
    remote_commit = _remote_commit() if fetch else None
    is_current = bool(local_commit and remote_commit and local_commit == remote_commit)
    has_update = bool(local_commit and remote_commit and local_commit != remote_commit)
    if has_update:
        reason = "GitHub fork has a newer commit. Rebuild and redeploy the Docker image."
    elif is_current:
        reason = "Deployed image is up to date with the GitHub fork."
    elif not local_commit:
        reason = "Cannot read build commit from this installation."
    else:
        reason = "Cannot check the GitHub fork right now."

    return UpdateCheck(
        current_branch="container" if _is_container_deployment() else "deployed",
        local_commit=local_commit[:12] if local_commit else None,
        origin_commit=remote_commit[:12] if remote_commit else None,
        upstream_commit=remote_commit[:12] if remote_commit else None,
        behind_upstream=1 if has_update else 0,
        ahead_upstream=0,
        dirty=False,
        can_update=has_update,
        reason=reason,
        last_checked_at=_now_iso(),
    )


def _check_github_fork_status(*, fetch: bool) -> UpdateCheck:
    branch = _git_out(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    local_full = _git_out(["rev-parse", "HEAD"])
    local_commit = _git_out(["rev-parse", "--short", "HEAD"])
    dirty = _is_dirty()
    remote_full: str | None = None
    reason = "Already up to date with the GitHub fork."

    if _remote_exists("origin"):
        if fetch:
            origin_fetch = _git(["fetch", "origin", LOCALIZED_REF])
            if origin_fetch.returncode != 0:
                reason = "Cannot check the GitHub fork right now."
        remote_full = _git_out(["rev-parse", f"origin/{LOCALIZED_REF}"])
        behind = _count_range(f"HEAD..origin/{LOCALIZED_REF}")
        ahead = _count_range(f"origin/{LOCALIZED_REF}..HEAD")
    else:
        remote_full = _remote_commit() if fetch else None
        behind = 1 if local_full and remote_full and local_full != remote_full else 0
        ahead = 0

    has_update = behind > 0
    if has_update:
        reason = "GitHub fork has a newer commit. Build and deploy with make update."
    elif ahead > 0:
        reason = "Local checkout is ahead of the GitHub fork."
    elif not remote_full:
        reason = "Cannot check the GitHub fork right now."

    return UpdateCheck(
        current_branch=branch,
        local_commit=local_commit,
        origin_commit=remote_full[:12] if remote_full else None,
        upstream_commit=remote_full[:12] if remote_full else None,
        behind_upstream=max(behind, 0),
        ahead_upstream=max(ahead, 0),
        dirty=dirty,
        can_update=has_update,
        reason=reason,
        last_checked_at=_now_iso(),
    )


def check_update_status(*, fetch: bool = True) -> UpdateCheck:
    """Return passive update status against the localized GitHub fork.

    This is intentionally check-only. Dashboard no longer mutates the local
    tree or container; Docker deployments are rebuilt and rolled out by the
    Makefile workflow.
    """

    if not _is_git_checkout():
        return _check_deployed_image_status(fetch=fetch)

    return _check_github_fork_status(fetch=fetch)


def _check_merge_update_status(*, fetch: bool = True) -> UpdateCheck:
    """Return source-merge status against official ``upstream/main``."""

    branch = _git_out(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    local_commit = _git_out(["rev-parse", "--short", "HEAD"])
    origin_commit: str | None = None
    upstream_commit: str | None = None
    dirty = _is_dirty()
    can_update = True
    reason = "Ready to update"

    if not _remote_exists("origin"):
        can_update = False
        reason = "Missing origin remote for your localized fork."
    if not _remote_exists("upstream"):
        can_update = False
        reason = "Missing upstream remote for the official Hermes repository."

    if fetch and _remote_exists("upstream"):
        upstream_fetch = _git(["fetch", "upstream", "main"])
        if upstream_fetch.returncode != 0:
            can_update = False
            reason = "Failed to fetch upstream/main."

    if fetch and _remote_exists("origin"):
        origin_fetch = _git(["fetch", "origin", "main"])
        if origin_fetch.returncode != 0 and can_update:
            can_update = False
            reason = "Failed to fetch origin/main."

    origin_commit = _git_out(["rev-parse", "--short", "origin/main"])
    upstream_commit = _git_out(["rev-parse", "--short", "upstream/main"])

    behind_upstream = _count_range("HEAD..upstream/main")
    ahead_upstream = _count_range("upstream/main..HEAD")

    if branch != "main":
        can_update = False
        reason = "Localized update only runs on the main branch."
    elif dirty:
        can_update = False
        reason = _format_status_for_log(
            "Working tree has uncommitted changes. Commit or clean them before updating."
        )
    elif upstream_commit is None and can_update:
        can_update = False
        reason = "Cannot resolve upstream/main."
    elif behind_upstream == 0 and can_update:
        reason = "Already up to date with upstream/main."

    return UpdateCheck(
        current_branch=branch,
        local_commit=local_commit,
        origin_commit=origin_commit,
        upstream_commit=upstream_commit,
        behind_upstream=max(behind_upstream, 0),
        ahead_upstream=max(ahead_upstream, 0),
        dirty=dirty,
        can_update=can_update,
        reason=reason,
        last_checked_at=_now_iso(),
    )


def _run_streamed(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    print(f"→ Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env)
    if result.returncode != 0:
        raise LocalizedUpdateError(f"Command failed with exit {result.returncode}: {' '.join(cmd)}")


def _ensure_clean_main() -> UpdateCheck:
    status = _check_merge_update_status(fetch=True)
    if not status.can_update and status.reason != "Already up to date with upstream/main.":
        raise LocalizedUpdateError(status.reason)
    return status


def _fast_forward_origin_if_needed() -> None:
    behind_origin = _count_range("HEAD..origin/main")
    ahead_origin = _count_range("origin/main..HEAD")
    if behind_origin <= 0:
        return
    if ahead_origin > 0:
        raise LocalizedUpdateError(
            "Local main and origin/main have diverged. Resolve manually before using Dashboard update."
        )
    print(f"→ Fast-forwarding local main from origin/main ({behind_origin} commit(s))...")
    _git_required(["merge", "--ff-only", "origin/main"], "Failed to fast-forward from origin/main.")


def _install_and_build() -> None:
    """Run the dependency/build/config steps shared with normal updates."""
    from hermes_cli import main as hm
    from hermes_cli.config import (
        check_config_version,
        get_missing_config_fields,
        get_missing_env_vars,
        migrate_config,
    )

    removed = hm._clear_bytecode_cache(PROJECT_ROOT)
    if removed:
        print(f"  ✓ Cleared {removed} stale __pycache__ director{'y' if removed == 1 else 'ies'}")

    print("→ Updating Python dependencies...")
    pip_cmd = [sys.executable, "-m", "pip"]
    uv_bin = shutil.which("uv") or hm._ensure_uv_for_termux(pip_cmd)
    install_group = "all"
    if uv_bin:
        uv_env = {**os.environ, "VIRTUAL_ENV": str(PROJECT_ROOT / "venv")}
        if hm._is_termux_env(uv_env):
            uv_env.pop("PYTHONPATH", None)
            uv_env.pop("PYTHONHOME", None)
            install_group = "termux-all"
        hm._install_python_dependencies_with_optional_fallback(
            [uv_bin, "pip"],
            env=uv_env,
            group=install_group,
        )
    else:
        hm._install_python_dependencies_with_optional_fallback(pip_cmd, group=install_group)

    hm._refresh_active_lazy_features()
    hm._update_node_dependencies()
    hm._build_web_ui(PROJECT_ROOT / "web")

    print("→ Checking configuration for new options...")
    current_ver, latest_ver = check_config_version()
    if get_missing_env_vars(required_only=True) or get_missing_config_fields() or current_ver < latest_ver:
        print("  ℹ Applying safe non-interactive config migrations.")
        migrate_config(interactive=False, quiet=False)
    else:
        print("  ✓ Configuration is up to date")


def run_localized_update() -> int:
    """Merge official upstream into the localized fork and push origin/main."""

    print("⚕ Updating localized Hermes fork...")
    print("  Source: upstream/main (official)")
    print("  Target: origin/main (localized fork)")
    print()

    _ensure_clean_main()
    _fast_forward_origin_if_needed()

    behind = _count_range("HEAD..upstream/main")
    if behind <= 0:
        print("✓ Already up to date with upstream/main.")
        return 0

    print(f"→ Merging upstream/main ({behind} new commit(s))...")
    merge = _git(["merge", "--no-edit", "upstream/main"])
    if merge.returncode != 0:
        print(merge.stdout.rstrip())
        print(merge.stderr.rstrip())
        print()
        print("✗ Merge conflict or merge failure.")
        print("  Resolve manually, then run:")
        print("    git status")
        print("    git add <resolved-files>")
        print("    git commit")
        print("    git push origin main")
        return 1
    if merge.stdout.strip():
        print(merge.stdout.rstrip())

    _install_and_build()

    print("→ Pushing localized main to origin...")
    push = _git(["push", "origin", "main"])
    if push.returncode != 0:
        print(push.stdout.rstrip())
        print(push.stderr.rstrip())
        print("✗ Push failed. Local update succeeded; push manually with: git push origin main")
        return 1

    print("✓ Localized update complete and pushed to origin/main.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    cmd = args[0] if args else "check"
    if cmd == "check":
        print(json.dumps(asdict(check_update_status(fetch=True)), ensure_ascii=False))
        return 0
    if cmd == "apply":
        return run_localized_update()
    print("Usage: python -m hermes_cli.localized_update [check|apply]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
