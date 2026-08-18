from __future__ import annotations

from .models import DependencyReport, RetrievalMatch


def projection_confidence(
    match: RetrievalMatch | None,
    dependencies: DependencyReport,
) -> tuple[float, tuple[str, ...]]:
    if dependencies.unresolved:
        return 0.0, ("UNRESOLVED_DERIVED_DEPENDENCY",)
    if match is None or not dependencies.paths:
        return 0.0, ()

    evidence: list[str] = []
    score = 0.0
    if dependencies.return_paths:
        score += 0.65
        evidence.append("STATIC_RETURN_DEPENDENCY")
    if dependencies.branch_paths:
        score += 0.10
        evidence.append("STATIC_BRANCH_DEPENDENCY")
    if match.score > 0:
        score += 0.15
        evidence.append("LEXICAL_CAPABILITY_MATCH")
    if match.runner_up_score == 0 or match.score >= match.runner_up_score * 1.15:
        score += 0.10
        evidence.append("RETRIEVAL_MARGIN")
    return min(score, 1.0), tuple(evidence)
