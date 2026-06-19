from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, List


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "runtime" / "schemas" / "review_findings.schema.json"


def _object_type_declared(node: dict[str, Any]) -> bool:
    node_type = node.get("type")
    if node_type == "object":
        return True
    if isinstance(node_type, list) and "object" in node_type:
        return True
    return "properties" in node


def _walk_schema(node: Any, path: str = "$") -> List[tuple[str, dict[str, Any]]]:
    objects: List[tuple[str, dict[str, Any]]] = []
    if not isinstance(node, dict):
        return objects
    if _object_type_declared(node):
        objects.append((path, node))

    properties = node.get("properties")
    if isinstance(properties, dict):
        for key, value in properties.items():
            objects.extend(_walk_schema(value, f"{path}.properties.{key}"))

    items = node.get("items")
    if isinstance(items, dict):
        objects.extend(_walk_schema(items, f"{path}.items"))
    elif isinstance(items, list):
        for index, item in enumerate(items):
            objects.extend(_walk_schema(item, f"{path}.items[{index}]"))

    for key in ("$defs", "definitions"):
        defs = node.get(key)
        if isinstance(defs, dict):
            for name, value in defs.items():
                objects.extend(_walk_schema(value, f"{path}.{key}.{name}"))

    for key in ("anyOf", "oneOf", "allOf"):
        branches = node.get(key)
        if isinstance(branches, list):
            for index, branch in enumerate(branches):
                objects.extend(_walk_schema(branch, f"{path}.{key}[{index}]"))

    return objects


class CodexOutputSchemaTests(unittest.TestCase):
    def test_review_findings_schema_is_strict_structured_output_compatible(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        for path, node in _walk_schema(schema):
            with self.subTest(path=path):
                self.assertIs(node.get("additionalProperties"), False)
                properties = node.get("properties")
                self.assertIsInstance(properties, dict)
                self.assertEqual(set(node.get("required", [])), set(properties.keys()))


if __name__ == "__main__":
    unittest.main()
