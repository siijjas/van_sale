"""Tests for forgotten (stale) shifts, managers closing a driver's shift, and the
Van Profile's require_open_shift setting.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_shift_lifecycle
"""

import frappe
from frappe.utils import add_days, now_datetime, nowdate

from van_sale.van_sale.finance import submit_route_expense
from van_sale.van_sale.sales import create_sales_order
from van_sale.van_sale.shift import close_shift, get_active_shift, get_shift_closing_summary, open_shift
from van_sale.van_sale.tests import test_shift_and_access as base
from van_sale.van_sale.utils import _driver_cache_key


class TestShiftLifecycle(base.TestShiftAndAccessRegressions):
	"""Reuses the shift tests' driver / Van Profile / customer / item fixtures; the
	parent's own tests are blanked out below so they don't run twice."""

	def setUp(self):
		super().setUp()
		# Frappe only rolls back at the end of the class, so shifts opened by an earlier
		# test are still open here. Every test starts with none.
		frappe.db.set_value(
			"Van Shift Opening", {"driver": ["in", [self.driver_user, "Administrator"]], "status": "Open"}, "status", "Closed"
		)

	def _insert_opening(self, driver: str, shift_date: str) -> str:
		frappe.set_user("Administrator")
		doc = frappe.get_doc({
			"doctype": "Van Shift Opening",
			"driver": driver,
			"shift_date": shift_date,
			"status": "Open",
			"company": self.company,
			"van_profile": self.van_profile,
			"period_start": now_datetime(),
		})
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc.name

	def _set_require_open_shift(self, value: int):
		frappe.set_user("Administrator")
		frappe.db.set_value("Van Profile", self.van_profile, "require_open_shift", value)
		frappe.cache.delete_value(_driver_cache_key(self.driver_user))
		# The cached driver config outlives the test's DB rollback.
		self.addCleanup(frappe.cache.delete_value, _driver_cache_key(self.driver_user))

	def test_stale_shift_blocks_new_shift_and_closes_as_its_own_day(self):
		yesterday = str(add_days(nowdate(), -1))
		stale = self._insert_opening(self.driver_user, yesterday)

		frappe.set_user(self.driver_user)
		active = get_active_shift()
		self.assertEqual(active["name"], stale)
		self.assertTrue(active["is_stale"])

		with self.assertRaisesRegex(frappe.ValidationError, "unclosed shift"):
			open_shift(balance_details="[]")

		summary = get_shift_closing_summary()
		self.assertEqual(summary["opening_shift"], stale)
		self.assertEqual(summary["shift_date"], yesterday)
		self.assertTrue(summary["is_stale"])

		closing = frappe.get_doc("Van Shift Closing", close_shift(opening_shift=stale, reconciliation="[]")["name"])
		self.assertEqual(str(closing.shift_date), yesterday)
		self.assertEqual(closing.driver, self.driver_user)
		self.assertFalse(closing.closed_by)

		# Now today's shift can open.
		self.assertFalse(open_shift(balance_details="[]")["is_stale"])

	def test_manager_can_close_a_drivers_shift_but_drivers_cannot_close_others(self):
		frappe.set_user(self.driver_user)
		opening = open_shift(balance_details="[]")["name"]

		frappe.set_user("Administrator")
		summary = get_shift_closing_summary(opening)
		self.assertEqual(summary["driver"], self.driver_user)
		closing = frappe.get_doc("Van Shift Closing", close_shift(opening_shift=opening, reconciliation="[]")["name"])
		self.assertEqual(closing.driver, self.driver_user)
		self.assertEqual(closing.closed_by, "Administrator")

		other = self._insert_opening("Administrator", nowdate())
		frappe.set_user(self.driver_user)
		with self.assertRaises(frappe.PermissionError):
			get_shift_closing_summary(other)
		with self.assertRaises(frappe.PermissionError):
			close_shift(opening_shift=other, reconciliation="[]")

	def test_require_open_shift_blocks_selling_until_todays_shift_is_open(self):
		self._set_require_open_shift(1)
		line = [{"item_code": self.item_code, "qty": 1, "rate": 10}]

		frappe.set_user(self.driver_user)
		with self.assertRaisesRegex(frappe.ValidationError, "Open your shift"):
			create_sales_order(self.customer_allowed, line)
		with self.assertRaisesRegex(frappe.ValidationError, "Open your shift"):
			submit_route_expense("Fuel", 5)

		# A stale shift doesn't count: it has to be closed first.
		stale = self._insert_opening(self.driver_user, str(add_days(nowdate(), -1)))
		frappe.set_user(self.driver_user)
		with self.assertRaisesRegex(frappe.ValidationError, "Close your shift from"):
			create_sales_order(self.customer_allowed, line)

		close_shift(opening_shift=stale, reconciliation="[]")
		open_shift(balance_details="[]")
		self.assertTrue(create_sales_order(self.customer_allowed, line)["name"])
		self.assertTrue(submit_route_expense("Fuel", 5))

	def test_selling_is_unrestricted_when_the_setting_is_off(self):
		self._set_require_open_shift(0)
		frappe.set_user(self.driver_user)
		self.assertIsNone(get_active_shift())
		self.assertTrue(
			create_sales_order(self.customer_allowed, [{"item_code": self.item_code, "qty": 1, "rate": 10}])["name"]
		)


for _name in dir(base.TestShiftAndAccessRegressions):
	if _name.startswith("test_"):
		setattr(TestShiftLifecycle, _name, None)
