from __future__ import annotations

import unittest
from dataclasses import dataclass

from context_runtime import ContextRuntime, NeedUnavailable
from context_runtime.analysis import DependencyAnalyzer


@dataclass
class Subscription:
    status: str
    seats: int

    @property
    def active(self) -> bool:
        return self.status == "active"


@dataclass
class Order:
    status: str
    total: float


@dataclass
class Customer:
    subscription: Subscription
    orders: list[Order]
    private_notes: str


class Repository:
    def get_customer(self, customer_id: str) -> Customer:
        """Return the complete customer record."""
        return Customer(
            subscription=Subscription(status="active", seats=10),
            orders=[Order(status="paid", total=100.0), Order(status="pending", total=50.0)],
            private_notes="secret" * 100,
        )


class DecisionService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def can_renew(self, customer_id: str) -> bool:
        """Determine whether this customer can renew."""
        customer = self.repository.get_customer(customer_id)
        return self._eligible(customer)

    def _eligible(self, customer: Customer) -> bool:
        return self._subscription_ok(customer.subscription) and self._first_order_paid(customer)

    def _subscription_ok(self, subscription: Subscription) -> bool:
        # property should expand to subscription.status; lower() should retain status
        return subscription.active and subscription.status.lower() == "active"

    def _first_order_paid(self, customer: Customer) -> bool:
        # numeric collection indexing should become orders.status for projection
        return customer.orders[0].status == "paid"


class StaticNeedProvider:
    def current_need(self) -> str | None:
        return "Can this customer renew?"


class NewFeatureTests(unittest.TestCase):
    def test_custom_need_provider_removes_need_argument(self) -> None:
        repository = Repository()
        runtime = ContextRuntime(need_provider=StaticNeedProvider())
        runtime.register(repository)
        runtime.register(DecisionService(repository))

        result = runtime.invoke_callable(
            callable=repository.get_customer,
            kwargs={"customer_id": "123"},
        )
        self.assertTrue(result.projected)
        self.assertEqual(
            result.content,
            {
                "subscription": {"status": "active"},
                "orders": [{"status": "paid"}, {"status": "pending"}],
            },
        )
        self.assertEqual(result.explain()["need"], "Can this customer renew?")

    def test_default_provider_supports_scoped_need(self) -> None:
        repository = Repository()
        runtime = ContextRuntime()
        runtime.register(repository)
        runtime.register(DecisionService(repository))

        with runtime.need_scope("Can this customer renew?"):
            result = runtime.invoke_callable(
                callable=repository.get_customer,
                kwargs={"customer_id": "123"},
            )
        self.assertTrue(result.projected)

    def test_missing_need_fails_explicitly(self) -> None:
        runtime = ContextRuntime()
        with self.assertRaises(NeedUnavailable):
            runtime.invoke(kwargs={"customer_id": "123"})

    def test_interprocedural_property_receiver_and_collection_dependencies(self) -> None:
        service = DecisionService(Repository())
        report = DependencyAnalyzer(max_call_depth=4).analyze(
            service.can_renew,
            resource_type=Customer,
        )
        self.assertEqual(
            set(report.paths),
            {"subscription.status", "orders.status"},
        )

@dataclass
class Preferences:
    email_opt_in: bool
@dataclass
class Permissions:
    account_suspended: bool
@dataclass
class Profile:
    email: str | None
@dataclass
class LegacyCustomer:
    subscription: Subscription
    preferences: Preferences
    permissions: Permissions
    profile: Profile
    noise: str
class LegacyRepo:
    def get_customer(self, customer_id: str) -> LegacyCustomer:
        return LegacyCustomer(Subscription('active',10), Preferences(True), Permissions(False), Profile('x@example.com'), 'x'*1000)
class LegacyRenewal:
    def __init__(self, repo: LegacyRepo): self.repo=repo
    def should_send_renewal_reminder(self, customer_id: str) -> bool:
        """Determine whether a customer should receive a renewal reminder."""
        customer=self.repo.get_customer(customer_id)
        subscription=customer.subscription
        eligible=subscription.seats > 0
        if customer.permissions.account_suspended:
            return False
        return subscription.status == 'active' and eligible and customer.preferences.email_opt_in and customer.profile.email is not None

