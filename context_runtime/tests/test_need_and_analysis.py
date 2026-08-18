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
        report = DependencyAnalyzer(max_call_depth=4).analyze(service.can_renew)
        self.assertEqual(
            set(report.paths),
            {"subscription.status", "orders.status"},
        )


if __name__ == "__main__":
    unittest.main()

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
