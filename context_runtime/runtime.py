from __future__ import annotations

from typing import Any, Callable

from .analysis import DependencyAnalyzer
from .artifacts import InMemoryArtifactStore
from .confidence import projection_confidence
from .models import Capability, InvocationResult, RetrievalMatch
from .projector import ProjectionError, project
from .registry import CapabilityRegistry
from .retrieval import BM25Retriever
from .schema import is_scalar


class CapabilityNotFound(LookupError):
    pass


class ContextRuntime:
    def __init__(
        self,
        *,
        projection_threshold: float = 0.85,
        selection_margin_ratio: float = 1.10,
    ) -> None:
        self.registry = CapabilityRegistry()
        self.artifacts = InMemoryArtifactStore()
        self.retriever = BM25Retriever()
        self.analyzer = DependencyAnalyzer()
        self.projection_threshold = projection_threshold
        self.selection_margin_ratio = selection_margin_ratio

    def register(self, target: object, *, include: list[str] | None = None) -> None:
        self.registry.register(target, include=include)

    def invoke(self, *, need: str, kwargs: dict[str, Any]) -> InvocationResult:
        """Select and execute the registered capability that best satisfies a need."""
        compatible = tuple(
            capability
            for capability in self.registry.all()
            if capability.accepts(kwargs)
        )
        match = self.retriever.match(need, compatible)
        if match is None:
            raise CapabilityNotFound(
                f"No registered capability matched the need with inputs {sorted(kwargs)}"
            )
        if (
            match.runner_up_score > 0
            and match.score < match.runner_up_score * self.selection_margin_ratio
        ):
            raise CapabilityNotFound(
                "Capability retrieval was ambiguous; provide a more specific need"
            )

        raw_result = match.capability.callable(**kwargs)
        evidence = ("DIRECT_CAPABILITY", "LEXICAL_CAPABILITY_MATCH")
        artifact_id = self.artifacts.put(
            match.capability.qualified_name, raw_result, raw_result
        )
        return InvocationResult(
            content=raw_result,
            artifact_id=artifact_id,
            capability=match.capability.qualified_name,
            confidence=1.0,
            projected=False,
            evidence=evidence,
            retrieval_score=match.score,
            _explanation={
                "need": need,
                "selected_capability": match.capability.qualified_name,
                "selection_score": round(match.score, 4),
                "runner_up_score": round(match.runner_up_score, 4),
                "decision": "direct_capability",
                "projected": False,
                "evidence": list(evidence),
            },
        )

    def invoke_callable(
        self,
        *,
        need: str,
        callable: Callable[..., Any],
        kwargs: dict[str, Any],
    ) -> InvocationResult:
        """Execute an already-selected tool and conservatively project its result."""
        called_capability = (
            self.registry.find_callable(callable) or self.registry.describe(callable)
        )
        raw_result = callable(**kwargs)

        reference_match = self._reference_match(
            need=need,
            kwargs=kwargs,
            exclude=called_capability,
        )
        dependencies = (
            self.analyzer.analyze(reference_match.capability.callable)
            if reference_match is not None
            else self.analyzer.analyze(callable)
        )
        confidence, evidence = projection_confidence(reference_match, dependencies)

        projected_result = raw_result
        projected = False
        decision = "full_result_fallback"
        fallback_reason: str | None = None
        if is_scalar(raw_result):
            confidence = 1.0
            evidence = ("DIRECT_SCALAR_RESULT",)
            decision = "scalar_result"
        elif confidence >= self.projection_threshold:
            try:
                projected_result = project(raw_result, dependencies.paths)
                projected = True
                decision = "static_dependency_projection"
            except ProjectionError as exc:
                fallback_reason = str(exc)
        else:
            fallback_reason = "Projection evidence did not meet the confidence threshold"

        artifact_id = self.artifacts.put(
            called_capability.qualified_name,
            raw_result,
            projected_result,
        )
        explanation = {
            "need": need,
            "called_capability": called_capability.qualified_name,
            "reference_capability": (
                reference_match.capability.qualified_name
                if reference_match is not None
                else None
            ),
            "decision": decision,
            "projected": projected,
            "confidence": round(confidence, 4),
            "threshold": self.projection_threshold,
            "dependencies": list(dependencies.paths),
            "evidence": list(evidence),
        }
        if fallback_reason is not None:
            explanation["fallback_reason"] = fallback_reason

        return InvocationResult(
            content=projected_result,
            artifact_id=artifact_id,
            capability=called_capability.qualified_name,
            confidence=confidence,
            projected=projected,
            evidence=evidence,
            dependencies=dependencies.paths,
            retrieval_score=reference_match.score if reference_match else 0.0,
            _explanation=explanation,
        )

    def _reference_match(
        self,
        *,
        need: str,
        kwargs: dict[str, Any],
        exclude: Capability,
    ) -> RetrievalMatch | None:
        candidates = tuple(
            capability
            for capability in self.registry.all()
            if capability.qualified_name != exclude.qualified_name
            and capability.accepts(kwargs)
        )
        return self.retriever.match(need, candidates)
