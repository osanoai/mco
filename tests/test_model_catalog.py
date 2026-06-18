"""Tests for model catalog: caching, resolution, CLI parsing, and adapter integration."""
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from runtime.model_catalog import (
    catalog_path,
    download_catalog,
    ensure_catalog,
    load_catalog,
    list_models_for_provider,
    list_providers,
    parse_provider_models,
    resolve_model,
    _is_stale,
)
from runtime.contracts import TaskInput
from runtime.adapters.claude import ClaudeAdapter
from runtime.adapters.codex import CodexAdapter
from runtime.adapters.cursor import CursorAdapter
from runtime.adapters.gemini import GeminiAdapter
from runtime.adapters.grok import GrokAdapter
from runtime.adapters.opencode import OpenCodeAdapter
from runtime.adapters.qwen import QwenAdapter


_SAMPLE_CATALOG = {
    "generatedAt": "2026-04-01T00:00:00Z",
    "catalogs": {
        "claude": {
            "cli": "claude",
            "tiers": [
                {"tier": "fast", "models": ["claude-haiku-4-5"]},
                {"tier": "balanced", "models": ["claude-sonnet-4-5", "claude-sonnet-4-6"]},
                {"tier": "powerful", "models": ["claude-opus-4-6"]},
            ],
        },
        "codex": {
            "cli": "codex",
            "tiers": [
                {"tier": "fast", "models": ["gpt-5.1-codex-mini"]},
                {"tier": "balanced", "models": ["gpt-5.2-codex"]},
                {"tier": "powerful", "models": ["gpt-5.4"]},
            ],
        },
        "grok": {
            "cli": "grok",
            "tiers": [
                {"tier": "fast", "models": ["grok-build"]},
                {"tier": "balanced", "models": ["grok-build"]},
                {"tier": "powerful", "models": ["grok-build"]},
            ],
        },
    },
}


class TestParseProviderModels:
    def test_basic(self):
        assert parse_provider_models("claude=opus,codex=o3") == {"claude": "opus", "codex": "o3"}

    def test_tier_names(self):
        assert parse_provider_models("claude=balanced") == {"claude": "balanced"}

    def test_exact_model(self):
        assert parse_provider_models("claude=claude-opus-4-6") == {"claude": "claude-opus-4-6"}

    def test_empty(self):
        assert parse_provider_models("") == {}

    def test_whitespace(self):
        assert parse_provider_models("  claude = opus , codex = o3  ") == {"claude": "opus", "codex": "o3"}

    def test_invalid_no_equals(self):
        try:
            parse_provider_models("invalid")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "provider-models" in str(e)

    def test_invalid_empty_model(self):
        try:
            parse_provider_models("claude=")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "empty model value" in str(e)


class TestResolveModel:
    def test_tier_to_model(self):
        assert resolve_model("claude", "fast", catalog=_SAMPLE_CATALOG) == "claude-haiku-4-5"
        assert resolve_model("claude", "balanced", catalog=_SAMPLE_CATALOG) == "claude-sonnet-4-6"  # newest first
        assert resolve_model("claude", "powerful", catalog=_SAMPLE_CATALOG) == "claude-opus-4-6"

    def test_tier_case_insensitive(self):
        assert resolve_model("claude", "POWERFUL", catalog=_SAMPLE_CATALOG) == "claude-opus-4-6"
        assert resolve_model("claude", "Balanced", catalog=_SAMPLE_CATALOG) == "claude-sonnet-4-6"  # newest first

    def test_exact_model_passthrough(self):
        assert resolve_model("claude", "claude-opus-4-6", catalog=_SAMPLE_CATALOG) == "claude-opus-4-6"

    def test_unknown_provider_passthrough(self):
        # Providers not in catalog (like opencode) should pass through the value
        assert resolve_model("opencode", "balanced", catalog=_SAMPLE_CATALOG) == "balanced"
        assert resolve_model("opencode", "some-model-id", catalog=_SAMPLE_CATALOG) == "some-model-id"

    def test_unknown_tier_passthrough(self):
        # If the tier doesn't exist, pass through (might be a new model)
        assert resolve_model("claude", "new-model-xyz", catalog=_SAMPLE_CATALOG) == "new-model-xyz"


class TestListModels:
    def test_list_providers(self):
        assert list_providers(catalog=_SAMPLE_CATALOG) == ["claude", "codex", "grok"]

    def test_list_models_for_provider(self):
        tiers = list_models_for_provider("claude", catalog=_SAMPLE_CATALOG)
        assert len(tiers) == 3
        assert tiers[0] == {"tier": "fast", "models": ["claude-haiku-4-5"]}

    def test_list_models_unknown_provider(self):
        assert list_models_for_provider("nonexistent", catalog=_SAMPLE_CATALOG) == []


