from __future__ import annotations

from .models import (
    Address,
    AuditEvent,
    Communication,
    Customer,
    Invoice,
    Order,
    Organization,
    Payment,
    Permissions,
    Preferences,
    Profile,
    Subscription,
    Ticket,
)


class CustomerRepository:
    def __init__(self) -> None:
        customer = _sample_customer()
        self._customers = {customer.customer_id: customer}
        self.calls = 0

    def get_customer(self, customer_id: str) -> Customer:
        """Get the complete customer record by customer identifier."""
        self.calls += 1
        return self._customers[customer_id]


def _sample_customer() -> Customer:
    verbose_note = (
        "Customer contacted support about workspace configuration, historical "
        "billing exports, and onboarding details. No renewal action was recorded."
    )
    return Customer(
        customer_id="123",
        profile=Profile(
            full_name="Ada Mensah",
            email="ada@example.com",
            phone="+1-555-0100",
            locale="en-US",
            timezone="America/New_York",
        ),
        organization=Organization(
            name="Northstar Labs",
            domain="northstar.example",
            employee_count=240,
            industry="Software",
        ),
        permissions=Permissions(
            account_suspended=False,
            can_purchase=True,
            roles=["admin", "billing"],
        ),
        subscription=Subscription(
            plan="growth",
            status="active",
            days_until_renewal=14,
            seats=85,
            monthly_price=2499.0,
        ),
        preferences=Preferences(
            email_opt_in=True,
            sms_opt_in=False,
            product_updates=True,
            marketing_topics=["platform", "security"],
        ),
        addresses=[
            Address("18 Market Street", "Boston", "MA", "02110", "US")
        ],
        invoices=[Invoice("inv_100", "paid", 2499.0, "2026-08-01")],
        payments=[Payment("pay_100", 2499.0, "succeeded", "2026-08-01")],
        orders=[Order("ord_100", 499.0, "fulfilled", True)],
        tickets=[Ticket("tic_100", "Workspace setup", "closed", verbose_note)],
        communications=[
            Communication("email", f"Account update {index}", verbose_note, "2026-07-15")
            for index in range(40)
        ],
        audit_events=[
            AuditEvent(
                action=f"account.event.{index}",
                actor="system",
                occurred_at="2026-07-15T10:30:00Z",
                metadata={"detail": verbose_note, "request_id": f"req_{index:04d}"},
            )
            for index in range(120)
        ],
        tags=["enterprise", "high-touch", "beta-program"],
        custom_fields={"segment": "mid-market", "region": "north-america"},
        created_at="2021-04-03T12:00:00Z",
        updated_at="2026-08-17T19:12:00Z",
        lifetime_value=184920.0,
        internal_notes=verbose_note * 10,
    )

