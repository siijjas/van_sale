"""Tests for phase 3 of the shift work: aggregation by the shift's time window,
closing totals and taxes, the variance tolerance flag, draft-order warnings,
manager reopen and the stale-shift notification job.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_shift_window
"""

import frappe
from frappe.utils import add_days, add_to_date, flt, now_datetime, nowdate

from van_sale.van_sale.cash_movement import create_cash_movement
from van_sale.van_sale.doctype.van_shift_closing.van_shift_closing import variance_status
from van_sale.van_sale.finance import create_payment_entry
from van_sale.van_sale.manager_report import get_manager_dashboard, get_period_report
from van_sale.van_sale.sales import create_sales_order, submit_sales_order
from van_sale.van_sale.shift import close_shift, get_active_shift, get_shift_closing_summary, open_shift, reopen_shift
from van_sale.van_sale.shift_report import get_closing_report, get_shift_closings, get_shift_summary
from van_sale.van_sale.tasks import notify_stale_shifts, stale_shifts
from van_sale.van_sale.tests import test_shift_and_access as base
from van_sale.van_sale.utils import _driver_cache_key


class TestShiftWindow(base.TestShiftAndAccessRegressions):
	"""Reuses the shift tests' driver / Van Profile / customer / item fixtures; the
	parent's own tests are blanked out below so they don't run twice."""

	def setUp(self):
		super().setUp()
		frappe.db.set_value(
			"Van Shift Opening", {"driver": ["in", [self.driver_user, "Administrator"]], "status": "Open"}, "status", "Closed"
		)
		self._set_profile(require_open_shift=0, variance_tolerance=0)
		self.addCleanup(self._set_profile, require_open_shift=0, variance_tolerance=0)

	def _set_profile(self, **values):
		frappe.set_user("Administrator")
		frappe.db.set_value("Van Profile", self.van_profile, values)
		frappe.clear_document_cache("Van Profile", self.van_profile)
		frappe.cache.delete_value(_driver_cache_key(self.driver_user))

	def _open(self, float_amount: float = 100) -> str:
		frappe.set_user(self.driver_user)
		return open_shift(
			balance_details=f'[{{"mode_of_payment": "{self.cash_mode}", "opening_amount": {float_amount}}}]'
		)["name"]

	def _order(self, qty: float = 1, rate: float = 10, submit: bool = True) -> str:
		frappe.set_user(self.driver_user)
		name = create_sales_order(self.customer_allowed, [{"item_code": self.item_code, "qty": qty, "rate": rate}])["name"]
		if submit:
			submit_sales_order(name)
		return name

	def _close(self, opening: str, cash_over: float = 0) -> dict:
		frappe.set_user(self.driver_user)
		summary = get_shift_closing_summary(opening)
		counted = [
			{
				"mode_of_payment": r["mode_of_payment"],
				"closing_amount": r["expected_amount"] + (cash_over if r["mode_of_payment"] == self.cash_mode else 0),
			}
			for r in summary["payment_reconciliation"]
		]
		return close_shift(opening_shift=opening, reconciliation=frappe.as_json(counted))

	# ─── window ────────────────────────────────────────────────────────────

	def test_closing_counts_only_what_was_created_inside_the_shift_window(self):
		# With require_open_shift off the driver can sell before opening a shift.
		before = self._order(qty=1, rate=10)
		opening = self._open()
		inside = self._order(qty=2, rate=15)
		create_payment_entry(self.customer_allowed, self.cash_mode, 30, references="[]", sales_order=inside)

		summary = get_shift_closing_summary(opening)
		self.assertAlmostEqual(summary["total_sales"], 30, places=2)
		self.assertAlmostEqual(summary["net_total"], 30, places=2)
		self.assertAlmostEqual(summary["total_quantity"], 2, places=3)
		self.assertAlmostEqual(summary["total_collections"], 30, places=2)
		# Opening float 100 + 30 collected.
		self.assertAlmostEqual(summary["expected_cash"], 130, places=2)
		# The order from before the shift opened is reported, not silently dropped.
		self.assertGreaterEqual(summary["outside_window"]["orders_count"], 1)
		self.assertEqual(summary["period_start"], get_active_shift()["period_start"])

		closed = self._close(opening)
		closing = frappe.get_doc("Van Shift Closing", closed["name"])
		refs = {t.reference_name for t in closing.transactions if t.reference_doctype == "Sales Order"}
		self.assertIn(inside, refs)
		self.assertNotIn(before, refs)
		self.assertAlmostEqual(flt(closing.total_sales), 30, places=2)
		self.assertAlmostEqual(flt(closing.total_quantity), 2, places=3)
		self.assertAlmostEqual(flt(closing.total_taxes), summary["total_taxes"], places=2)
		self.assertEqual(len(closing.taxes), len(summary["taxes"]))
		self.assertTrue(closing.period_end)
		# The opening points back at its closing with the same period end.
		opening_doc = frappe.get_doc("Van Shift Opening", opening)
		self.assertEqual(opening_doc.closing_shift, closing.name)
		self.assertEqual(str(opening_doc.period_end), str(closing.period_end))
		self.assertEqual(opening_doc.status, "Closed")

		# Once claimed by a closing, the "before" order is still outside any window, but a
		# second shift today no longer sees the "inside" order as its own.
		opening2 = self._open()
		summary2 = get_shift_closing_summary(opening2)
		self.assertAlmostEqual(summary2["total_sales"], 0, places=2)
		self.assertNotIn(inside, {t["name"] for t in summary2["draft_orders"]})

		report = get_closing_report(closing.name)
		self.assertAlmostEqual(report["totals"]["net_total"], 30, places=2)
		self.assertIn("taxes", report)
		self.assertEqual(report["totals"]["sales_orders_count"], 1)

	def test_stale_shift_window_runs_to_its_close_not_its_date(self):
		# A shift opened "yesterday" (period_start in the past) and still open: an order
		# made now, the day after, belongs to it because the window ends at closing.
		frappe.set_user("Administrator")
		stale = frappe.get_doc({
			"doctype": "Van Shift Opening",
			"driver": self.driver_user,
			"shift_date": str(add_days(nowdate(), -1)),
			"status": "Open",
			"company": self.company,
			"van_profile": self.van_profile,
			"period_start": add_to_date(now_datetime(), days=-1),
		}).insert(ignore_permissions=True)
		stale.submit()

		# Same-day data from other tests in this run can be inside the window too (it is
		# the driver's unclaimed activity since yesterday), so compare deltas.
		before = get_shift_closing_summary(stale.name)
		self.assertTrue(before["is_stale"])
		order = self._order(qty=1, rate=25)
		summary = get_shift_closing_summary(stale.name)
		self.assertAlmostEqual(summary["total_sales"] - before["total_sales"], 25, places=2)
		closing = frappe.get_doc("Van Shift Closing", self._close(stale.name)["name"])
		self.assertEqual(str(closing.shift_date), str(add_days(nowdate(), -1)))
		self.assertIn(order, {t.reference_name for t in closing.transactions})

	# ─── drafts ────────────────────────────────────────────────────────────

	def test_draft_orders_are_listed_and_counted_but_never_block(self):
		opening = self._open()
		draft = self._order(qty=1, rate=40, submit=False)
		summary = get_shift_closing_summary(opening)
		self.assertEqual([d["name"] for d in summary["draft_orders"]], [draft])
		self.assertAlmostEqual(summary["total_sales"], 0, places=2)
		self.assertEqual([d["name"] for d in get_shift_summary(opening)["draft_orders"]], [draft])

		closed = self._close(opening)
		self.assertEqual(closed["draft_orders_count"], 1)
		self.assertEqual(frappe.db.get_value("Van Shift Closing", closed["name"], "draft_orders_count"), 1)
		self.assertEqual(frappe.db.get_value("Sales Order", draft, "docstatus"), 0)
		self.assertEqual(get_closing_report(closed["name"])["totals"]["draft_orders_count"], 1)

		frappe.set_user("Administrator")
		alerts = get_manager_dashboard()["alerts"]
		self.assertIn(("draft_orders", closed["name"]), {(a["kind"], a["reference"]) for a in alerts})

	# ─── variance ──────────────────────────────────────────────────────────

	def test_variance_status_is_flag_only_against_the_profile_tolerance(self):
		self.assertEqual(variance_status(0, 0), "Balanced")
		self.assertEqual(variance_status(0.004, 0), "Balanced")
		self.assertEqual(variance_status(-5, 10), "Within Tolerance")
		self.assertEqual(variance_status(10, 10), "Within Tolerance")
		self.assertEqual(variance_status(10.01, 10), "Exceeds Tolerance")
		self.assertEqual(variance_status(1, 0), "Exceeds Tolerance")

		self._set_profile(variance_tolerance=10)
		opening = self._open()
		self.assertAlmostEqual(get_shift_closing_summary(opening)["variance_tolerance"], 10, places=2)
		closed = self._close(opening, cash_over=-5)
		self.assertEqual(closed["variance_status"], "Within Tolerance")
		self.assertAlmostEqual(closed["variance_tolerance"], 10, places=2)
		within = closed["name"]

		frappe.set_user("Administrator")
		dashboard = get_manager_dashboard()
		van = next(v for v in dashboard["vans"] if v["driver"] == self.driver_user)
		self.assertEqual(van["variance_status"], "Within Tolerance")
		self.assertNotIn(("variance", within), {(a["kind"], a["reference"]) for a in dashboard["alerts"]})

		# Beyond tolerance: still closes, but flagged everywhere a manager looks.
		opening = self._open()
		closed = self._close(opening, cash_over=-25)
		self.assertEqual(closed["variance_status"], "Exceeds Tolerance")
		frappe.set_user("Administrator")
		dashboard = get_manager_dashboard()
		alert = next(a for a in dashboard["alerts"] if a["kind"] == "variance" and a["reference"] == closed["name"])
		self.assertEqual(alert["level"], "danger")
		self.assertIn("tolerance", alert["body"])
		row = next(r for r in get_period_report(nowdate(), nowdate(), driver=self.driver_user)["shifts"] if r["name"] == closed["name"])
		self.assertEqual(row["variance_status"], "Exceeds Tolerance")
		totals = get_period_report(nowdate(), nowdate(), driver=self.driver_user)["totals"]
		self.assertGreaterEqual(totals["flagged_shifts"], 1)
		self.assertGreater(totals["variance_shifts"], totals["flagged_shifts"] - 1)
		self.assertEqual(get_closing_report(closed["name"])["totals"]["variance_status"], "Exceeds Tolerance")
		statuses = {row.name: row.variance_status for row in get_shift_closings()}
		self.assertEqual(statuses[within], "Within Tolerance")
		self.assertEqual(statuses[closed["name"]], "Exceeds Tolerance")

	# ─── reopen ────────────────────────────────────────────────────────────

	def test_manager_can_reopen_a_closed_shift_and_the_window_continues(self):
		opening = self._open()
		self._order(qty=1, rate=10)
		closed = self._close(opening)["name"]
		self.assertIsNone(get_active_shift())

		with self.assertRaises(frappe.PermissionError):
			reopen_shift(closed)

		frappe.set_user("Administrator")
		reopened = reopen_shift(closed)
		self.assertEqual(reopened["name"], opening)
		self.assertEqual(reopened["status"], "Open")
		self.assertIsNone(reopened["period_end"])
		self.assertIsNone(reopened["closing_shift"])
		self.assertEqual(frappe.db.get_value("Van Shift Closing", closed, "docstatus"), 2)

		# The driver is back on the same shift; more activity joins it, and a second
		# closing covers everything from the original opening to now.
		frappe.set_user(self.driver_user)
		self.assertEqual(get_active_shift()["name"], opening)
		self._order(qty=1, rate=5)
		create_cash_movement("Expense", 2)
		summary = get_shift_closing_summary(opening)
		self.assertAlmostEqual(summary["total_sales"], 15, places=2)
		closing2 = frappe.get_doc("Van Shift Closing", self._close(opening)["name"])
		self.assertAlmostEqual(flt(closing2.total_sales), 15, places=2)
		self.assertAlmostEqual(flt(closing2.total_expenses), 2, places=2)
		self.assertEqual(frappe.db.get_value("Van Shift Opening", opening, "closing_shift"), closing2.name)

		# Cannot reopen it while the driver has another shift open.
		other = self._open()
		frappe.set_user("Administrator")
		with self.assertRaisesRegex(frappe.ValidationError, "already has an open shift"):
			reopen_shift(closing2.name)
		# ... nor reopen a cancelled closing.
		with self.assertRaises(frappe.ValidationError):
			reopen_shift(closed)
		frappe.db.set_value("Van Shift Opening", other, "status", "Closed")

	# ─── scheduler ─────────────────────────────────────────────────────────

	def test_daily_job_notifies_managers_of_stale_shifts(self):
		frappe.set_user("Administrator")
		manager = "_test_van_sale_manager@example.com"
		if not frappe.db.exists("User", manager):
			frappe.get_doc({
				"doctype": "User",
				"email": manager,
				"first_name": "Test Van Manager",
				"user_type": "System User",
				"send_welcome_email": 0,
				"enabled": 1,
				"roles": [{"role": "Sales Manager"}],
			}).insert(ignore_permissions=True)

		self.assertNotIn(self.driver_user, {s["driver"] for s in stale_shifts()})
		stale = frappe.get_doc({
			"doctype": "Van Shift Opening",
			"driver": self.driver_user,
			"shift_date": str(add_days(nowdate(), -2)),
			"status": "Open",
			"company": self.company,
			"van_profile": self.van_profile,
			"period_start": add_to_date(now_datetime(), days=-2),
		}).insert(ignore_permissions=True)
		stale.submit()
		self.addCleanup(frappe.db.set_value, "Van Shift Opening", stale.name, "status", "Closed")

		logs_before = frappe.db.count("Notification Log", {"for_user": manager, "document_type": "Van Shift Opening"})
		result = notify_stale_shifts()
		mine = next(s for s in result["shifts"] if s["name"] == stale.name)
		self.assertEqual(mine["days_open"], 2)
		self.assertIn(manager, result["notified"])
		self.assertNotIn("Administrator", result["notified"])
		self.assertEqual(
			frappe.db.count("Notification Log", {"for_user": manager, "document_type": "Van Shift Opening"}),
			logs_before + 1,
		)
		log = frappe.get_last_doc("Notification Log", filters={"for_user": manager, "document_type": "Van Shift Opening"})
		self.assertIn(stale.name, log.email_content)
		self.assertEqual(log.type, "Alert")


for _name in dir(base.TestShiftAndAccessRegressions):
	if _name.startswith("test_"):
		setattr(TestShiftWindow, _name, None)