class TestCaching:
    def test_catalog_path(self):
        path = catalog_path("/tmp/test-mco")
        assert path == Path("/tmp/test-mco/modelCatalog.generated.json")

    def test_is_stale_no_file(self):
        assert _is_stale(Path("/tmp/nonexistent-mco-catalog-test")) is True

    def test_is_stale_fresh_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b"{}")
            path = Path(f.name)
        try:
            assert _is_stale(path) is False
            assert _is_stale(path, max_age_seconds=0) is True
        finally:
            path.unlink()

    def test_is_stale_old_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b"{}")
            path = Path(f.name)
        try:
            # Set mtime to 25h ago
            old_time = time.time() - 90000
            os.utime(path, (old_time, old_time))
            assert _is_stale(path) is True
        finally:
            path.unlink()

    def test_ensure_catalog_uses_cached(self):
        """ensure_catalog should return existing file if fresh."""
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_file = Path(tmpdir) / "modelCatalog.generated.json"
            catalog_file.write_text(json.dumps(_SAMPLE_CATALOG), encoding="utf-8")
            # ensure_catalog should just return the existing file
            result = ensure_catalog(global_config_dir=tmpdir)
            assert result == catalog_file

    def test_load_catalog_from_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_file = Path(tmpdir) / "modelCatalog.generated.json"
            catalog_file.write_text(json.dumps(_SAMPLE_CATALOG), encoding="utf-8")
            catalog = load_catalog(global_config_dir=tmpdir)
            assert "catalogs" in catalog
            assert "claude" in catalog["catalogs"]

    def test_load_catalog_corrupt_redownload(self):
        """If cached file is corrupt, load_catalog tries to redownload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_file = Path(tmpdir) / "modelCatalog.generated.json"
            catalog_file.write_text("NOT JSON", encoding="utf-8")
            # load_catalog should redownload and succeed (network available)
            # or raise FileNotFoundError if network is down
            try:
                catalog = load_catalog(global_config_dir=tmpdir)
                # If download succeeded, we get a valid catalog
                assert "catalogs" in catalog
            except FileNotFoundError:
                pass  # Expected when no network


class TestAdapterModelInjection:
    """Test that adapters correctly inject --model flags from metadata."""

    def _task(self, provider_models=None, prompt="hello"):
        metadata = {}
        if provider_models:
            metadata["provider_models"] = provider_models
        return TaskInput(
            task_id="test-1",
            prompt=prompt,
            repo_root="/tmp/test",
            target_paths=["."],
            metadata=metadata,
        )

    # ── Claude ──

    def test_claude_with_model(self):
        adapter = ClaudeAdapter()
        cmd = adapter._build_command(self._task({"claude": "claude-opus-4-6"}))
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-opus-4-6"

    def test_claude_without_model(self):
        adapter = ClaudeAdapter()
        cmd = adapter._build_command(self._task())
        assert "--model" not in cmd

    # ── Codex ──

    def test_codex_with_model(self):
        adapter = CodexAdapter()
        cmd = adapter._build_command(self._task({"codex": "o3"}))
        assert "-c" in cmd
        idx = cmd.index("-c")
        assert cmd[idx + 1] == "model=o3"

    def test_codex_without_model(self):
        adapter = CodexAdapter()
        cmd = adapter._build_command(self._task())
        assert "-c" not in cmd

    # ── Cursor ──

    def test_cursor_with_model(self):
        adapter = CursorAdapter()
        cmd = adapter._build_command(self._task({"cursor": "gpt-5"}))
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "gpt-5"

    def test_cursor_without_model(self):
        adapter = CursorAdapter()
        cmd = adapter._build_command(self._task())
        assert "--model" not in cmd

    # ── Gemini ──

    def test_gemini_with_model(self):
        adapter = GeminiAdapter()
        cmd = adapter._build_command(self._task({"gemini": "gemini-2.5-pro"}))
        assert cmd[0] == "agy"
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "gemini-2.5-pro"
        assert "--dangerously-skip-permissions" in cmd

    def test_gemini_without_model(self):
        adapter = GeminiAdapter()
        cmd = adapter._build_command(self._task())
        assert "--model" not in cmd

    # ── Grok ──

    def test_grok_with_model(self):
        adapter = GrokAdapter()
        cmd = adapter._build_command(self._task({"grok": "grok-build"}))
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "grok-build"

    def test_grok_without_model(self):
        adapter = GrokAdapter()
        cmd = adapter._build_command(self._task())
        assert "--model" not in cmd

    # ── OpenCode ──

    def test_opencode_with_model(self):
        adapter = OpenCodeAdapter()
        cmd = adapter._build_command(self._task({"opencode": "opencode/gpt-5-nano"}))
        assert "-m" in cmd
        idx = cmd.index("-m")
        assert cmd[idx + 1] == "opencode/gpt-5-nano"

    def test_opencode_without_model(self):
        adapter = OpenCodeAdapter()
        cmd = adapter._build_command(self._task())
        assert "-m" not in cmd

    # ── Qwen ──

    def test_qwen_with_model(self):
        adapter = QwenAdapter()
        cmd = adapter._build_command(self._task({"qwen": "qwen2.5-coder-32b"}))
        assert "-m" in cmd
        idx = cmd.index("-m")
        assert cmd[idx + 1] == "qwen2.5-coder-32b"
        assert "--auth-type" not in cmd

    def test_qwen_without_model(self):
        adapter = QwenAdapter()
        cmd = adapter._build_command(self._task())
        assert "-m" not in cmd
        assert "--auth-type" not in cmd

    def test_qwen_auth_probe_uses_configured_auth(self):
        adapter = QwenAdapter()
        cmd = adapter._auth_check_command("qwen")
        assert cmd == ["qwen", "Reply with exactly OK", "--output-format", "text"]

    # ── Cross-provider ──

    def test_claude_ignores_other_provider_models(self):
        """Claude adapter should only read its own model, not codex's."""
        adapter = ClaudeAdapter()
        cmd = adapter._build_command(self._task({"codex": "o3"}))
        assert "--model" not in cmd

    def test_claude_uses_own_model_with_others_present(self):
        adapter = ClaudeAdapter()
        cmd = adapter._build_command(self._task({"codex": "o3", "claude": "claude-opus-4-6"}))
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-opus-4-6"
