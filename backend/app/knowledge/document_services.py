from __future__ import annotations

import json
import subprocess
from typing import Any
from uuid import UUID

from core.config import Settings
from core.errors import ApplicationError


class WorkspaceDocumentService:
    """Authorized local document commands; no database or report-export coupling."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def execute(self, owner_id: UUID, action: str, **command: Any) -> dict[str, Any]:
        settings = self.settings
        if owner_id not in settings.workspace_document_read_user_ids:
            raise ApplicationError("workspace_forbidden")
        if action == "save" and owner_id not in settings.workspace_document_write_user_ids:
            raise ApplicationError("workspace_forbidden")
        if action in {"publish", "sync", "restore", "replace"} and (
            owner_id not in settings.workspace_document_write_user_ids
            or owner_id not in settings.workspace_document_publish_user_ids
        ):
            raise ApplicationError("workspace_forbidden")
        tool, source, store = (
            settings.workspace_document_tool_root,
            settings.workspace_document_source_root,
            settings.workspace_document_snapshot_root,
        )
        if (
            not tool
            or not source
            or not store
            or not all(p.is_absolute() for p in (tool, source, store))
        ):
            raise ApplicationError("workspace_unavailable")
        if source.resolve() == tool.resolve().parent:
            # Editing the active application checkout is never a runtime fallback.
            raise ApplicationError("workspace_unavailable")
        data = {
            **command,
            "action": action,
            "owner_id": str(owner_id),
            "source": str(source),
            "store": str(store),
        }
        try:
            result = subprocess.run(
                ["node", str(tool / "scripts/local-cli.mjs")],
                input=json.dumps(data),
                text=True,
                capture_output=True,
                timeout=40,
                cwd=tool,
                check=False,
            )
            payload = json.loads(result.stdout) if result.returncode == 0 else {}
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            raise ApplicationError("workspace_unavailable") from error
        if not isinstance(payload, dict):
            raise ApplicationError("workspace_unavailable")
        if payload.get("error"):
            code = str(payload["error"])
            if code not in {
                "workspace_forbidden",
                "workspace_unavailable",
                "workspace_invalid_input",
                "workspace_version_conflict",
                "workspace_busy",
                "workspace_decision_requires_replacement",
                "resource_not_found",
                "idempotency_conflict",
            }:
                code = "workspace_unavailable"
            raise ApplicationError(code)
        value = payload.get("result")
        if not isinstance(value, dict):
            raise ApplicationError("workspace_unavailable")
        if action == "list":
            value.update(
                can_write=owner_id in settings.workspace_document_write_user_ids,
                can_publish=(
                    owner_id in settings.workspace_document_publish_user_ids
                    and owner_id in settings.workspace_document_write_user_ids
                ),
            )
        return value
