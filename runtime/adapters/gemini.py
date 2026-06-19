from __future__ import annotations

from typing import Any, List

from ..contracts import CapabilitySet, NormalizeContext, NormalizedFinding, TaskInput
from ..provider_identity import canonical_provider_map
from .parsing import normalize_findings_from_text
from .shim import ShimAdapterBase


class AntigravityAdapter(ShimAdapterBase):
    def __init__(self) -> None:
        super().__init__(
            provider_id="antigravity",
            binary_name="agy",
            capability_set=CapabilitySet(
                tiers=["C0", "C1", "C2", "C3"],
                supports_native_async=False,
                supports_poll_endpoint=False,
                supports_resume_after_restart=False,
                supports_schema_enforcement=False,
                min_supported_version="0.1",
                tested_os=["macos"],
            ),
        )

    def _auth_check_command(self, binary: str) -> List[str]:
        return [binary, "--print-timeout", "30s", "-p", "Reply with exactly OK"]

    def _build_command(self, input_task: TaskInput) -> List[str]:
        timeout_seconds = int(input_task.timeout_seconds or 0)
        timeout_arg = f"{timeout_seconds if timeout_seconds > 0 else 600}s"
        cmd = ["agy", "--print-timeout", timeout_arg]
        provider_models = canonical_provider_map(input_task.metadata.get("provider_models") or {})
        model = provider_models.get("antigravity")
        if model:
            cmd.extend(["--model", model])
        cmd.extend(["--dangerously-skip-permissions", "-p", input_task.prompt])
        return cmd

    def _build_command_for_record(self) -> List[str]:
        return [
            "agy",
            "--print-timeout",
            "<timeout>s",
            "--model",
            "<model>",
            "--dangerously-skip-permissions",
            "-p",
            "<prompt>",
        ]

    def _is_success(self, return_code: int, stdout_text: str, stderr_text: str) -> bool:
        if return_code != 0:
            return False
        text = f"{stdout_text}\n{stderr_text}".lower()
        if "unknown arguments" in text:
            return False
        if "api error" in text:
            return False
        return True

    def normalize(self, raw: Any, ctx: NormalizeContext) -> List[NormalizedFinding]:
        text = raw if isinstance(raw, str) else ""
        return normalize_findings_from_text(text, ctx, "antigravity")


class GeminiAdapter(AntigravityAdapter):
    """Legacy import alias for Antigravity."""

    pass
