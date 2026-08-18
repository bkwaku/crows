from __future__ import annotations

import json

from context_runtime import ContextRuntime
from context_runtime.schema import to_mapping

from .repositories import CustomerRepository
from .services import AccountService, BillingService, RenewalService


def approximate_tokens(value: object) -> int:
    return max(1, len(json.dumps(to_mapping(value))) // 4)


def main() -> None:
    repository = CustomerRepository()
    runtime = ContextRuntime()
    runtime.register(repository)
    runtime.register(RenewalService(repository))
    runtime.register(AccountService(repository))
    runtime.register(BillingService())

    direct = runtime.invoke(
        need="Should this customer receive a renewal reminder?",
        kwargs={"customer_id": "123"},
    )
    wrapped = runtime.invoke_callable(
        need="Should this customer receive a renewal reminder?",
        callable=repository.get_customer,
        kwargs={"customer_id": "123"},
    )
    raw = runtime.artifacts.get(wrapped.artifact_id).raw_result

    print("Automatic capability selection")
    print(json.dumps({"content": direct.content, **direct.explain()}, indent=2))
    print("\nExisting tool wrapper")
    print(json.dumps({"content": wrapped.content, **wrapped.explain()}, indent=2))
    print(
        "\nApproximate context reduction: "
        f"{approximate_tokens(raw)} -> {approximate_tokens(wrapped.content)} tokens"
    )


if __name__ == "__main__":
    main()

