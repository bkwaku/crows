from __future__ import annotations

import dataclasses
import types
from collections.abc import Mapping, Sequence
from typing import Any, Union, get_args, get_origin, get_type_hints


_SCALAR_TYPES = {str, int, float, bool, bytes, type(None)}


def is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool, bytes))


def to_mapping(value: Any) -> Any:
    """Convert supported structured values without requiring their libraries."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_mapping(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return to_mapping(model_dump())
    dict_method = getattr(value, "dict", None)
    if callable(dict_method) and value.__class__.__module__.startswith("pydantic"):
        return to_mapping(dict_method())
    if isinstance(value, Mapping):
        return {str(key): to_mapping(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_mapping(item) for item in value]
    return value


def schema_paths(annotation: Any, prefix: str = "", depth: int = 0) -> tuple[str, ...]:
    if annotation in (None, Any) or depth > 8:
        return ()

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (Union, types.UnionType):
        paths: set[str] = set()
        for argument in args:
            if argument is not type(None):
                paths.update(schema_paths(argument, prefix, depth + 1))
        return tuple(sorted(paths))
    if origin in (list, tuple, set, frozenset, Sequence):
        return schema_paths(args[0], prefix, depth + 1) if args else ()
    if origin in (dict, Mapping):
        return ()
    if annotation in _SCALAR_TYPES:
        return (prefix,) if prefix else ()

    fields: dict[str, Any] = {}
    if dataclasses.is_dataclass(annotation):
        try:
            fields = get_type_hints(annotation)
        except (NameError, TypeError):
            fields = {field.name: field.type for field in dataclasses.fields(annotation)}
    elif hasattr(annotation, "model_fields"):
        fields = {
            name: getattr(field, "annotation", Any)
            for name, field in annotation.model_fields.items()
        }
    elif hasattr(annotation, "__annotations__"):
        try:
            fields = get_type_hints(annotation)
        except (NameError, TypeError):
            fields = dict(annotation.__annotations__)

    paths: set[str] = set()
    for name, field_annotation in fields.items():
        path = f"{prefix}.{name}" if prefix else name
        nested = schema_paths(field_annotation, path, depth + 1)
        paths.update(nested or (path,))
    return tuple(sorted(paths))


def observed_paths(value: Any, prefix: str = "", depth: int = 0) -> tuple[str, ...]:
    if depth > 8:
        return ()
    mapped = to_mapping(value)
    if not isinstance(mapped, Mapping):
        return (prefix,) if prefix else ()
    paths: set[str] = set()
    for name, item in mapped.items():
        path = f"{prefix}.{name}" if prefix else str(name)
        nested = observed_paths(item, path, depth + 1)
        paths.update(nested or (path,))
    return tuple(sorted(paths))

