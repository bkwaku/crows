from __future__ import annotations

from uuid import uuid4

from .models import Artifact


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}

    def put(self, capability: str, raw_result: object, projected_result: object) -> str:
        artifact_id = f"artifact_{uuid4().hex}"
        self._artifacts[artifact_id] = Artifact(
            artifact_id=artifact_id,
            capability=capability,
            raw_result=raw_result,
            projected_result=projected_result,
        )
        return artifact_id

    def get(self, artifact_id: str) -> Artifact:
        try:
            return self._artifacts[artifact_id]
        except KeyError as exc:
            raise KeyError(f"Unknown artifact: {artifact_id}") from exc

    def __len__(self) -> int:
        return len(self._artifacts)

