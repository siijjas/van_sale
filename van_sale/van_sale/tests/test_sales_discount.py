"""Regression tests for the Sales Order discount feature and its permission gate.

A driver applies an overall discount in the cart (additional_discount_percentage)
before submitting the Sales Order. submit_sales_order() must reject it outright
when the driver's Van Profile has allow_discount_change disabled, and apply it
correctly (via ERPNext's own calculate_taxes_and_totals()) when allowed.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_sales_discount
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from van_sale.van_sale.sales import create_sales_order, submit_sales_order

TEST_PREFIX = "_Test Van Sale Discount"


def _root_group(doctype: str) -> str | None:
	return frappe.db.get_value(doctype, {"is_group": 1}, "name")


class TestSalesOrderDiscount(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		company_row = frappe.get_all("Company", fields=["name"], limit=1)
		if not company_row:
			raise unittest.SkipTest("No Company configured on this site")
		cls.company = company_row[0].name

		item_group = _root_group("Item Group")
		customer_group = _root_group("Customer Group")
		uom_row = frappe.get_all("UOM", limit=1)
		warehouses = frappe.get_all(
			"Warehouse", filters={"company": cls.company, "is_group": 0}, fields=["name"], limit=2
		)
		if not (item_group and customer_group and uom_row) or len(warehouses) < 2:
			raise unittest.SkipTest("Item Group / Customer Group / UOM / two Warehouses missing on this site")

		cls.customer = f"{TEST_PREFIX} Customer"
		if not frappe.db.exists("Customer", cls.customer):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": cls.customer,
					"customer_group": customer_group,
					"customer_type": "Company",
				}
			).insert(ignore_permissions=True)

		cls.item_code = f"{TEST_PREFIX} Item"
		if not frappe.db.exists("Item", cls.item_code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": cls.item_code,
					"item_name": cls.item_code,
					"item_group": item_group,
					"stock_uom": uom_row[0].name,
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)

		# Two drivers on two profiles: one with discounts disallowed (the default),
		# one with them explicitly allowed.
		cls.driver_no_discount = "_test_van_sale_discount_denied@example.com"
		cls.driver_with_discount = "_test_van_sale_discount_allowed@example.com"
		for user in (cls.driver_no_discount, cls.driver_with_discount):
			if not frappe.db.exists("User", user):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": user,
						"first_name": "Test Van Discount Driver",
						"user_type": "System User",
						"send_welcome_email": 0,
						"enabled": 1,
					}
				).insert(ignore_permissions=True)

		if not frappe.db.exists("Van Profile", f"{TEST_PREFIX} Denied"):
			frappe.get_doc(
				{
					"doctype": "Van Profile",
					"profile_name": f"{TEST_PREFIX} Denied",
					"company": cls.company,
					"is_active": 1,
					"source_warehouse": warehouses[0].name,
					"van_warehouse": warehouses[1].name,
					"allow_discount_change": 0,
					"assigned_drivers": [{"driver_user": cls.driver_no_discount}],
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("Van Profile", f"{TEST_PREFIX} Allowed"):
			frappe.get_doc(
				{
					"doctype": "Van Profile",
					"profile_name": f"{TEST_PREFIX} Allowed",
					"company": cls.company,
					"is_active": 1,
					"source_warehouse": warehouses[0].name,
					"van_warehouse": warehouses[1].name,
					"allow_discount_change": 1,
					"assigned_drivers": [{"driver_user": cls.driver_with_discount}],
				}
			).insert(ignore_permissions=True)

	def _make_draft_sales_order(self, discount_percent=0, discount_amount=0):
		today = nowdate()
		# Built through the real endpoint: Sales Order writes no longer go through
		# the DocPerm layer, so a direct .insert() as a driver is refused by design.
		so = frappe.get_doc("Sales Order", create_sales_order(
			self.customer,
			[{"item_code": self.item_code, "qty": 1, "rate": 100}],
			discount_percent=discount_percent,
			discount_amount=discount_amount,
		)["name"])
		return so

	def test_discount_blocked_when_profile_disallows(self):
		"""Rejected when the draft is SAVED, not only at submit: the guard now runs
		inside create_sales_order() too, so a forbidden discount never reaches a
		draft in the first place."""
		frappe.set_user(self.driver_no_discount)
		self.addCleanup(frappe.set_user, "Administrator")
		with self.assertRaises(frappe.PermissionError):
			self._make_draft_sales_order(discount_percent=10)

	def test_order_without_discount_still_submits_when_disallowed(self):
		"""The check must only fire when a discount is actually set — plain
		orders must keep working for drivers who can't apply discounts."""
		frappe.set_user(self.driver_no_discount)
		self.addCleanup(frappe.set_user, "Administrator")
		so = self._make_draft_sales_order(discount_percent=0)
		submit_sales_order(so.name)
		so.reload()
		self.assertEqual(so.docstatus, 1)

	def test_discount_applied_when_profile_allows(self):
		frappe.set_user(self.driver_with_discount)
		self.addCleanup(frappe.set_user, "Administrator")
		so = self._make_draft_sales_order(discount_percent=10)
		submit_sales_order(so.name)
		so.reload()
		self.assertEqual(so.docstatus, 1)
		# 1 x 100 with a 10% discount on grand total -> 90.
		self.assertAlmostEqual(so.grand_total, 90, places=2)

	def test_flat_amount_discount_applied_when_profile_allows(self):
		"""additional_discount_percentage=0 with discount_amount set directly
		must be preserved as-is (ERPNext's own set_discount_amount() only
		recomputes discount_amount from the percentage when it's nonzero)."""
		frappe.set_user(self.driver_with_discount)
		self.addCleanup(frappe.set_user, "Administrator")
		so = self._make_draft_sales_order(discount_percent=0, discount_amount=15)
		submit_sales_order(so.name)
		so.reload()
		self.assertEqual(so.docstatus, 1)
		self.assertAlmostEqual(so.grand_total, 85, places=2)

	def test_flat_amount_discount_blocked_when_profile_disallows(self):
		"""As above — a flat discount is refused at save time as well."""
		frappe.set_user(self.driver_no_discount)
		self.addCleanup(frappe.set_user, "Administrator")
		with self.assertRaises(frappe.PermissionError):
			self._make_draft_sales_order(discount_percent=0, discount_amount=15)
