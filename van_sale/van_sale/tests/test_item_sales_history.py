"""Regression test for get_item_sales_history()'s owner scoping.

Sales Order has no row-level permission hook (unlike the Van Shift/Van Expense
doctypes), so this app-layer owner filter is the only thing stopping one
driver from seeing another driver's customers and negotiated rates for an
item. Managers see everything.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_item_sales_history
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from van_sale.van_sale.sales import create_sales_order, get_item_sales_history, submit_sales_order

TEST_PREFIX = "_Test Van Sale Item History"


def _root_group(doctype: str) -> str | None:
	return frappe.db.get_value(doctype, {"is_group": 1}, "name")


class TestItemSalesHistory(FrappeTestCase):
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

		cls.customer_a = f"{TEST_PREFIX} Customer A"
		cls.customer_b = f"{TEST_PREFIX} Customer B"
		cls.customer_c = f"{TEST_PREFIX} Customer C"
		for cust in (cls.customer_a, cls.customer_b, cls.customer_c):
			if not frappe.db.exists("Customer", cust):
				frappe.get_doc(
					{
						"doctype": "Customer",
						"customer_name": cust,
						"customer_group": customer_group,
						"customer_type": "Company",
					}
				).insert(ignore_permissions=True)

		cls.driver_a = "_test_van_sale_history_driver_a@example.com"
		cls.driver_b = "_test_van_sale_history_driver_b@example.com"
		for user in (cls.driver_a, cls.driver_b):
			if not frappe.db.exists("User", user):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": user,
						"first_name": "Test Van History Driver",
						"user_type": "System User",
						"send_welcome_email": 0,
						"enabled": 1,
					}
				).insert(ignore_permissions=True)

		for suffix, driver in (("A", cls.driver_a), ("B", cls.driver_b)):
			profile_name = f"{TEST_PREFIX} Profile {suffix}"
			if not frappe.db.exists("Van Profile", profile_name):
				frappe.get_doc(
					{
						"doctype": "Van Profile",
						"profile_name": profile_name,
						"company": cls.company,
						"is_active": 1,
						"source_warehouse": warehouses[0].name,
						"van_warehouse": warehouses[1].name,
						"assigned_drivers": [{"driver_user": driver}],
					}
				).insert(ignore_permissions=True)

	def _submit_order_as(self, driver, customer, rate):
		frappe.set_user(driver)
		today = nowdate()
		# Built through the real endpoint: Sales Order writes no longer go through
		# the DocPerm layer, so a direct .insert() as a driver is refused by design.
		so = frappe.get_doc("Sales Order", create_sales_order(customer, [{"item_code": self.item_code, "qty": 1, "rate": rate}])["name"])
		submit_sales_order(so.name)
		return so.name

	def test_driver_only_sees_their_own_sales(self):
		self._submit_order_as(self.driver_a, self.customer_a, 100)
		self._submit_order_as(self.driver_b, self.customer_b, 200)
		self.addCleanup(frappe.set_user, "Administrator")

		frappe.set_user(self.driver_a)
		rows_a = get_item_sales_history(self.item_code)
		customers_seen = {r.customer for r in rows_a}
		self.assertIn(self.customer_a, customers_seen)
		self.assertNotIn(self.customer_b, customers_seen)

		frappe.set_user(self.driver_b)
		rows_b = get_item_sales_history(self.item_code)
		customers_seen_b = {r.customer for r in rows_b}
		self.assertIn(self.customer_b, customers_seen_b)
		self.assertNotIn(self.customer_a, customers_seen_b)

	def test_manager_sees_all_sales(self):
		self._submit_order_as(self.driver_a, self.customer_a, 100)
		self._submit_order_as(self.driver_b, self.customer_b, 200)
		self.addCleanup(frappe.set_user, "Administrator")

		frappe.set_user("Administrator")
		rows = get_item_sales_history(self.item_code)
		customers_seen = {r.customer for r in rows}
		self.assertIn(self.customer_a, customers_seen)
		self.assertIn(self.customer_b, customers_seen)

	def test_customer_filter_narrows_to_that_customer(self):
		"""The catalog is entered after picking a customer, so the normal call
		passes customer= — results (and the rate shown) must be scoped to just
		that customer's own past purchases of the item, not every customer."""
		self._submit_order_as(self.driver_a, self.customer_a, 100)
		self._submit_order_as(self.driver_a, self.customer_c, 150)
		self.addCleanup(frappe.set_user, "Administrator")

		frappe.set_user(self.driver_a)
		rows = get_item_sales_history(self.item_code, customer=self.customer_a)
		self.assertTrue(rows)
		self.assertTrue(all(r.customer == self.customer_a for r in rows))
		self.assertAlmostEqual(rows[0].rate, 100, places=2)
