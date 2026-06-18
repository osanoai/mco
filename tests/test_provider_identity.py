from runtime.provider_identity import (
    canonical_provider_id,
    canonical_provider_list,
    canonical_provider_map,
    canonicalize_detected_by,
)


def test_canonical_provider_id_maps_legacy_gemini() -> None:
    assert canonical_provider_id("gemini") == "antigravity"
    assert canonical_provider_id("antigravity") == "antigravity"


def test_canonical_provider_list_dedupes_aliases() -> None:
    assert canonical_provider_list(["claude", "gemini", "antigravity", "claude"]) == [
        "claude",
        "antigravity",
    ]


def test_canonical_provider_map_rekeys_legacy_and_prefers_canonical() -> None:
    assert canonical_provider_map({"gemini": 30}) == {"antigravity": 30}
    assert canonical_provider_map({"gemini": 30, "antigravity": 60}) == {"antigravity": 60}


def test_canonicalize_detected_by_filters_and_dedupes() -> None:
    assert canonicalize_detected_by(["gemini", "", "antigravity", "claude"]) == [
        "antigravity",
        "claude",
    ]
