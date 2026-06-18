"""Model catalog: cache and resolve model IDs from the packaged MCO catalog.

Set MCO_MODEL_CATALOG_URL to refresh from a trusted external catalog.

Cache policy:
    - File does not exist   → seed from bundled catalog or configured URL
    - File older than 24h   → refresh from configured URL or bundled catalog
    - File younger than 24h → use cached

Cache location: ~/.mco/modelCatalog.generated.json
"""
from __future__ import annotations

from importlib.resources import files
import json
import os
import ssl
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from .provider_identity import canonical_provider_id

_CATALOG_URL_ENV = "MCO_MODEL_CATALOG_URL"
_DEFAULT_GLOBAL_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".mco")
_CACHE_FILENAME = "modelCatalog.generated.json"
_BUNDLED_CATALOG_FILENAME = "model_catalog.json"
_MAX_DOWNLOAD_SECONDS = 15


def catalog_path(global_config_dir: Optional[str] = None) -> Path:
    """Return the path to the cached catalog file."""
    d = global_config_dir or _DEFAULT_GLOBAL_CONFIG_DIR
    return Path(d) / _CACHE_FILENAME


def _is_stale(file_path: Path, max_age_seconds: int = 86400) -> bool:
    """Return True if the file doesn't exist or is older than max_age_seconds."""
    if not file_path.exists():
        return True
    return (time.time() - file_path.stat().st_mtime) > max_age_seconds


def _ssl_context() -> ssl.SSLContext:
    """Return a verifying SSL context."""
    try:
        import certifi  # type: ignore
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _configured_catalog_url() -> str:
    return os.environ.get(_CATALOG_URL_ENV, "").strip()


def _bundled_catalog_bytes() -> Optional[bytes]:
    try:
        return files("runtime").joinpath("schemas", _BUNDLED_CATALOG_FILENAME).read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None


def _write_valid_catalog(data: bytes, dest: Path) -> Optional[Path]:
    parsed = json.loads(data)
    if not isinstance(parsed, dict) or "catalogs" not in parsed:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def download_catalog(
    url: Optional[str] = None,
    dest: Optional[Path] = None,
    global_config_dir: Optional[str] = None,
    timeout: int = _MAX_DOWNLOAD_SECONDS,
) -> Optional[Path]:
    """Write a valid catalog to dest. Uses a configured URL, otherwise the bundled catalog."""
    if dest is None:
        dest = catalog_path(global_config_dir)
    try:
        catalog_url = (url if url is not None else _configured_catalog_url()).strip()
        if catalog_url:
            req = Request(catalog_url, headers={"User-Agent": "mco-model-catalog/1.0"})
            ctx = _ssl_context()
            with urlopen(req, timeout=timeout, context=ctx) as resp:
                return _write_valid_catalog(resp.read(), dest)
        data = _bundled_catalog_bytes()
        if data is None:
            return None
        return _write_valid_catalog(data, dest)
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        return None


def ensure_catalog(global_config_dir: Optional[str] = None) -> Path:
    """Ensure the catalog file is available, downloading if needed.

    - If no file exists, download synchronously (blocking).
    - If file is stale, attempt a background download; on failure, use the stale file.
    - If file is fresh, just return it.
    """
    path = catalog_path(global_config_dir)

    if not path.exists():
        # First-time: must download, blocking
        result = download_catalog(dest=path, global_config_dir=global_config_dir)
        if result is None:
            raise FileNotFoundError(
                f"Could not load model catalog to {path}. "
                "Check the packaged catalog or MCO_MODEL_CATALOG_URL."
            )
        return path

    if _is_stale(path):
        # Stale: try to refresh, but don't block on failure
        download_catalog(dest=path, global_config_dir=global_config_dir)

    return path


def load_catalog(global_config_dir: Optional[str] = None) -> Dict[str, Any]:
    """Load the catalog JSON, ensuring it's cached first. Returns the parsed dict."""
    path = ensure_catalog(global_config_dir)
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, dict) and "catalogs" in data:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    # If the cached file is corrupt, try redownloading
    result = download_catalog(dest=path, global_config_dir=global_config_dir)
    if result is not None:
        try:
            text = result.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict) and "catalogs" in data:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    raise FileNotFoundError(
        f"Model catalog at {path} is corrupt and refresh failed. "
        "Delete it and try 'mco models --refresh'."
    )


def resolve_model(
    provider: str,
    model_or_tier: str,
    catalog: Optional[Dict[str, Any]] = None,
    global_config_dir: Optional[str] = None,
) -> Optional[str]:
    """Resolve a model name or tier to a concrete model ID.

    If model_or_tier is a tier name (fast/balanced/powerful), return the first
    model in that tier. If it's an exact model ID, return it as-is.
    Returns None if the provider is not in the catalog.
    """
    if catalog is None:
        try:
            catalog = load_catalog(global_config_dir)
        except FileNotFoundError:
            # No catalog available: if it looks like a concrete model ID, pass through
            return model_or_tier

    provider_entry = catalog.get("catalogs", {}).get(canonical_provider_id(provider))
    if provider_entry is None:
        # Provider not in catalog (e.g. opencode, qwen): pass through raw value
        return model_or_tier

    # Check if it's an exact model ID first
    for tier_entry in provider_entry.get("tiers", []):
        models = tier_entry.get("models", [])
        if model_or_tier in models:
            return model_or_tier

    # Check if it's a tier name
    for tier_entry in provider_entry.get("tiers", []):
        tier_name = str(tier_entry.get("tier", "")).strip().lower()
        if tier_name == model_or_tier.lower():
            models = list(reversed(tier_entry.get("models", [])))
            if models:
                return models[0]

    # Unknown: pass through as-is (might be a new model not yet in catalog)
    return model_or_tier


def list_models_for_provider(
    provider: str,
    catalog: Optional[Dict[str, Any]] = None,
    global_config_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return a list of tier dicts for a provider: [{tier, label, models}]."""
    if catalog is None:
        try:
            catalog = load_catalog(global_config_dir)
        except FileNotFoundError:
            return []

    provider_entry = catalog.get("catalogs", {}).get(canonical_provider_id(provider))
    if not provider_entry:
        return []

    result = []
    for tier_entry in provider_entry.get("tiers", []):
        tier_name = str(tier_entry.get("tier", "")).strip()
        models = list(reversed(tier_entry.get("models", [])))
        result.append({"tier": tier_name, "models": models})
    return result


def list_providers(
    catalog: Optional[Dict[str, Any]] = None,
    global_config_dir: Optional[str] = None,
) -> List[str]:
    """Return sorted list of provider names in the catalog."""
    if catalog is None:
        try:
            catalog = load_catalog(global_config_dir)
        except FileNotFoundError:
            return []
    return sorted(catalog.get("catalogs", {}).keys())


def parse_provider_models(raw: str) -> Dict[str, str]:
    """Parse --provider-models flag value: 'claude=opus,codex=o3' → {'claude': 'opus', 'codex': 'o3'}."""
    result: Dict[str, str] = {}
    if not raw or not raw.strip():
        return result
    for chunk in raw.split(","):
        pair = chunk.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(
                f"invalid provider-models entry: '{pair}'. "
                "Expected format: provider=model (e.g. claude=opus)"
            )
        provider, model_value = pair.split("=", 1)
        provider_name = canonical_provider_id(provider.strip())
        if not provider_name:
            raise ValueError(f"invalid provider-models entry: '{pair}'")
        model_text = model_value.strip()
        if not model_text:
            raise ValueError(f"empty model value for provider '{provider_name}'")
        result[provider_name] = model_text
    return result
