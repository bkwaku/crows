from __future__ import annotations

import unittest

from context_runtime import ContextRuntime
from context_runtime.runtime import CapabilityNotFound
from examples.saas_app import (
    AccountService,
    BillingService,
    CustomerRepository,
    RenewalService,
)
from examples.saas_app.models import Customer


class DictRepository:
    def fetch_user(self, user_id: str) -> dict:
        """Fetch the complete user record."""
        return {
            "status": "active",
            "settings": {"enabled": True, "theme": "dark"},
            "private_notes": ["irrelevant"] * 100,
        }


class DictDecisionService:
    def __init__(self, repository: DictRepository) -> None:
        self.repository = repository

    def is_user_enabled(self, user_id: str) -> bool:
        """Determine whether a user is active and enabled."""
        user = self.repository.fetch_user(user_id)
        return user["status"] == "active" and user["settings"]["enabled"]


class MissingFieldService:
    def __init__(self, repository: DictRepository) -> None:
        self.repository = repository

    def can_access_beta(self, user_id: str) -> bool:
        """Determine whether a user can access beta features."""
        user = self.repository.fetch_user(user_id)
        return user["entitlements"]["beta"]


class FirstFeatureService:
    def __init__(self, repository: DictRepository) -> None:
        self.repository = repository

    def can_access_feature(self, user_id: str) -> bool:
        """Determine whether a user can access a feature."""
        user = self.repository.fetch_user(user_id)
        return user["status"] == "active"


class SecondFeatureService:
    def __init__(self, repository: DictRepository) -> None:
        self.repository = repository

    def can_access_feature(self, user_id: str) -> bool:
        """Determine whether a user can access a feature."""
        user = self.repository.fetch_user(user_id)
        return user["settings"]["enabled"]


class ContextRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = CustomerRepository()
        self.runtime = ContextRuntime()
        self.runtime.register(self.repository)
        self.runtime.register(RenewalService(self.repository))
        self.runtime.register(AccountService(self.repository))
        self.runtime.register(BillingService())

    def test_invoke_selects_and_executes_business_capability(self) -> None:
        result = self.runtime.invoke(
            need="Should this customer receive a renewal reminder?",
            kwargs={"customer_id": "123"},
        )

        self.assertIs(result.content, True)
        self.assertEqual(
            result.capability, "RenewalService.should_send_renewal_reminder"
        )
        self.assertEqual(result.explain()["decision"], "direct_capability")
        self.assertEqual(self.repository.calls, 1)
        self.assertIs(
            self.runtime.artifacts.get(result.artifact_id).raw_result,
            result.content,
        )

    def test_invoke_filters_capabilities_by_supplied_inputs(self) -> None:
        result = self.runtime.invoke(
            need="Can this order receive a refund?",
            kwargs={"order_id": "ord_100"},
        )

        self.assertEqual(result.capability, "BillingService.can_issue_refund")
        self.assertIs(result.content, True)

    def test_wrapper_projects_broad_result_and_retains_raw_artifact(self) -> None:
        result = self.runtime.invoke_callable(
            need="Should this customer receive a renewal reminder?",
            callable=self.repository.get_customer,
            kwargs={"customer_id": "123"},
        )

        self.assertTrue(result.projected)
        self.assertEqual(
            result.content,
            {
                "permissions": {"account_suspended": False},
                "preferences": {"email_opt_in": True},
                "profile": {"email": "ada@example.com"},
                "subscription": {
                    "days_until_renewal": 14,
                    "status": "active",
                },
            },
        )
        artifact = self.runtime.artifacts.get(result.artifact_id)
        self.assertIsInstance(artifact.raw_result, Customer)
        self.assertIs(artifact.projected_result, result.content)
        self.assertEqual(self.repository.calls, 1)

    def test_wrapper_projects_dictionary_paths(self) -> None:
        repository = DictRepository()
        runtime = ContextRuntime()
        runtime.register(repository)
        runtime.register(DictDecisionService(repository))

        result = runtime.invoke_callable(
            need="Is this user active and enabled?",
            callable=repository.fetch_user,
            kwargs={"user_id": "u_1"},
        )

        self.assertTrue(result.projected)
        self.assertEqual(
            result.content,
            {"status": "active", "settings": {"enabled": True}},
        )

    def test_missing_required_dependency_falls_back_to_full_result(self) -> None:
        repository = DictRepository()
        runtime = ContextRuntime()
        runtime.register(repository)
        runtime.register(MissingFieldService(repository))

        result = runtime.invoke_callable(
            need="Can this user access beta features?",
            callable=repository.fetch_user,
            kwargs={"user_id": "u_1"},
        )

        self.assertFalse(result.projected)
        self.assertIn("private_notes", result.content)
        self.assertIn("absent", result.explain()["fallback_reason"])

    def test_ambiguous_reference_match_returns_full_result(self) -> None:
        repository = DictRepository()
        runtime = ContextRuntime()
        runtime.register(repository)
        runtime.register(FirstFeatureService(repository))
        runtime.register(SecondFeatureService(repository))

        result = runtime.invoke_callable(
            need="Can this user access a feature?",
            callable=repository.fetch_user,
            kwargs={"user_id": "u_1"},
        )

        explanation = result.explain()
        self.assertFalse(result.projected)
        self.assertIn("private_notes", result.content)
        self.assertEqual(result.confidence, 0.0)
        self.assertTrue(explanation["reference_match_ambiguous"])
        self.assertEqual(
            explanation["fallback_reason"],
            "Reference capability retrieval was ambiguous",
        )
        self.assertEqual(result.evidence, ("AMBIGUOUS_REFERENCE_MATCH",))

    def test_no_dependency_evidence_falls_back_to_raw_object(self) -> None:
        runtime = ContextRuntime()
        runtime.register(self.repository)

        result = runtime.invoke_callable(
            need="Summarize this customer's history",
            callable=self.repository.get_customer,
            kwargs={"customer_id": "123"},
        )

        self.assertFalse(result.projected)
        self.assertIsInstance(result.content, Customer)
        self.assertEqual(result.confidence, 0.0)

    def test_unknown_need_raises_instead_of_guessing(self) -> None:
        with self.assertRaises(CapabilityNotFound):
            self.runtime.invoke(
                need="Translate a legal document",
                kwargs={"customer_id": "123"},
            )


if __name__ == "__main__":
    unittest.main()
