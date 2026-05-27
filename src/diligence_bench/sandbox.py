from __future__ import annotations

import os
from typing import Any, Literal, cast

DEFAULT_MODAL_APP_NAME = "diligence-bench"
WorkspacePersistence = Literal["tar", "snapshot_filesystem", "snapshot_directory"]
# Keep rollouts isolated by default. Snapshot modes can leak cached files across
# benchmark tasks, which changes the difficulty of later examples.
DEFAULT_WORKSPACE_PERSISTENCE: WorkspacePersistence = "tar"

SANDBOX_IMAGE_BASE = "python:3.14-slim"
SANDBOX_APT_PACKAGES = ("bash", "curl", "jq")
SANDBOX_PIP_PACKAGES = ("requests", "beautifulsoup4", "lxml")


def build_modal_sandbox_client() -> Any:
    from agents.extensions.sandbox import ModalSandboxClient
    from agents.extensions.sandbox.modal.sandbox import ModalImageSelector

    return ModalSandboxClient(image=ModalImageSelector.from_image(_build_sandbox_image()))


def build_modal_sandbox_options(timeout: int = 3600) -> Any:
    from agents.extensions.sandbox import ModalSandboxClientOptions

    return ModalSandboxClientOptions(
        app_name=os.getenv("MODAL_APP_NAME", DEFAULT_MODAL_APP_NAME),
        workspace_persistence=_workspace_persistence(),
        sandbox_create_timeout_s=_optional_float("MODAL_SANDBOX_CREATE_TIMEOUT"),
        timeout=timeout,
    )


def _build_sandbox_image() -> Any:
    import modal

    return (
        modal.Image.from_registry(SANDBOX_IMAGE_BASE)
        .apt_install(*SANDBOX_APT_PACKAGES)
        .pip_install(*SANDBOX_PIP_PACKAGES)
    )


def _optional_float(name: str) -> float | None:
    raw = os.getenv(name)
    if not raw:
        return None
    return float(raw)


def _workspace_persistence() -> WorkspacePersistence:
    value = os.getenv("MODAL_WORKSPACE_PERSISTENCE", DEFAULT_WORKSPACE_PERSISTENCE)
    if value not in {"tar", "snapshot_filesystem", "snapshot_directory"}:
        raise ValueError(
            "MODAL_WORKSPACE_PERSISTENCE must be tar, snapshot_filesystem, or snapshot_directory"
        )
    return cast(WorkspacePersistence, value)
