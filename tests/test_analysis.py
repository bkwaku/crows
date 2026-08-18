from __future__ import annotations

import unittest

from context_runtime.analysis import DependencyAnalyzer
from examples.saas_app import CustomerRepository, RenewalService


class DependencyAnalyzerTests(unittest.TestCase):
    def test_follows_aliases_and_return_controlling_branches(self) -> None:
        service = RenewalService(CustomerRepository())

        report = DependencyAnalyzer().analyze(
            service.should_send_renewal_reminder
        )

        self.assertEqual(
            set(report.paths),
            {
                "permissions.account_suspended",
                "preferences.email_opt_in",
                "profile.email",
                "subscription.days_until_renewal",
                "subscription.status",
            },
        )
        self.assertEqual(
            set(report.branch_paths), {"permissions.account_suspended"}
        )
        self.assertNotIn("audit_events", " ".join(report.paths))


if __name__ == "__main__":
    unittest.main()

