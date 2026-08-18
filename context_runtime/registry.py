from __future__ import annotations

import inspect
from collections.abc import Iterable
from typing import Any, get_type_hints

from .models import Capability, ParameterSpec
from .schema import schema_paths


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, target: object, *, include: Iterable[str] | None = None) -> list[Capability]:
        include_names = set(include) if include is not None else None
        discovered: list[Capability] = []

        if inspect.isfunction(target) or inspect.ismethod(target):
            discovered.append(self._from_callable(target))
        else:
            for name, member in inspect.getmembers(target, predicate=callable):
                if name.startswith("_"):
                    continue
                if include_names is not None and name not in include_names:
                    continue
                discovered.append(self._from_callable(member))

        for capability in discovered:
            self._capabilities[capability.qualified_name] = capability
        return discovered

    def _from_callable(self, function: Any) -> Capability:
        signature = inspect.signature(function)
        try:
            hints = get_type_hints(function)
        except (NameError, TypeError):
            hints = {}
        parameters = tuple(
            ParameterSpec(
                name=name,
                required=parameter.default is inspect.Parameter.empty,
                annotation=_annotation_name(hints.get(name, parameter.annotation)),
            )
            for name, parameter in signature.parameters.items()
            if name not in {"self", "cls"}
            and parameter.kind
            not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        )
        owner = getattr(function, "__self__", None)
        owner_name = owner.__class__.__name__ if owner is not None else function.__module__
        qualified_name = f"{owner_name}.{function.__name__}"
        return_annotation = hints.get("return", signature.return_annotation)
        if return_annotation is inspect.Signature.empty:
            return_annotation = None
        return Capability(
            name=function.__name__,
            qualified_name=qualified_name,
            callable=function,
            description=inspect.getdoc(function) or "",
            parameters=parameters,
            return_annotation=return_annotation,
            schema_paths=schema_paths(return_annotation),
        )

    def describe(self, function: Any) -> Capability:
        return self._from_callable(function)

    def all(self) -> tuple[Capability, ...]:
        return tuple(self._capabilities.values())

    def find_callable(self, function: Any) -> Capability | None:
        for capability in self._capabilities.values():
            if capability.callable == function:
                return capability
        return None

    def __len__(self) -> int:
        return len(self._capabilities)


def _annotation_name(annotation: Any) -> str | None:
    if annotation is inspect.Parameter.empty:
        return None
    return getattr(annotation, "__name__", str(annotation))