class RegressionTests(unittest.TestCase):
    def test_existing_style_analysis_still_projects(self):
        repo=LegacyRepo(); runtime=ContextRuntime(); runtime.register(repo); runtime.register(LegacyRenewal(repo))
        result=runtime.invoke_callable(need='Should this customer receive a renewal reminder?', callable=repo.get_customer, kwargs={'customer_id':'1'})
        self.assertTrue(result.projected, result.explain())
        self.assertEqual(set(result.dependencies), {'subscription.status','subscription.seats','permissions.account_suspended','preferences.email_opt_in','profile.email'})


@dataclass
class ProvenanceCustomer:
    status: str
    private_notes: str


@dataclass
class Summary:
    status: str


class ProvenanceRepository:
    def get_customer(self, customer_id: str) -> ProvenanceCustomer:
        """Return the complete provenance test customer."""
        return ProvenanceCustomer(
            status="customer-status-is-not-summary-status",
            private_notes="secret" * 100,
        )


class AnalyticsService:
    def calculate_summary(self, customer: ProvenanceCustomer) -> Summary:
        return Summary(status="good")


class DerivedDecisionService:
    def __init__(
        self,
        repository: ProvenanceRepository,
        analytics: AnalyticsService,
    ) -> None:
        self.repository = repository
        self.analytics = analytics

    def is_customer_eligible(self, customer_id: str) -> bool:
        """Determine whether this customer is eligible from an analytics summary."""
        customer = self.repository.get_customer(customer_id)
        summary = self.analytics.calculate_summary(customer)
        return summary.status == "good"

    def is_customer_directly_eligible(self, customer_id: str) -> bool:
        """Determine eligibility using an inline analytics summary."""
        customer = self.repository.get_customer(customer_id)
        return (
            customer.status == "active"
            and self.analytics.calculate_summary(customer).status == "good"
        )


class ProvenanceSafetyTests(unittest.TestCase):
    def test_derived_call_result_is_not_mapped_to_primary_resource(self) -> None:
        repository = ProvenanceRepository()
        service = DerivedDecisionService(repository, AnalyticsService())

        report = DependencyAnalyzer().analyze(
            service.is_customer_eligible,
            resource_type=ProvenanceCustomer,
        )

        self.assertEqual(report.paths, ())
        self.assertEqual(len(report.unresolved), 1)
        self.assertIn("calculate_summary", report.unresolved[0])
        self.assertIn("Summary", report.unresolved[0])
        self.assertIn("ProvenanceCustomer", report.unresolved[0])

    def test_unresolved_derived_dependency_forces_full_result(self) -> None:
        repository = ProvenanceRepository()
        runtime = ContextRuntime()
        runtime.register(repository)
        runtime.register(DerivedDecisionService(repository, AnalyticsService()))

        result = runtime.invoke_callable(
            need="Is this customer eligible from an analytics summary?",
            callable=repository.get_customer,
            kwargs={"customer_id": "123"},
        )

        explanation = result.explain()
        self.assertFalse(result.projected)
        self.assertIsInstance(result.content, ProvenanceCustomer)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.evidence, ("UNRESOLVED_DERIVED_DEPENDENCY",))
        self.assertEqual(
            explanation["fallback_reason"],
            "Reference capability depends on a derived or opaque call result",
        )
        self.assertIn("calculate_summary", explanation["unresolved_dependencies"][0])

    def test_inline_opaque_call_is_also_unresolved(self) -> None:
        repository = ProvenanceRepository()
        service = DerivedDecisionService(repository, AnalyticsService())

        report = DependencyAnalyzer().analyze(
            service.is_customer_directly_eligible,
            resource_type=ProvenanceCustomer,
        )

        self.assertEqual(report.paths, ("status",))
        self.assertEqual(len(report.unresolved), 1)
        self.assertIn("calculate_summary", report.unresolved[0])


if __name__ == "__main__":
    unittest.main()
