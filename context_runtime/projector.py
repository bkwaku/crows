from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .schema import to_mapping


class ProjectionError(ValueError):
    pass


def project(value: Any, paths: tuple[str, ...] | list[str]) -> Any:
    mapped = to_mapping(value)
    if not isinstance(mapped, (Mapping, list)):
        raise ProjectionError("Only structured results can be projected")

    trie: dict[str, dict] = {}
    for path in paths:
        cursor = trie
        for part in path.split("."):
            cursor = cursor.setdefault(part, {})
    if not trie:
        raise ProjectionError("Projection requires at least one field path")

    projected, complete = _project_node(mapped, trie)
    if not complete:
        raise ProjectionError("At least one required dependency was absent from the result")
    return projected


def _project_node(value: Any, trie: dict[str, dict]) -> tuple[Any, bool]:
    if not trie:
        return value, True
    if isinstance(value, list):
        items = [_project_node(item, trie) for item in value]
        return [item for item, _ in items], all(complete for _, complete in items)
    if not isinstance(value, Mapping):
        return None, False

    result: dict[str, Any] = {}
    complete = True
    for key, child_trie in trie.items():
        if key not in value:
            complete = False
            continue
        child, child_complete = _project_node(value[key], child_trie)
        result[key] = child
        complete = complete and child_complete
    return result, complete

