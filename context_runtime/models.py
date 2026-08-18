from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    required: bool
    annotation: str | None = None


@dataclass
class Capability:
    name: str
    qualified_name: str
    callable: Callable[..., Any]
    description: str
    parameters: tuple[ParameterSpec, ...]
    return_annotation: Any = None
    schema_paths: tuple[str, ...] = ()

    @property
    def search_document(self) -> str:
        schema = " ".join(self.schema_paths)
        return f"{self.name} {self.qualified_name} {self.description} {schema}"

    def accepts(self, kwargs: dict[str, Any]) -> bool:
        supplied = set(kwargs)
        known = {parameter.name for parameter in self.parameters}
        required = {
            parameter.name for parameter in self.parameters if parameter.required
        }
        return required <= supplied and supplied <= known


@dataclass(frozen=True)
class RetrievalMatch:
    capability: Capability
    score: float
    runner_up_score: float


@dataclass(frozen=True)
class DependencyReport:
    paths: tuple[str, ...]
    return_paths: tuple[str, ...] = ()
    branch_paths: tuple[str, ...] = ()


@dataclass
class Artifact:
    artifact_id: str
    capability: str
    raw_result: Any
    projected_result: Any


@dataclass
class InvocationResult:
    content: Any
    artifact_id: str
    capability: str
    confidence: float
    projected: bool
    evidence: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    retrieval_score: float = 0.0
    _explanation: dict[str, Any] = field(default_factory=dict, repr=False)

    def explain(self) -> dict[str, Any]:
        """Return a serializable account of selection and projection decisions."""
        return dict(self._explanation)

