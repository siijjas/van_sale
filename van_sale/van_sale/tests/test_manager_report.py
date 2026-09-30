"""Tests for the manager dashboard and period report.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_manager_report
"""

import frappe
from frappe.utils import add_days, nowdate

from van_sale.van_sale.finance import submit_route_expense
from van_sale.van_sale.manager_report import get_fleet, get_manager_dashboard, get_period_report
from van_sale.van_sale.sales import create_sales_order, submit_sales_order
from van_sale.van_sale.shift import open_shift
from van_sale.van_sale.tests import test_shift_and_access as base


class TestManagerReport(base.TestShiftAndAccessRegressions):
	"""Reuses the shift tests' driver / Van Profile / customer / item fixtures; the
	parent's own tests are blanked out below so they don't run twice."""

	def _driver_row(self, report: dict) -> dict:
		return next(row for row in report["by_driver"] if row["driver"] == self.driver_user)

	def test_drivers_cannot_read_manager_reports(self):
		for fn, args in ((get_fleet, ()), (get_manager_dashboard, ()), (get_period_report, (nowdate(), nowdate()))):
			with self.assertRaises(frappe.PermissionError):
				fn(*args)

	def test_period_report_and_dashboard_pick_up_driver_activity(self):
		frappe.set_user("Administrator")
		before = self._driver_row(get_period_report(nowdate(), nowdate(), driver=self.driver_user))

		frappe.set_user(self.driver_user)
		so = create_sales_order(self.customer_allowed, [{"item_code": self.item_code, "qty": 3, "rate": 20}])["name"]
		submit_sales_order(so)
		submit_route_expense("Tolls", 7)

		frappe.set_user("Administrator")
		report = get_period_report(nowdate(), nowdate(), driver=self.driver_user)
		after = self._driver_row(report)
		self.assertAlmostEqual(after["sales"] - before["sales"], 60, places=2)
		self.assertEqual(after["orders_count"] - before["orders_count"], 1)
		self.assertAlmostEqual(after["expenses"] - before["expenses"], 7, places=2)
		# Driver filter narrows the fleet to that one driver, and totals are its sum.
		self.assertEqual([row["driver"] for row in report["by_driver"]], [self.driver_user])
		self.assertAlmostEqual(report["totals"]["sales"], after["sales"], places=2)
		self.assertEqual(len(report["daily"]), 1)
		self.assertIn(self.item_code, [row["item_code"] for row in report["items"]])
		self.assertIn("Tolls", [row["expense_type"] for row in report["expenses_by_type"]])
		# The previous period is the same length, immediately before.
		self.assertEqual(report["period"]["previous_to"], str(add_days(nowdate(), -1)))
		self.assertEqual(report["period"]["previous_from"], str(add_days(nowdate(), -1)))

		# Trading without a shift is flagged; opening one shows the van as open.
		dashboard = get_manager_dashboard()
		self.assertIn(
			("no_shift", self.driver_user), {(a["kind"], a["driver"]) for a in dashboard["alerts"]}
		)
		frappe.set_user(self.driver_user)
		open_shift(balance_details=f'[{{"mode_of_payment": "{self.cash_mode}", "opening_amount": 50}}]')
		frappe.set_user("Administrator")
		van = next(v for v in get_manager_dashboard()["vans"] if v["driver"] == self.driver_user)
		self.assertEqual(van["shift_status"], "open")
		self.assertIsNotNone(van["expected_cash"])

	def test_period_report_rejects_bad_ranges(self):
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			get_period_report(nowdate(), add_days(nowdate(), -1))
		with self.assertRaises(frappe.ValidationError):
			get_period_report(add_days(nowdate(), -400), nowdate())


for _name in dir(base.TestShiftAndAccessRegressions):
	if _name.startswith("test_"):
		setattr(TestManagerReport, _name, None)
