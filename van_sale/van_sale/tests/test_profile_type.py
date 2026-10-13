"""Tests for Van Profile types: a Field Sales profile (orders + payments only, no van)
next to the existing Van Sales profile.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_profile_type
"""

import frappe

from van_sale.van_sale.driver import get_app_context
from van_sale.van_sale.inventory import get_driver_stock_dashboard, search_transfer_items
from van_sale.van_sale.sales import create_sales_order, create_sales_return, get_invoice_stock_shortages
from van_sale.van_sale.shift import open_shift, require_open_shift
from van_sale.van_sale.tests import test_shift_and_access as base
from van_sale.van_sale.utils import _capabilities, _driver_cache_key


class TestProfileType(base.TestShiftAndAccessRegressions):
	"""Reuses the shift tests' driver / Van Profile / customer / item fixtures; the
	parent's own tests are blanked out below so they don't run twice."""

	def setUp(self):
		super().setUp()
		self.addCleanup(self._restore_van_profile)
		self.addCleanup(frappe.cache.delete_value, _driver_cache_key(self.driver_user))

	# ─── helpers ───────────────────────────────────────────────────────────

	def _profile(self):
		frappe.set_user("Administrator")
		return frappe.get_doc("Van Profile", self.van_profile)

	def _make_field_sales(self, use_shifts: int = 0, require_open_shift: int = 0):
		doc = self._profile()
		doc.profile_type = "Field Sales"
		doc.use_shifts = use_shifts
		doc.require_open_shift = require_open_shift
		doc.stock_warehouse = self.source_warehouse
		doc.save(ignore_permissions=True)
		frappe.cache.delete_value(_driver_cache_key(self.driver_user))
		return doc

	def _restore_van_profile(self):
		doc = self._profile()
		doc.profile_type = "Van Sales"
		doc.source_warehouse = self.source_warehouse
		doc.van_warehouse = self.van_warehouse
		doc.stock_warehouse = None
		doc.use_shifts = 1
		doc.require_open_shift = 0
		doc.save(ignore_permissions=True)
		frappe.cache.delete_value(_driver_cache_key(self.driver_user))

	# ─── validation ────────────────────────────────────────────────────────

	def test_existing_profiles_default_to_van_sales(self):
		doc = self._profile()
		self.assertEqual(doc.profile_type, "Van Sales")
		self.assertTrue(doc.use_shifts)

	def test_van_sales_requires_both_warehouses(self):
		doc = self._profile()
		doc.van_warehouse = None
		with self.assertRaisesRegex(frappe.ValidationError, "both a Main Warehouse and a Van Warehouse"):
			doc.save(ignore_permissions=True)

	def test_field_sales_clears_warehouses_and_stock_controls(self):
		doc = self._profile()
		doc.profile_type = "Field Sales"
		doc.allow_sale_without_stock = 1
		doc.validate_stock_on_save = 1
		doc.allow_offline_stock_dashboard = 1
		doc.use_shifts = 0
		doc.require_open_shift = 1
		doc.stock_warehouse = self.source_warehouse
		doc.save(ignore_permissions=True)

		doc.reload()
		self.assertIsNone(doc.source_warehouse)
		self.assertIsNone(doc.van_warehouse)
		self.assertEqual(doc.stock_warehouse, self.source_warehouse)
		self.assertFalse(doc.allow_sale_without_stock)
		self.assertFalse(doc.validate_stock_on_save)
		self.assertFalse(doc.allow_offline_stock_dashboard)
		# require_open_shift is meaningless without shifts.
		self.assertFalse(doc.require_open_shift)

	def test_invalid_profile_type_rejected(self):
		doc = self._profile()
		doc.profile_type = "Something Else"
		with self.assertRaisesRegex(frappe.ValidationError, "Profile Type must be one of"):
			doc.save(ignore_permissions=True)

	# ─── capabilities ──────────────────────────────────────────────────────

	def test_capabilities_for_each_type(self):
		van = _capabilities({"profile_type": "Van Sales", "use_shifts": 1, "require_open_shift": 1})
		self.assertTrue(van["can_invoice"] and van["can_deliver"] and van["can_return"])
		self.assertTrue(van["can_load_stock"] and van["can_view_stock"])
		self.assertTrue(van["uses_shifts"] and van["requires_open_shift"])
		self.assertFalse(van["is_field_sales"])

		field = _capabilities({"profile_type": "Field Sales", "use_shifts": 0, "require_open_shift": 1})
		self.assertTrue(field["is_field_sales"])
		for cap in ("can_invoice", "can_deliver", "can_return", "can_load_stock", "can_view_stock", "uses_shifts"):
			self.assertFalse(field[cap], cap)
		# Only meaningful together with shifts.
		self.assertFalse(field["requires_open_shift"])

		field_with_shifts = _capabilities({"profile_type": "Field Sales", "use_shifts": 1, "require_open_shift": 1})
		self.assertTrue(field_with_shifts["uses_shifts"])
		self.assertTrue(field_with_shifts["requires_open_shift"])

		# A manager with no profile keeps the historical behaviour.
		none = _capabilities(None)
		self.assertTrue(none["can_invoice"])
		self.assertFalse(none["can_load_stock"])

	def test_app_context_carries_capabilities(self):
		self._make_field_sales()
		frappe.set_user(self.driver_user)
		ctx = get_app_context()
		self.assertEqual(ctx["driver_config"]["profile_type"], "Field Sales")
		self.assertEqual(ctx["driver_config"]["stock_warehouse"], self.source_warehouse)
		self.assertTrue(ctx["capabilities"]["is_field_sales"])
		self.assertEqual(ctx["capabilities"], ctx["driver_config"]["capabilities"])

	# ─── server guards ─────────────────────────────────────────────────────

	def test_field_sales_can_order_but_not_invoice_return_or_load(self):
		self._make_field_sales()
		frappe.set_user(self.driver_user)

		so = create_sales_order(self.customer_allowed, [{"item_code": self.item_code, "qty": 1, "rate": 10}])
		self.assertTrue(so["name"])
		# No van, so the order carries no warehouse.
		self.assertFalse(frappe.db.get_value("Sales Order", so["name"], "set_warehouse"))

		with self.assertRaisesRegex(frappe.PermissionError, "does not allow you to invoice"):
			get_invoice_stock_shortages(so["name"])
		with self.assertRaisesRegex(frappe.PermissionError, "does not allow you to take returns"):
			create_sales_return(self.customer_allowed, [{"item_code": self.item_code, "qty": 1}])
		with self.assertRaisesRegex(frappe.PermissionError, "does not allow you to view van stock"):
			get_driver_stock_dashboard(force_refresh=1)
		with self.assertRaisesRegex(frappe.PermissionError, "does not allow you to load stock"):
			search_transfer_items("")

	def test_profile_without_shifts_cannot_open_one_and_is_never_blocked(self):
		# require_open_shift is on, but use_shifts is off: the guard must not fire.
		self._make_field_sales(use_shifts=0, require_open_shift=1)
		frappe.set_user(self.driver_user)
		require_open_shift("take an order")  # no throw
		with self.assertRaisesRegex(frappe.PermissionError, "does not allow you to open a shift"):
			open_shift([])

	def test_field_sales_with_shifts_still_enforces_open_shift(self):
		self._make_field_sales(use_shifts=1, require_open_shift=1)
		frappe.db.set_value(
			"Van Shift Opening", {"driver": self.driver_user, "status": "Open"}, "status", "Closed"
		)
		frappe.set_user(self.driver_user)
		with self.assertRaisesRegex(frappe.ValidationError, "Open your shift"):
			require_open_shift("take an order")
		open_shift([{"mode_of_payment": self.cash_mode, "opening_amount": 50}])
		require_open_shift("take an order")  # now passes

	# ─── parent's tests are not re-run here ────────────────────────────────

	def test_driver_cannot_write_sales_order_through_docperms(self):
		pass

	def test_customer_access_respects_allowed_customer_groups(self):
		pass

	def test_driver_can_run_full_shift_and_sales_cycle(self):
		pass
