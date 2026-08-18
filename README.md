# Minimum-Sufficient Context Runtime Prototype

This repository is a dependency-free Python prototype for selecting an existing
application capability and exposing only the result needed by an AI agent. It
does not use a generative model.

The headline API does not require the caller to choose a function:

```python
from context_runtime import ContextRuntime

runtime = ContextRuntime()
runtime.register(customer_repository)
runtime.register(renewal_service)

result = runtime.invoke(
    need="Should this customer receive a renewal reminder?",
    kwargs={"customer_id": "123"},
)

print(result.content)       # True
print(result.capability)    # RenewalService.should_send_renewal_reminder
print(result.explain())     # Selection and evidence manifest
```

The runtime first filters registered capabilities by input compatibility, then
uses local BM25-style lexical retrieval over names, documentation, signatures,
and return schemas. It executes the selected application function unchanged.

## Existing Tool Integration

When an existing agent framework has already selected a broad tool, the wrapper
API executes it and projects the result using dependencies extracted from the
best matching business capability:

```python
result = runtime.invoke_callable(
    need="Should this customer receive a renewal reminder?",
    callable=customer_repository.get_customer,
    kwargs={"customer_id": "123"},
)
```

For the included SaaS example, `get_customer` returns a large nested dataclass.
The model-visible result is reduced to:

```python
{
    "permissions": {"account_suspended": False},
    "preferences": {"email_opt_in": True},
    "profile": {"email": "ada@example.com"},
    "subscription": {
        "days_until_renewal": 14,
        "status": "active",
    },
}
```

The complete `Customer` remains available outside model context:

```python
artifact = runtime.artifacts.get(result.artifact_id)
raw_customer = artifact.raw_result
```

## Safety Rule

Projection is evidence based. The AST analyzer follows field reads in return
expressions, local aliases, and branch conditions that control returns. Logging
and unrelated accesses do not enter the slice. Projection only occurs when:

- a compatible business capability matches the need;
- static return dependencies were found;
- retrieval evidence clears the configured confidence threshold; and
- every required dependency exists in the actual result.

If any check fails, the runtime returns the full result. The prototype therefore
prefers correctness over context reduction.

## Run It

The checked-out workspace already contains an isolated `.venv`. To recreate it:

```bash
python3 -m venv .venv
```

There are no third-party dependencies to install. Run the demo, benchmark, and
tests from the repository root:

```bash
.venv/bin/python -m examples.saas_app.demo
.venv/bin/python -m benchmarks.prototype
.venv/bin/python -m unittest discover -s tests -v
```

## Package Layout

```text
context_runtime/
  analysis.py       Python AST dependency slicing
  artifacts.py      In-memory raw result retention
  confidence.py     Evidence-based projection scoring
  projector.py      Dict, dataclass, and Pydantic-compatible projection
  registry.py       Explicit capability discovery and schema inspection
  retrieval.py      Local BM25-style capability retrieval
  runtime.py        Public invoke APIs and fallback policy
  schema.py         Return schema and runtime value normalization
examples/saas_app/  Broad customer model, repository, and business services
benchmarks/         Gold dependency recall and reduction harness
tests/              Selection, analysis, projection, artifact, and fallback tests
```

## Deliberate V0 Limits

This prototype supports synchronous, read-only Python functions and methods with
dict, dataclass, scalar, or Pydantic-style results. Registration is explicit and
artifacts are process-local. It does not rewrite database queries, generate SQL,
use embeddings, crawl arbitrary packages, or provide framework-specific agent
adapters yet.

