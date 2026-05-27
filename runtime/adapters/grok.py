from __future__ import annotations

from typing import Any, List

from ..contracts import CapabilitySet, NormalizeContext, NormalizedFinding, TaskInput
from .parsing import normalize_findings_from_text
from .shim import ShimAdapterBase


class GrokAdapter(ShimAdapterBase):
    _DEFAULT_TOGGLE_FLAGS = {
        "no_plan": "--no-plan",
        "no_memory": "--no-memory",
        "no_subagents": "--no-subagents",
        "disable_web_search": "--disable-web-search",
    }

    def __init__(self) -> None:
        super().__init__(
            provider_id="grok",
            binary_name="grok",
            capability_set=CapabilitySet(
                tiers=["C0", "C1", "C2", "C3"],
                supports_native_async=False,
                supports_poll_endpoint=False,
                supports_resume_after_restart=False,
                supports_schema_enforcement=False,
                min_supported_version="0.2.3",
                tested_os=["linux", "macos"],
            ),
        )

    def _auth_check_command(self, binary: str) -> List[str]:
        return [binary, "models"]

    def supported_permission_keys(self) -> List[str]:
        return [
            "permission_mode",
            "sandbox",
            "always_approve",
            "tools",
            "disallowed_tools",
            "allow",
            "deny",
            "no_plan",
            "no_memory",
            "no_subagents",
            "disable_web_search",
        ]

    @staticmethod
    def _truthy(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "on", "y"}

    @staticmethod
    def _falsey(value: object) -> bool:
        if isinstance(value, bool):
            return not value
        return isinstance(value, str) and value.strip().lower() in {"0", "false", "no", "off", "n"}

    @staticmethod
    def _string_value(value: object) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _build_command(self, input_task: TaskInput) -> List[str]:
        raw_permissions = input_task.metadata.get("provider_permissions")
        permissions = raw_permissions if isinstance(raw_permissions, dict) else {}

        permission_mode = self._string_value(permissions.get("permission_mode")) or "bypassPermissions"
        cmd = [
            "grok",
            "--cwd",
            input_task.repo_root,
            "--permission-mode",
            permission_mode,
        ]

        sandbox = self._string_value(permissions.get("sandbox"))
        if sandbox:
            cmd.extend(["--sandbox", sandbox])
        if self._truthy(permissions.get("always_approve")):
            cmd.append("--always-approve")
        for key, flag in (
            ("tools", "--tools"),
            ("disallowed_tools", "--disallowed-tools"),
            ("allow", "--allow"),
            ("deny", "--deny"),
        ):
            value = self._string_value(permissions.get(key))
            if value:
                cmd.extend([flag, value])

        for key, flag in self._DEFAULT_TOGGLE_FLAGS.items():
            if not self._falsey(permissions.get(key)):
                cmd.append(flag)

        provider_models = input_task.metadata.get("provider_models") or {}
        model = provider_models.get("grok")
        if model:
            cmd.extend(["--model", model])

        cmd.extend(["--output-format", "plain", "--verbatim", "-p", input_task.prompt])
        return cmd

    def _build_command_for_record(self) -> List[str]:
        return [
            "grok",
            "--cwd",
            "<repo_root>",
            "--permission-mode",
            "bypassPermissions",
            "--sandbox",
            "<sandbox>",
            "--always-approve",
            "--tools",
            "<tools>",
            "--disallowed-tools",
            "<disallowed-tools>",
            "--allow",
            "<allow>",
            "--deny",
            "<deny>",
            "--no-plan",
            "--no-memory",
            "--no-subagents",
            "--disable-web-search",
            "--model",
            "<model>",
            "--output-format",
            "plain",
            "--verbatim",
            "-p",
            "<prompt>",
        ]

    def normalize(self, raw: Any, ctx: NormalizeContext) -> List[NormalizedFinding]:
        text = raw if isinstance(raw, str) else ""
        return normalize_findings_from_text(text, ctx, "grok")
