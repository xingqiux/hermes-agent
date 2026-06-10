"""Regression guards for the xkqq private Docker deployment workflow."""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
MAKEFILE = REPO_ROOT / "Makefile"
COMPOSE = REPO_ROOT / "docker-compose.xkqq.yml"
RECONCILE_SCRIPT = REPO_ROOT / "docker" / "cont-init.d" / "02-reconcile-profiles"


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return DOCKERFILE.read_text()


@pytest.fixture(scope="module")
def makefile_text() -> str:
    return MAKEFILE.read_text()


@pytest.fixture(scope="module")
def compose_text() -> str:
    return COMPOSE.read_text()


@pytest.fixture(scope="module")
def reconcile_script_text() -> str:
    return RECONCILE_SCRIPT.read_text()


def test_private_build_can_bake_runtime_uid_gid(dockerfile_text: str, makefile_text: str) -> None:
    assert "ARG HERMES_RUNTIME_UID=10000" in dockerfile_text
    assert "ARG HERMES_RUNTIME_GID=10000" in dockerfile_text
    assert "--build-arg HERMES_RUNTIME_UID=$(REMOTE_UID)" in makefile_text
    assert "--build-arg HERMES_RUNTIME_GID=$(REMOTE_GID)" in makefile_text


def test_dashboard_container_skips_profile_reconcile(
    compose_text: str,
    reconcile_script_text: str,
) -> None:
    assert "HERMES_SKIP_PROFILE_RECONCILE=1" in compose_text
    assert "HERMES_SKIP_PROFILE_RECONCILE" in reconcile_script_text
    assert "Skipping profile gateway reconciliation" in reconcile_script_text


def test_private_registry_pushes_latest_by_default(makefile_text: str) -> None:
    push_target = makefile_text.split("\npush:\n", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
    assert "docker push $(IMAGE):latest" in push_target
    assert "docker push $(IMAGE):$(TAG)" not in push_target
