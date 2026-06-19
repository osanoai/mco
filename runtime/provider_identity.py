from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, TypeVar


CANONICAL_PROVIDER_ALIASES: Dict[str, str] = {
    "gemini": "antigravity",
}


def canonical_provider_id(provider: str) -> str:
    value = str(provider).strip()
    return CANONICAL_PROVIDER_ALIASES.get(value, value)


def canonical_provider_list(providers: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for provider in providers:
        canonical = canonical_provider_id(provider)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
    return result


T = TypeVar("T")


def canonical_provider_map(values: Optional[Mapping[str, T]]) -> Dict[str, T]:
    """Canonicalize provider-keyed maps.

    If both a legacy and canonical key are present, the canonical key wins.
    """
    if not values:
        return {}
    result: Dict[str, T] = {}
    canonical_keys = {key for key in values if canonical_provider_id(key) == key}
    for key, value in values.items():
        canonical = canonical_provider_id(key)
        if canonical in result and key != canonical:
            continue
        if key != canonical and canonical in canonical_keys:
            continue
        result[canonical] = value
    return result


def canonicalize_detected_by(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return canonical_provider_list(str(item) for item in value if str(item).strip())


def legacy_provider_ids_for(provider: str) -> Tuple[str, ...]:
    canonical = canonical_provider_id(provider)
    aliases = tuple(alias for alias, target in CANONICAL_PROVIDER_ALIASES.items() if target == canonical)
    return (canonical, *aliases)
