from __future__ import annotations

import json

from context_runtime import ContextRuntime
from context_runtime.schema import to_mapping
from examples.saas_app import AccountService, CustomerRepository, RenewalService


CASES = (
    (
        "Should this customer receive a renewal reminder?",
        {
            "permissions.account_suspended",
            "preferences.email_opt_in",
            "profile.email",
            "subscription.days_until_renewal",
            "subscription.status",
        },
    ),
    (
        "Is this customer account suspended?",
        {"permissions.account_suspended"},
    ),
    (
        "Can this customer be contacted?",
        {
            "preferences.email_opt_in",
            "preferences.sms_opt_in",
            "profile.email",
            "profile.phone",
        },
    ),
    (
        "Can this customer upgrade their subscription plan?",
        {"permissions.can_purchase", "subscription.status"},
    ),
)


def approximate_tokens(value: object) -> int:
    return max(1, len(json.dumps(to_mapping(value))) // 4)


def run() -> list[dict[str, object]]:
    repository = CustomerRepository()
    runtime = ContextRuntime()
    runtime.register(repository)
    runtime.register(RenewalService(repository))
    runtime.register(AccountService(repository))

    rows: list[dict[str, object]] = []
    for need, required_paths in CASES:
        result = runtime.invoke_callable(
            need=need,
            callable=repository.get_customer,
            kwargs={"customer_id": "123"},
        )
        raw = runtime.artifacts.get(result.artifact_id).raw_result
        retained = set(result.dependencies)
        recall = len(required_paths & retained) / len(required_paths)
        raw_tokens = approximate_tokens(raw)
        projected_tokens = approximate_tokens(result.content)
        rows.append(
            {
                "need": need,
                "reference_capability": result.explain()["reference_capability"],
                "projection_recall": recall,
                "raw_tokens": raw_tokens,
                "projected_tokens": projected_tokens,
                "context_reduction": 1 - projected_tokens / raw_tokens,
            }
        )
    return rows


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

