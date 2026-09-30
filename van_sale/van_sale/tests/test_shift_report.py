"""Tests for the shift summary (open shift snapshot) and closing report (closed shift).

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_shift_report
"""

import frappe
from frappe.utils import flt, now_datetime, nowdate

from van_sale.van_sale.finance import submit_route_expense
from van_sale.van_sale.sales import create_sales_order, submit_sales_order
from van_sale.van_sale.shift import close_shift, open_shift
from van_sale.van_sale.shift_report import get_closing_report, get_shift_closings, get_shift_summary
from van_sale.van_sale.tests import test_shift_and_access as base


class TestShiftReports(base.TestShiftAndAccessRegressions):
	"""Reuses the driver / Van Profile / customer / item fixtures of the shift tests.

	The parent's own tests are blanked out below so they don't run twice. Same-day data
	for the test driver can survive from other tests in the run, so assertions compare
	against a shift summary taken at the start rather than against absolute totals.
	"""

	def _item_qty(self, report: dict) -> float:
		return next((row["net_qty"] for row in report["items"] if row["item_code"] == self.item_code), 0.0)

	def test_summary_tracks_open_shift_and_closing_report_matches_close(self):
		opening = open_shift(balance_details=f'[{{"mode_of_payment": "{self.cash_mode}", "opening_amount": 100}}]')
		before = get_shift_summary()
		self.assertEqual(before["report_type"], "summary")
		self.assertEqual(before["shift"]["opening_shift"], opening["name"])

		so = create_sales_order(self.customer_allowed, [{"item_code": self.item_code, "qty": 2, "rate": 50}])["name"]
		submit_sales_order(so)
		submit_route_expense("Fuel", 10, "Test fill-up")

		closings_before = frappe.db.count("Van Shift Closing")
		after = get_shift_summary()
		# Running a shift summary must not close the shift or write a closing.
		self.assertEqual(frappe.db.count("Van Shift Closing"), closings_before)
		self.assertEqual(frappe.db.get_value("Van Shift Opening", opening["name"], "status"), "Open")

		self.assertAlmostEqual(after["totals"]["total_sales"] - before["totals"]["total_sales"], 100, places=2)
		self.assertEqual(after["totals"]["sales_orders_count"] - before["totals"]["sales_orders_count"], 1)
		self.assertAlmostEqual(after["totals"]["expected_cash"] - before["totals"]["expected_cash"], -10, places=2)
		self.assertAlmostEqual(self._item_qty(after) - self._item_qty(before), 2)
		self.assertIn("Test fill-up", [e["notes"] for e in after["expenses"]])
		self.assertTrue(all(r["closing_amount"] is None for r in after["payment_reconciliation"]))

		# Count 5 over expected on the cash mode.
		counted = [
			{"mode_of_payment": r["mode_of_payment"], "closing_amount": r["expected_amount"] + (5 if r["mode_of_payment"] == self.cash_mode else 0)}
			for r in after["payment_reconciliation"]
		]
		closing = close_shift(opening_shift=opening["name"], reconciliation=frappe.as_json(counted))

		y = get_closing_report(closing["name"])
		self.assertEqual(y["report_type"], "closing")
		self.assertEqual(y["shift"]["closing_shift"], closing["name"])
		self.assertAlmostEqual(y["totals"]["net_difference"], 5, places=2)
		self.assertAlmostEqual(y["totals"]["total_sales"], after["totals"]["total_sales"], places=2)
		self.assertAlmostEqual(y["totals"]["expected_cash"], after["totals"]["expected_cash"], places=2)
		self.assertEqual(y["items"], after["items"])
		self.assertEqual(y["expenses"], after["expenses"])
		cash_row = next(r for r in y["payment_reconciliation"] if r["mode_of_payment"] == self.cash_mode)
		self.assertAlmostEqual(cash_row["difference"], 5, places=2)

		# The closing now records invoices too (none here, but the Sales Order is there).
		self.assertIn(("Sales Order", so), {(t.reference_doctype, t.reference_name) for t in frappe.get_doc("Van Shift Closing", closing["name"]).transactions})

		self.assertIn(closing["name"], [row.name for row in get_shift_closings()])

		# Once closed, the shift has a closing report and no summary.
		with self.assertRaises(frappe.ValidationError):
			get_shift_summary(opening["name"])
		with self.assertRaises(frappe.ValidationError):
			get_shift_summary()

		if frappe.db.exists("Print Format", "Van Shift Closing Report"):
			html = frappe.get_print("Van Shift Closing", closing["name"], print_format="Van Shift Closing Report")
			self.assertIn("Closing Report", html)
			self.assertIn(closing["name"], html)

	def test_driver_cannot_view_another_drivers_reports(self):
		frappe.set_user("Administrator")
		other = frappe.get_doc(
			{
				"doctype": "Van Shift Opening",
				"driver": "Administrator",
				"shift_date": nowdate(),
				"status": "Open",
				"company": self.company,
				"period_start": now_datetime(),
			}
		)
		other.insert(ignore_permissions=True)
		other.submit()

		frappe.set_user(self.driver_user)
		with self.assertRaises(frappe.PermissionError):
			get_shift_summary(other.name)
		self.assertNotIn("Administrator", {row.driver for row in get_shift_closings()})

		# A manager can read any driver's open shift.
		frappe.set_user("Administrator")
		self.assertEqual(get_shift_summary(other.name)["shift"]["driver"], "Administrator")
		self.assertEqual(flt(get_shift_summary(other.name)["totals"]["total_opening_float"]), 0)


for _name in dir(base.TestShiftAndAccessRegressions):
	if _name.startswith("test_"):
		setattr(TestShiftReports, _name, None)
