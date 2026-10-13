"""Tests for Van Cash Movement: expenses and deposits out of the shift's cash drawer,
posted to Journal Entries and deducted from the closing's expected cash.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_cash_movement
"""

import frappe
from frappe.utils import flt

from van_sale.van_sale.cash_movement import (
	cancel_cash_movement,
	create_cash_movement,
	get_cash_movement_context,
	get_shift_cash_movements,
)
from van_sale.van_sale.shift import close_shift, get_shift_closing_summary, open_shift
from van_sale.van_sale.shift_report import get_closing_report, get_shift_summary
from van_sale.van_sale.tests import test_shift_and_access as base
from van_sale.van_sale.utils import _driver_cache_key


class TestCashMovement(base.TestShiftAndAccessRegressions):
	"""Reuses the shift tests' driver / Van Profile / customer / item fixtures; the
	parent's own tests are blanked out below so they don't run twice."""

	def setUp(self):
		super().setUp()
		frappe.db.set_value(
			"Van Shift Opening", {"driver": self.driver_user, "status": "Open"}, "status", "Closed"
		)
		self.addCleanup(self._reset_profile)
		self.addCleanup(frappe.cache.delete_value, _driver_cache_key(self.driver_user))

	def _reset_profile(self):
		frappe.set_user("Administrator")
		frappe.db.set_value(
			"Van Profile",
			self.van_profile,
			{
				"allow_expense": 1,
				"allow_cash_deposit": 1,
				"cash_movement_max_amount": 0,
				"require_cash_movement_remarks": 0,
			},
		)
		frappe.db.delete("Van Profile Expense Account", {"parent": self.van_profile})
		frappe.clear_document_cache("Van Profile", self.van_profile)
		frappe.cache.delete_value(_driver_cache_key(self.driver_user))

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

	def _je_lines(self, journal_entry: str) -> dict[str, tuple[float, float]]:
		return {
			row.account: (flt(row.debit), flt(row.credit))
			for row in frappe.get_all(
				"Journal Entry Account",
				filters={"parent": journal_entry, "parenttype": "Journal Entry"},
				fields=["account", "debit", "credit"],
			)
		}

	# ─── posting ───────────────────────────────────────────────────────────

	def test_expense_posts_journal_entry_and_reduces_expected_cash(self):
		opening = self._open(100)
		before = get_shift_closing_summary()

		movement = create_cash_movement("Expense", 12.5, against_name="Shell 42", remarks="Fuel")
		self.assertEqual(movement["opening_shift"], opening)
		self.assertEqual(movement["source_account"], self.cash_account)
		self.assertEqual(movement["target_account"], self.expense_account)
		self.assertEqual(frappe.db.get_value("Journal Entry", movement["journal_entry"], "docstatus"), 1)
		self.assertEqual(
			self._je_lines(movement["journal_entry"]),
			{self.expense_account: (12.5, 0.0), self.cash_account: (0.0, 12.5)},
		)

		after = get_shift_closing_summary()
		self.assertAlmostEqual(after["total_expenses"] - before["total_expenses"], 12.5, places=2)
		self.assertAlmostEqual(after["expected_cash"] - before["expected_cash"], -12.5, places=2)

	def test_deposit_moves_cash_to_back_office_and_reduces_expected_cash(self):
		self._open(100)
		before = get_shift_closing_summary()

		movement = create_cash_movement("Deposit", 40, against_name="Head office")
		self.assertIsNone(movement["expense_account"])
		self.assertEqual(movement["target_account"], self.ho_cash_account)
		self.assertEqual(
			self._je_lines(movement["journal_entry"]),
			{self.ho_cash_account: (40.0, 0.0), self.cash_account: (0.0, 40.0)},
		)

		after = get_shift_closing_summary()
		self.assertAlmostEqual(after["total_deposits"] - before["total_deposits"], 40, places=2)
		# Deposits don't count as expenses, but the drawer still holds less.
		self.assertAlmostEqual(after["total_expenses"], before["total_expenses"], places=2)
		self.assertAlmostEqual(after["expected_cash"] - before["expected_cash"], -40, places=2)

	def test_closing_freezes_movements_and_report_lists_them(self):
		opening = self._open(100)
		expense = create_cash_movement("Expense", 5, remarks="Tolls")
		deposit = create_cash_movement("Deposit", 30)

		summary = get_shift_summary()
		self.assertIn(expense["name"], [e["name"] for e in summary["expenses"]])
		self.assertIn(deposit["name"], [d["name"] for d in summary["deposits"]])
		self.assertEqual(summary["totals"]["deposits_count"], 1)

		closed = close_shift(opening_shift=opening, reconciliation="[]")
		closing = frappe.get_doc("Van Shift Closing", closed["name"])
		self.assertAlmostEqual(flt(closing.total_deposits), 30, places=2)
		refs = {(t.reference_doctype, t.reference_name) for t in closing.transactions}
		self.assertIn(("Van Cash Movement", expense["name"]), refs)
		self.assertIn(("Van Cash Movement", deposit["name"]), refs)

		report = get_closing_report(closed["name"])
		self.assertEqual(report["report_type"], "closing")
		self.assertAlmostEqual(report["totals"]["total_deposits"], 30, places=2)
		self.assertEqual([d["journal_entry"] for d in report["deposits"]], [deposit["journal_entry"]])

	# ─── rules ─────────────────────────────────────────────────────────────

	def test_needs_an_open_shift(self):
		frappe.set_user(self.driver_user)
		with self.assertRaisesRegex(frappe.ValidationError, "Open your shift"):
			create_cash_movement("Expense", 5)

	def test_profile_rules_are_enforced(self):
		self._open()
		with self.assertRaises(frappe.ValidationError):
			create_cash_movement("Expense", 0)
		with self.assertRaises(frappe.ValidationError):
			create_cash_movement("Refund", 5)

		self._set_profile(allow_cash_deposit=0)
		frappe.set_user(self.driver_user)
		with self.assertRaisesRegex(frappe.PermissionError, "deposits are not enabled"):
			create_cash_movement("Deposit", 5)
		ctx = get_cash_movement_context()
		self.assertFalse(ctx["allow_cash_deposit"])
		self.assertTrue(ctx["allow_expense"])

		self._set_profile(allow_cash_deposit=1, cash_movement_max_amount=10)
		frappe.set_user(self.driver_user)
		with self.assertRaisesRegex(frappe.ValidationError, "exceeds the maximum"):
			create_cash_movement("Expense", 10.01)
		self.assertTrue(create_cash_movement("Expense", 10)["name"])

		self._set_profile(cash_movement_max_amount=0, require_cash_movement_remarks=1)
		frappe.set_user(self.driver_user)
		with self.assertRaisesRegex(frappe.ValidationError, "Remarks are required"):
			create_cash_movement("Expense", 5)
		self.assertTrue(create_cash_movement("Expense", 5, remarks="ok")["name"])

	def test_allowed_expense_accounts_restrict_the_choice(self):
		other = frappe.db.get_value(
			"Account",
			{
				"company": self.company,
				"root_type": "Expense",
				"is_group": 0,
				"disabled": 0,
				"name": ["!=", self.expense_account],
			},
			"name",
		)
		if not other:
			self.skipTest("Need two expense accounts")
		frappe.set_user("Administrator")
		profile = frappe.get_doc("Van Profile", self.van_profile)
		profile.append("allowed_expense_accounts", {"account": self.expense_account})
		profile.save(ignore_permissions=True)
		frappe.cache.delete_value(_driver_cache_key(self.driver_user))

		self._open()
		ctx = get_cash_movement_context()
		self.assertEqual([a["name"] for a in ctx["expense_accounts"]], [self.expense_account])
		with self.assertRaisesRegex(frappe.ValidationError, "is not allowed on your profile"):
			create_cash_movement("Expense", 5, expense_account=other)
		self.assertTrue(create_cash_movement("Expense", 5, expense_account=self.expense_account)["name"])

	def test_non_expense_account_is_rejected(self):
		self._open()
		with self.assertRaisesRegex(frappe.ValidationError, "is not an expense account"):
			create_cash_movement("Expense", 5, expense_account=self.ho_cash_account)

	# ─── access ────────────────────────────────────────────────────────────

	def test_driver_sees_own_shift_only_and_cannot_cancel(self):
		self._open()
		movement = create_cash_movement("Expense", 5)
		self.assertEqual([m["name"] for m in get_shift_cash_movements()], [movement["name"]])

		with self.assertRaises(frappe.PermissionError):
			cancel_cash_movement(movement["name"])

		# Another driver's shift is off limits.
		frappe.set_user("Administrator")
		other_opening = frappe.get_doc({
			"doctype": "Van Shift Opening",
			"driver": "Administrator",
			"shift_date": frappe.utils.nowdate(),
			"status": "Open",
			"company": self.company,
			"period_start": frappe.utils.now_datetime(),
		}).insert(ignore_permissions=True)
		other_opening.submit()
		self.addCleanup(frappe.db.set_value, "Van Shift Opening", other_opening.name, "status", "Closed")
		frappe.set_user(self.driver_user)
		with self.assertRaises(frappe.PermissionError):
			get_shift_cash_movements(other_opening.name)

	def test_manager_cancel_reverses_journal_entry_while_shift_is_open(self):
		opening = self._open(100)
		movement = create_cash_movement("Expense", 8)
		before = get_shift_closing_summary()["expected_cash"]

		frappe.set_user("Administrator")
		cancel_cash_movement(movement["name"])
		self.assertEqual(frappe.db.get_value("Van Cash Movement", movement["name"], "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Journal Entry", movement["journal_entry"], "docstatus"), 2)

		frappe.set_user(self.driver_user)
		self.assertAlmostEqual(get_shift_closing_summary()["expected_cash"] - before, 8, places=2)
		self.assertEqual(get_shift_cash_movements(), [])

		# Once the shift is closed the movement is frozen into it.
		kept = create_cash_movement("Deposit", 3)
		close_shift(opening_shift=opening, reconciliation="[]")
		frappe.set_user("Administrator")
		with self.assertRaisesRegex(frappe.ValidationError, "already closed"):
			cancel_cash_movement(kept["name"])


for _name in dir(base.TestShiftAndAccessRegressions):
	if _name.startswith("test_"):
		setattr(TestCashMovement, _name, None)
