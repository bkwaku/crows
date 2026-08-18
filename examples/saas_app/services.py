from __future__ import annotations

import logging

from .repositories import CustomerRepository


logger = logging.getLogger(__name__)


class RenewalService:
    def __init__(self, customer_repository: CustomerRepository) -> None:
        self.customer_repository = customer_repository

    def should_send_renewal_reminder(self, customer_id: str) -> bool:
        """Determine whether a customer should receive a renewal reminder."""
        customer = self.customer_repository.get_customer(customer_id)

        # This access is operational noise and must not enter the static slice.
        logger.info("Checking renewal for %s", customer.audit_events[-1].actor)

        subscription = customer.subscription
        in_reminder_window = subscription.days_until_renewal <= 30
        if customer.permissions.account_suspended:
            return False
        return (
            subscription.status == "active"
            and in_reminder_window
            and customer.preferences.email_opt_in
            and customer.profile.email is not None
        )


class AccountService:
    def __init__(self, customer_repository: CustomerRepository) -> None:
        self.customer_repository = customer_repository

    def is_account_suspended(self, customer_id: str) -> bool:
        """Check whether a customer account is currently suspended."""
        customer = self.customer_repository.get_customer(customer_id)
        return customer.permissions.account_suspended

    def is_customer_contactable(self, customer_id: str) -> bool:
        """Check whether a customer can be contacted through an opted-in channel."""
        customer = self.customer_repository.get_customer(customer_id)
        return (
            customer.preferences.email_opt_in
            and customer.profile.email is not None
        ) or (
            customer.preferences.sms_opt_in
            and customer.profile.phone is not None
        )

    def can_upgrade_plan(self, customer_id: str) -> bool:
        """Determine whether a customer can upgrade their subscription plan."""
        customer = self.customer_repository.get_customer(customer_id)
        return (
            customer.subscription.status == "active"
            and customer.permissions.can_purchase
        )


class BillingService:
    def can_issue_refund(self, order_id: str) -> bool:
        """Determine whether an order is eligible for a refund."""
        return order_id.startswith("ord_")

    def is_invoice_overdue(self, invoice_id: str) -> bool:
        """Determine whether an invoice is overdue."""
        return invoice_id.startswith("overdue_")

