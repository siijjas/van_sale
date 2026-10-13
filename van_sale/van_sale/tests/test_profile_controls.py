"""Tests for the POS-profile style controls on Van Profile: discount cap, zero rated
items, customer price list, credit sales, returns, customer creation, blind close,
manager-only close and cancelling cash movements.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_profile_controls
"""

import frappe
from frappe.utils import flt

from van_sale.van_sale.cash_movement import cancel_cash_movement, create_cash_movement
from van_sale.van_sale.sales import (
	create_customer, create_sales_invoice, create_sales_order, create_sales_return, submit_sales_order,
)
from van_sale.van_sale.shift import close_shift, get_shift_closing_summary, open_shift
from van_sale.van_sale.tests import test_shift_and_access as base
from van_sale.van_sale.utils import _capabilities, _driver_cache_key, _get_driver_config

CONTROL_FIELDS = (
	"allow_discount_change", "max_discount_percent", "allow_zero_rated_items", "use_customer_price_list",
	"allow_credit_sale", "allow_return", "return_validity_days", "allow_create_customer",
	"allow_duplicate_customer_names", "hide_expected_amount", "allow_driver_close_shift",
	"allow_cancel_cash_movement", "daily_credit_limit", "allow_rate_change",
)


class TestProfileControls(base.TestShiftAndAccessRegressions):
	"""Reuses the shift tests' driver / Van Profile / customer / item fixtures; the
	parent's own tests are blanked out below so they don't run twice."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._original = frappe.db.get_value("Van Profile", self.van_profile, CONTROL_FIELDS, as_dict=True)
		self.addCleanup(self._restore)
		# Every test starts with no open shift (Frappe only rolls back per class).
		frappe.db.set_value(
			"Van Shift Opening", {"driver": ["in", [self.driver_user, "Administrator"]], "status": "Open"}, "status", "Closed"
		)
		self._set(allow_rate_change=1)
		frappe.set_user(self.driver_user)

	def _set(self, **values):
		frappe.set_user("Administrator")
		frappe.db.set_value("Van Profile", self.van_profile, values)
		frappe.cache.delete_value(_driver_cache_key(self.driver_user))
		frappe.set_user(self.driver_user)

	def _restore(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Van Profile", self.van_profile, dict(self._original))
		frappe.cache.delete_value(_driver_cache_key(self.driver_user))

	def _order(self, **kwargs):
		return create_sales_order(self.customer_allowed, [{"item_code": self.item_code, "qty": 1, "rate": 100}], **kwargs)

	# ─── pricing & discounts ───────────────────────────────────────────────

	def test_max_discount_percent_caps_order_discounts(self):
		self._set(allow_discount_change=1, max_discount_percent=10)
		self.assertTrue(self._order(discount_percent=5)["name"])
		self.assertTrue(self._order(discount_amount=10)["name"])
		with self.assertRaisesRegex(frappe.PermissionError, "above the 10%"):
			self._order(discount_percent=15)
		with self.assertRaisesRegex(frappe.PermissionError, "above the 10%"):
			self._order(discount_amount=20)
		self._set(max_discount_percent=0)
		self.assertTrue(self._order(discount_percent=50)["name"])

	def test_zero_rated_lines_refused_unless_allowed(self):
		frappe.set_user("Administrator")
		free_item = f"{base.TEST_PREFIX} Free Item"
		if not frappe.db.exists("Item", free_item):
			frappe.get_doc({
				"doctype": "Item", "item_code": free_item, "item_name": free_item, "item_group": "All Item Groups",
				"stock_uom": "Nos", "is_stock_item": 0, "standard_rate": 0,
			}).insert(ignore_permissions=True)
		self._set(allow_zero_rated_items=0)
		line = [{"item_code": free_item, "qty": 1, "rate": 0}]
		with self.assertRaisesRegex(frappe.PermissionError, "Zero rated"):
			create_sales_order(self.customer_allowed, line)
		self._set(allow_zero_rated_items=1)
		so = frappe.get_doc("Sales Order", create_sales_order(self.customer_allowed, line)["name"])
		self.assertEqual(flt(so.items[0].rate), 0)

	def test_customer_price_list_used_when_enabled(self):
		frappe.set_user("Administrator")
		price_list = f"{base.TEST_PREFIX} Customer PL"
		if not frappe.db.exists("Price List", price_list):
			frappe.get_doc({"doctype": "Price List", "price_list_name": price_list, "selling": 1, "enabled": 1,
				"currency": frappe.get_cached_value("Company", self.company, "default_currency")}).insert(ignore_permissions=True)
		if not frappe.db.exists("Item Price", {"item_code": self.item_code, "price_list": price_list}):
			frappe.get_doc({"doctype": "Item Price", "item_code": self.item_code, "price_list": price_list,
				"price_list_rate": 77, "selling": 1}).insert(ignore_permissions=True)
		frappe.db.set_value("Customer", self.customer_allowed, "default_price_list", price_list)
		self.addCleanup(frappe.db.set_value, "Customer", self.customer_allowed, "default_price_list", None)

		self._set(use_customer_price_list=1)
		so = frappe.get_doc("Sales Order", create_sales_order(self.customer_allowed, [{"item_code": self.item_code, "qty": 1}])["name"])
		self.assertEqual(so.selling_price_list, price_list)
		self.assertAlmostEqual(flt(so.items[0].rate), 77, places=2)

		self._set(use_customer_price_list=0)
		so = frappe.get_doc("Sales Order", self._order()["name"])
		self.assertNotEqual(so.selling_price_list, price_list)

	def test_daily_credit_limit_counts_the_order_once(self):
		# Other tests in this class leave today's drafts behind, and those count too.
		frappe.set_user("Administrator")
		existing = frappe.db.get_value(
			"Sales Order", {"docstatus": ["!=", 2], "transaction_date": frappe.utils.nowdate(), "owner": self.driver_user},
			"sum(grand_total)",
		)
		self._set(daily_credit_limit=flt(existing) + 100)
		so = self._order()["name"]
		# Exactly at the limit must pass: the draft being submitted is not "existing".
		self.assertEqual(frappe.get_doc("Sales Order", submit_sales_order(so)["name"]).docstatus, 1)
		with self.assertRaisesRegex(frappe.PermissionError, "daily credit limit"):
			submit_sales_order(self._order()["name"])

	# ─── sales & returns ───────────────────────────────────────────────────

	def test_credit_sale_switch_requires_payment_at_invoicing(self):
		self._set(allow_credit_sale=0)
		self.assertFalse(_capabilities(_get_driver_config())["can_credit_sale"])
		so = submit_sales_order(self._order()["name"])["name"]
		with self.assertRaisesRegex(frappe.PermissionError, "without collecting payment"):
			create_sales_invoice(so, mark_as_paid=0)
		# Managers are not bound by the switch.
		frappe.set_user("Administrator")
		self.assertTrue(_capabilities(None)["can_credit_sale"])

	def test_return_switch_and_validity_window(self):
		self._set(allow_return=0)
		self.assertFalse(_capabilities(_get_driver_config())["can_return"])
		line = [{"item_code": self.item_code, "qty": 1, "rate": 100}]
		with self.assertRaisesRegex(frappe.PermissionError, "does not allow you to take returns"):
			create_sales_return(self.customer_allowed, line)

		self._set(allow_return=1, return_validity_days=30)
		self.assertTrue(_capabilities(_get_driver_config())["can_return"])
		frappe.set_user("Administrator")
		frappe.db.delete("Sales Invoice", {"customer": self.customer_allowed, "docstatus": 0})
		bought = frappe.db.sql(
			"""select 1 from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent
			where si.docstatus = 1 and si.is_return = 0 and si.customer = %s and sii.item_code = %s
			and si.posting_date >= date_sub(curdate(), interval 30 day) limit 1""",
			(self.customer_allowed, self.item_code),
		)
		frappe.set_user(self.driver_user)
		if not bought:
			with self.assertRaisesRegex(frappe.PermissionError, "has not bought"):
				create_sales_return(self.customer_allowed, line)

	# ─── customers ─────────────────────────────────────────────────────────

	def test_customer_creation_switch_and_duplicate_names(self):
		name = f"{base.TEST_PREFIX} Walk-in"
		frappe.set_user("Administrator")
		for existing in frappe.get_all("Customer", filters={"customer_name": name}, pluck="name"):
			frappe.delete_doc("Customer", existing, force=True, ignore_permissions=True)
		self._set(allow_create_customer=1, allow_duplicate_customer_names=0)
		first = create_customer(name)["name"]
		with self.assertRaisesRegex(frappe.ValidationError, "already exists"):
			create_customer(name)
		self._set(allow_duplicate_customer_names=1)
		self.assertNotEqual(create_customer(name)["name"], first)
		self._set(allow_create_customer=0)
		self.assertFalse(_capabilities(_get_driver_config())["can_create_customer"])
		with self.assertRaisesRegex(frappe.PermissionError, "create customers"):
			create_customer(f"{name} 2")

	# ─── shifts ────────────────────────────────────────────────────────────

	def test_blind_close_hides_expected_amounts_from_the_driver_only(self):
		self._set(hide_expected_amount=1)
		opening = open_shift(balance_details="[]")["name"]
		summary = get_shift_closing_summary()
		self.assertTrue(summary["blind"])
		self.assertIsNone(summary["expected_cash"])
		self.assertTrue(all(row["expected_amount"] is None and row["closing_amount"] == 0 for row in summary["payment_reconciliation"]))

		frappe.set_user("Administrator")
		summary = get_shift_closing_summary(opening)
		self.assertFalse(summary["blind"])
		self.assertIsNotNone(summary["expected_cash"])

		# The closing itself still records the real expected figures.
		frappe.set_user(self.driver_user)
		closing = frappe.get_doc("Van Shift Closing", close_shift(opening_shift=opening, reconciliation="[]")["name"])
		self.assertEqual(closing.docstatus, 1)

	def test_manager_only_close_blocks_the_driver(self):
		self._set(allow_driver_close_shift=0)
		self.assertFalse(_capabilities(_get_driver_config())["can_close_shift"])
		opening = open_shift(balance_details="[]")["name"]
		with self.assertRaisesRegex(frappe.PermissionError, "only lets a manager"):
			get_shift_closing_summary()
		with self.assertRaisesRegex(frappe.PermissionError, "only lets a manager"):
			close_shift(opening_shift=opening, reconciliation="[]")
		frappe.set_user("Administrator")
		closing = frappe.get_doc("Van Shift Closing", close_shift(opening_shift=opening, reconciliation="[]")["name"])
		self.assertEqual(closing.closed_by, "Administrator")

	def test_driver_cancels_own_cash_movement_only_when_allowed(self):
		open_shift(balance_details="[]")
		movement = create_cash_movement("Expense", 5)["name"]
		self._set(allow_cancel_cash_movement=0)
		with self.assertRaisesRegex(frappe.PermissionError, "cancel cash movements"):
			cancel_cash_movement(movement)
		self._set(allow_cancel_cash_movement=1)
		self.assertEqual(cancel_cash_movement(movement)["docstatus"], 2)


for _name in dir(base.TestShiftAndAccessRegressions):
	if _name.startswith("test_"):
		setattr(TestProfileControls, _name, None)
