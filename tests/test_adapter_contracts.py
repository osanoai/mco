from __future__ import annotations

import subprocess
import tempfile
import time
import unittest

from unittest.mock import patch

from runtime.adapters import ClaudeAdapter, CodexAdapter, CursorAdapter, GeminiAdapter, GrokAdapter, OpenCodeAdapter, QwenAdapter
from runtime.adapters.shim import _sanitize_env
from runtime.contracts import NormalizeContext, TaskInput


class AdapterContractTests(unittest.TestCase):
    def _wait_terminal(self, adapter: object, ref: object, timeout_seconds: float = 5.0) -> object:
        start = time.time()
        while time.time() - start < timeout_seconds:
            status = adapter.poll(ref)  # type: ignore[attr-defined]
            if status.completed:
                return status
            time.sleep(0.05)
        self.fail("adapter run did not reach terminal state")

    def test_claude_adapter_run_poll_normalize(self) -> None:
        adapter = ClaudeAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-claude-contract",
                prompt="ignored in contract test",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "command_override": [
                        "python3",
                        "-c",
                        'print(\'{"findings":[{"finding_id":"f1","severity":"high","category":"bug","title":"t","evidence":{"file":"a.py","line":1,"snippet":"x"},"recommendation":"r","confidence":0.9,"fingerprint":"fp1"}]}\')',
                    ],
                },
            )
            ref = adapter.run(task)
            status = self._wait_terminal(adapter, ref)
            self.assertTrue(status.completed)
            self.assertEqual(status.attempt_state, "SUCCEEDED")
            self.assertIsNotNone(status.output_path)

            with open(f"{tmpdir}/{task.task_id}/raw/claude.stdout.log", "r", encoding="utf-8") as fh:
                raw = fh.read()
            findings = adapter.normalize(
                raw,
                NormalizeContext(task_id=task.task_id, provider="claude", repo_root=tmpdir, raw_ref="raw/claude.stdout.log"),
            )
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].provider, "claude")

    def test_codex_adapter_run_poll_with_non_zero_exit(self) -> None:
        adapter = CodexAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-codex-contract",
                prompt="ignored in contract test",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "command_override": [
                        "bash",
                        "-lc",
                        'echo \'{"type":"turn.completed"}\'; echo \'{"findings":[{"finding_id":"f2","severity":"medium","category":"maintainability","title":"m","evidence":{"file":"b.py","line":2,"snippet":"y"},"recommendation":"r2","confidence":0.6,"fingerprint":"fp2"}]}\'; exit 1',
                    ],
                },
            )
            ref = adapter.run(task)
            status = self._wait_terminal(adapter, ref)
            self.assertEqual(status.attempt_state, "SUCCEEDED")
            self.assertIsNone(status.error_kind)

            with open(f"{tmpdir}/{task.task_id}/raw/codex.stdout.log", "r", encoding="utf-8") as fh:
                raw = fh.read()
            findings = adapter.normalize(
                raw,
                NormalizeContext(task_id=task.task_id, provider="codex", repo_root=tmpdir, raw_ref="raw/codex.stdout.log"),
            )
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].provider, "codex")

    def test_codex_adapter_includes_output_schema_when_provided(self) -> None:
        adapter = CodexAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-codex-schema",
                prompt="review",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "output_schema_path": "/tmp/review.schema.json",
                },
            )
            cmd = adapter._build_command(task)  # type: ignore[attr-defined]
            self.assertIn("--output-schema", cmd)
            self.assertIn("/tmp/review.schema.json", cmd)

    def test_cursor_adapter_builds_headless_agent_command(self) -> None:
        adapter = CursorAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-cursor-command",
                prompt="review",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "provider_models": {"cursor": "gpt-5"},
                    "provider_permissions": {
                        "approve_mcps": "true",
                        "force": "true",
                        "mode": "plan",
                        "sandbox": "disabled",
                    },
                },
            )
            cmd = adapter._build_command(task)  # type: ignore[attr-defined]
        self.assertEqual(cmd[0], "cursor-agent")
        self.assertIn("--print", cmd)
        self.assertIn("--trust", cmd)
        self.assertIn("--workspace", cmd)
        self.assertIn(tmpdir, cmd)
        self.assertIn("--approve-mcps", cmd)
        self.assertIn("--force", cmd)
        self.assertEqual(cmd[cmd.index("--mode") + 1], "plan")
        self.assertEqual(cmd[cmd.index("--sandbox") + 1], "disabled")
        self.assertEqual(cmd[cmd.index("--model") + 1], "gpt-5")

    def test_cursor_adapter_can_omit_trust(self) -> None:
        adapter = CursorAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-cursor-no-trust",
                prompt="review",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={"provider_permissions": {"trust": "false"}},
            )
            cmd = adapter._build_command(task)  # type: ignore[attr-defined]
        self.assertNotIn("--trust", cmd)

    def test_adapter_cancel(self) -> None:
        adapter = ClaudeAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-cancel-contract",
                prompt="ignored",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "command_override": ["python3", "-c", "import time; time.sleep(10)"],
                },
            )
            ref = adapter.run(task)
            adapter.cancel(ref)
            status = self._wait_terminal(adapter, ref)
            self.assertTrue(status.completed)
            self.assertIn(status.attempt_state, ("FAILED", "SUCCEEDED", "EXPIRED"))

    def test_run_handle_is_released_after_terminal_poll(self) -> None:
        adapter = ClaudeAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-handle-release",
                prompt="ignored",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "command_override": ["python3", "-c", "print('ok')"],
                },
            )
            ref = adapter.run(task)
            status = self._wait_terminal(adapter, ref)
            self.assertTrue(status.completed)
            self.assertNotIn(ref.run_id, adapter._runs)  # type: ignore[attr-defined]

    def test_cancel_releases_finished_run_handle_without_poll(self) -> None:
        adapter = ClaudeAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-cancel-release-finished",
                prompt="ignored",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "command_override": ["python3", "-c", "print('done')"],
                },
            )
            ref = adapter.run(task)
            time.sleep(0.2)
            adapter.cancel(ref)
            self.assertNotIn(ref.run_id, adapter._runs)  # type: ignore[attr-defined]

    def test_gemini_adapter_run_poll_normalize(self) -> None:
        adapter = GeminiAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-gemini-contract",
                prompt="ignored in contract test",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "command_override": [
                        "python3",
                        "-c",
                        'print(\'{"findings":[{"finding_id":"g1","severity":"low","category":"maintainability","title":"g","evidence":{"file":"g.py","line":3,"snippet":"z"},"recommendation":"rg","confidence":0.7,"fingerprint":"gfp"}]}\')',
                    ],
                },
            )
            ref = adapter.run(task)
            status = self._wait_terminal(adapter, ref)
            self.assertEqual(status.attempt_state, "SUCCEEDED")
            with open(f"{tmpdir}/{task.task_id}/raw/gemini.stdout.log", "r", encoding="utf-8") as fh:
                raw = fh.read()
            findings = adapter.normalize(
                raw,
                NormalizeContext(task_id=task.task_id, provider="gemini", repo_root=tmpdir, raw_ref="raw/gemini.stdout.log"),
            )
            self.assertEqual(len(findings), 1)

    def test_opencode_adapter_run_poll_normalize(self) -> None:
        adapter = OpenCodeAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-opencode-contract",
                prompt="ignored in contract test",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "command_override": [
                        "python3",
                        "-c",
                        'print(\'{"findings":[{"finding_id":"o1","severity":"medium","category":"performance","title":"o","evidence":{"file":"o.py","line":2,"snippet":"q"},"recommendation":"ro","confidence":0.6,"fingerprint":"ofp"}]}\')',
                    ],
                },
            )
            ref = adapter.run(task)
            status = self._wait_terminal(adapter, ref)
            self.assertEqual(status.attempt_state, "SUCCEEDED")
            with open(f"{tmpdir}/{task.task_id}/raw/opencode.stdout.log", "r", encoding="utf-8") as fh:
                raw = fh.read()
            findings = adapter.normalize(
                raw,
                NormalizeContext(task_id=task.task_id, provider="opencode", repo_root=tmpdir, raw_ref="raw/opencode.stdout.log"),
            )
            self.assertEqual(len(findings), 1)

    def test_qwen_adapter_run_poll_normalize(self) -> None:
        adapter = QwenAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-qwen-contract",
                prompt="ignored in contract test",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "command_override": [
                        "python3",
                        "-c",
                        'print(\'{"findings":[{"finding_id":"q1","severity":"high","category":"security","title":"q","evidence":{"file":"q.py","line":4,"snippet":"w"},"recommendation":"rq","confidence":0.9,"fingerprint":"qfp"}]}\')',
                    ],
                },
            )
            ref = adapter.run(task)
            status = self._wait_terminal(adapter, ref)
            self.assertEqual(status.attempt_state, "SUCCEEDED")
            with open(f"{tmpdir}/{task.task_id}/raw/qwen.stdout.log", "r", encoding="utf-8") as fh:
                raw = fh.read()
            findings = adapter.normalize(
                raw,
                NormalizeContext(task_id=task.task_id, provider="qwen", repo_root=tmpdir, raw_ref="raw/qwen.stdout.log"),
            )
            self.assertEqual(len(findings), 1)

    def test_grok_adapter_run_poll_normalize(self) -> None:
        adapter = GrokAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-grok-contract",
                prompt="ignored in contract test",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "command_override": [
                        "python3",
                        "-c",
                        'print(\'{"findings":[{"finding_id":"x1","severity":"medium","category":"bug","title":"x","evidence":{"file":"x.py","line":5,"snippet":"v"},"recommendation":"rx","confidence":0.8,"fingerprint":"xfp"}]}\')',
                    ],
                },
            )
            ref = adapter.run(task)
            status = self._wait_terminal(adapter, ref)
            self.assertEqual(status.attempt_state, "SUCCEEDED")
            with open(f"{tmpdir}/{task.task_id}/raw/grok.stdout.log", "r", encoding="utf-8") as fh:
                raw = fh.read()
            findings = adapter.normalize(
                raw,
                NormalizeContext(task_id=task.task_id, provider="grok", repo_root=tmpdir, raw_ref="raw/grok.stdout.log"),
            )
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].provider, "grok")

    def test_grok_adapter_builds_verified_command_shape(self) -> None:
        adapter = GrokAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-grok-command",
                prompt="review",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={"provider_models": {"grok": "grok-build"}},
            )
            cmd = adapter._build_command(task)  # type: ignore[attr-defined]
        self.assertEqual(cmd[0], "grok")
        self.assertEqual(cmd[cmd.index("--cwd") + 1], tmpdir)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "bypassPermissions")
        self.assertIn("--no-plan", cmd)
        self.assertIn("--no-memory", cmd)
        self.assertIn("--no-subagents", cmd)
        self.assertIn("--disable-web-search", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "grok-build")
        self.assertEqual(cmd[-2:], ["-p", "review"])
        self.assertNotIn("--max-turns", cmd)

    def test_grok_adapter_maps_permissions(self) -> None:
        adapter = GrokAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-grok-permissions",
                prompt="review",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "provider_permissions": {
                        "permission_mode": "plan",
                        "sandbox": "workspace-write",
                        "always_approve": "true",
                        "tools": "edit,shell",
                        "disallowed_tools": "web",
                        "allow": "src/**",
                        "deny": "secrets/**",
                        "no_plan": "false",
                        "no_memory": "false",
                        "no_subagents": "false",
                        "disable_web_search": "false",
                    },
                },
            )
            cmd = adapter._build_command(task)  # type: ignore[attr-defined]
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "plan")
        self.assertEqual(cmd[cmd.index("--sandbox") + 1], "workspace-write")
        self.assertIn("--always-approve", cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "edit,shell")
        self.assertEqual(cmd[cmd.index("--disallowed-tools") + 1], "web")
        self.assertEqual(cmd[cmd.index("--allow") + 1], "src/**")
        self.assertEqual(cmd[cmd.index("--deny") + 1], "secrets/**")
        self.assertNotIn("--no-plan", cmd)
        self.assertNotIn("--no-memory", cmd)
        self.assertNotIn("--no-subagents", cmd)
        self.assertNotIn("--disable-web-search", cmd)

    def test_grok_adapter_auth_probe_command(self) -> None:
        adapter = GrokAdapter()
        self.assertEqual(adapter._auth_check_command("grok"), ["grok", "models"])  # type: ignore[attr-defined]

    def test_grok_command_record_contract(self) -> None:
        adapter = GrokAdapter()
        record = adapter._build_command_for_record()  # type: ignore[attr-defined]
        self.assertEqual(record[0], "grok")
        self.assertIn("--cwd", record)
        self.assertIn("--permission-mode", record)
        self.assertIn("--output-format", record)
        self.assertIn("--verbatim", record)
        self.assertIn("-p", record)

    def test_sanitize_env_strips_claudecode(self) -> None:
        with patch.dict("os.environ", {"CLAUDECODE": "1", "HOME": "/tmp"}):
            env = _sanitize_env()
            self.assertNotIn("CLAUDECODE", env)
            self.assertIn("HOME", env)

    def test_popen_receives_sanitized_env(self) -> None:
        adapter = ClaudeAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            task = TaskInput(
                task_id="task-env-check",
                prompt="ignored",
                repo_root=tmpdir,
                target_paths=["."],
                metadata={
                    "artifact_root": tmpdir,
                    "command_override": ["python3", "-c", "import os, sys; sys.exit(0 if 'CLAUDECODE' not in os.environ else 1)"],
                },
            )
            with patch.dict("os.environ", {"CLAUDECODE": "1"}):
                ref = adapter.run(task)
            status = self._wait_terminal(adapter, ref)
            self.assertTrue(status.completed)
            self.assertEqual(status.attempt_state, "SUCCEEDED")

    def test_detect_uses_which_result_for_binary_path(self) -> None:
        adapter = CodexAdapter()
        with patch("runtime.adapters.shim.shutil.which", return_value="/mock/bin/codex") as mocked_which:
            with patch.object(adapter, "_probe_version", return_value="codex-cli 0.105.0"):
                with patch.object(adapter, "_probe_auth", return_value=(False, "probe_config_error")):
                    presence = adapter.detect()
        mocked_which.assert_called_once()
        self.assertEqual(presence.binary_path, "/mock/bin/codex")
        self.assertFalse(presence.auth_ok)
        self.assertEqual(presence.reason, "probe_config_error")

    def test_probe_version_uses_sanitized_env(self) -> None:
        adapter = CodexAdapter()
        with patch.dict("os.environ", {"CLAUDECODE": "1", "PATH": "/tmp/bin"}):
            with patch("runtime.adapters.shim.subprocess.run") as mocked_run:
                mocked_run.return_value = subprocess.CompletedProcess(
                    args=["codex", "--version"],
                    returncode=0,
                    stdout="codex-cli 0.105.0\n",
                    stderr="",
                )
                version = adapter._probe_version("/mock/bin/codex")  # type: ignore[attr-defined]
        self.assertEqual(version, "codex-cli 0.105.0")
        kwargs = mocked_run.call_args.kwargs
        self.assertIn("env", kwargs)
        self.assertNotIn("CLAUDECODE", kwargs["env"])
        self.assertEqual(kwargs["env"].get("PATH"), "/tmp/bin")

    def test_probe_auth_reason_classification(self) -> None:
        adapter = CodexAdapter()
        with patch("runtime.adapters.shim.subprocess.run") as mocked_run:
            mocked_run.return_value = subprocess.CompletedProcess(
                args=["codex", "login", "status"],
                returncode=1,
                stdout="",
                stderr="Configuration error: unknown key model_reasoning_effort",
            )
            ok, reason = adapter._probe_auth("/mock/bin/codex")  # type: ignore[attr-defined]
            self.assertFalse(ok)
            self.assertEqual(reason, "probe_config_error")

            mocked_run.return_value = subprocess.CompletedProcess(
                args=["codex", "login", "status"],
                returncode=1,
                stdout="",
                stderr="Not logged in. Please run codex login",
            )
            ok, reason = adapter._probe_auth("/mock/bin/codex")  # type: ignore[attr-defined]
            self.assertFalse(ok)
            self.assertEqual(reason, "auth_check_failed")

            mocked_run.return_value = subprocess.CompletedProcess(
                args=["codex", "login", "status"],
                returncode=1,
                stdout="",
                stderr="unexpected runtime failure",
            )
            ok, reason = adapter._probe_auth("/mock/bin/codex")  # type: ignore[attr-defined]
            self.assertFalse(ok)
            self.assertEqual(reason, "probe_unknown_error")


if __name__ == "__main__":
    unittest.main()
