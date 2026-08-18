from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Profile:
    full_name: str
    email: str | None
    phone: str | None
    locale: str
    timezone: str


@dataclass
class Organization:
    name: str
    domain: str
    employee_count: int
    industry: str


@dataclass
class Permissions:
    account_suspended: bool
    can_purchase: bool
    roles: list[str]


@dataclass
class Subscription:
    plan: str
    status: str
    days_until_renewal: int
    seats: int
    monthly_price: float


@dataclass
class Preferences:
    email_opt_in: bool
    sms_opt_in: bool
    product_updates: bool
    marketing_topics: list[str]


@dataclass
class Address:
    line_1: str
    city: str
    region: str
    postal_code: str
    country: str


@dataclass
class Invoice:
    invoice_id: str
    status: str
    amount: float
    due_date: str


@dataclass
class Payment:
    payment_id: str
    amount: float
    status: str
    created_at: str


@dataclass
class Order:
    order_id: str
    total: float
    status: str
    refundable: bool


@dataclass
class Ticket:
    ticket_id: str
    subject: str
    status: str
    body: str


@dataclass
class Communication:
    channel: str
    subject: str
    body: str
    sent_at: str


@dataclass
class AuditEvent:
    action: str
    actor: str
    occurred_at: str
    metadata: dict[str, str]


@dataclass
class Customer:
    customer_id: str
    profile: Profile
    organization: Organization
    permissions: Permissions
    subscription: Subscription
    preferences: Preferences
    addresses: list[Address] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    tickets: list[Ticket] = field(default_factory=list)
    communications: list[Communication] = field(default_factory=list)
    audit_events: list[AuditEvent] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    custom_fields: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    lifetime_value: float = 0.0
    internal_notes: str = ""

