from __future__ import annotations

from typing import Any, List

from ..contracts import CapabilitySet, NormalizeContext, NormalizedFinding, TaskInput
from .parsing import normalize_findings_from_text
from .shim import ShimAdapterBase


class CursorAdapter(ShimAdapterBase):
    def __init__(self) -> None:
        super().__init__(
            provider_id="cursor",
            binary_name="agent",
            capability_set=CapabilitySet(
                tiers=["C0", "C1", "C2", "C3", "C4"],
                supports_native_async=False,
                supports_poll_endpoint=False,
                supports_resume_after_restart=True,
                supports_schema_enforcement=False,
                min_supported_version="0.0.0",
                tested_os=["macos", "linux"],
            ),
        )

    def _auth_check_command(self, binary: str) -> List[str]:
        return [binary, "status", "--format", "json"]

    def supported_permission_keys(self) -> List[str]:
        return ["approve_mcps", "force", "mode", "sandbox", "trust"]

    @staticmethod
    def _truthy(value: object) -> bool:
        return isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "on", "force", "yolo"}

    @staticmethod
    def _falsey(value: object) -> bool:
        return isinstance(value, str) and value.strip().lower() in {"0", "false", "no", "off"}

    def _build_command(self, input_task: TaskInput) -> List[str]:
        raw_permissions = input_task.metadata.get("provider_permissions")
        permissions = raw_permissions if isinstance(raw_permissions, dict) else {}

        cmd = ["agent", "--print", "--output-format", "text"]

        mode = permissions.get("mode")
        if isinstance(mode, str) and mode.strip():
            cmd.extend(["--mode", mode.strip()])

        sandbox = permissions.get("sandbox")
        if isinstance(sandbox, str) and sandbox.strip():
            cmd.extend(["--sandbox", sandbox.strip()])

        if self._truthy(permissions.get("force")):
            cmd.append("--force")
        if self._truthy(permissions.get("approve_mcps")):
            cmd.append("--approve-mcps")

        # Cursor only accepts --trust in print/headless mode. Defaulting to
        # trust keeps MCO non-interactive; callers can set trust=false to omit it.
        if not self._falsey(permissions.get("trust")):
            cmd.append("--trust")

        provider_models = input_task.metadata.get("provider_models") or {}
        model = provider_models.get("cursor")
        if model:
            cmd.extend(["--model", model])

        cmd.extend(["--workspace", input_task.repo_root, input_task.prompt])
        return cmd

    def _build_command_for_record(self) -> List[str]:
        return [
            "agent",
            "--print",
            "--output-format",
            "text",
            "--mode",
            "<mode>",
            "--sandbox",
            "<enabled|disabled>",
            "--force",
            "--approve-mcps",
            "--trust",
            "--model",
            "<model>",
            "--workspace",
            "<repo_root>",
            "<prompt>",
        ]

    def _is_success(self, return_code: int, stdout_text: str, stderr_text: str) -> bool:
        if return_code != 0:
            return False
        text = f"{stdout_text}\n{stderr_text}".lower()
        if "error:" in text and "api key" in text:
            return False
        if "not authenticated" in text or "not logged in" in text:
            return False
        return True

    def normalize(self, raw: Any, ctx: NormalizeContext) -> List[NormalizedFinding]:
        text = raw if isinstance(raw, str) else ""
        return normalize_findings_from_text(text, ctx, "cursor")
