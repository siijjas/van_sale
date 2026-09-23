"""Regression test for get_daily_log()'s invoice-aware payment status data.

A Sales Order paid via create_sales_invoice()'s mark_as_paid path is settled
on the Sales Invoice, not as advance_paid against the Sales Order itself — so
get_daily_log() must expose invoiced_total/invoiced_outstanding (summed
correctly across the order's linked invoice(s), not double-counted per line
item) for the frontend to tell a genuinely paid order apart from an unpaid one.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_daily_log
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from van_sale.van_sale.sales import create_sales_invoice, create_sales_order, get_daily_log, submit_sales_order

TEST_PREFIX = "_Test Van Sale Daily Log"


def _root_group(doctype: str) -> str | None:
	return frappe.db.get_value(doctype, {"is_group": 1}, "name")


class TestDailyLogInvoiceStatus(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		company_row = frappe.get_all("Company", fields=["name"], limit=1)
		if not company_row:
			raise unittest.SkipTest("No Company configured on this site")
		cls.company = company_row[0].name

		cash_account = frappe.db.get_value(
			"Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
		)
		if not cash_account:
			raise unittest.SkipTest("No Cash-type Account configured for this company")

		item_group = _root_group("Item Group")
		customer_group = _root_group("Customer Group")
		uom_row = frappe.get_all("UOM", limit=1)
		warehouses = frappe.get_all(
			"Warehouse", filters={"company": cls.company, "is_group": 0}, fields=["name"], limit=2
		)
		if not (item_group and customer_group and uom_row) or len(warehouses) < 2:
			raise unittest.SkipTest("Item Group / Customer Group / UOM / two Warehouses missing on this site")

		cls.cash_mode = f"{TEST_PREFIX} Cash"
		if not frappe.db.exists("Mode of Payment", cls.cash_mode):
			frappe.get_doc(
				{
					"doctype": "Mode of Payment",
					"mode_of_payment": cls.cash_mode,
					"type": "Cash",
					"enabled": 1,
					"accounts": [{"company": cls.company, "default_account": cash_account}],
				}
			).insert(ignore_permissions=True)
		elif not frappe.db.get_value(
			"Mode of Payment Account", {"parent": cls.cash_mode, "company": cls.company}, "name"
		):
			doc = frappe.get_doc("Mode of Payment", cls.cash_mode)
			doc.append("accounts", {"company": cls.company, "default_account": cash_account})
			doc.save(ignore_permissions=True)

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

		cls.driver_user = "_test_van_sale_daily_log_driver@example.com"
		if not frappe.db.exists("User", cls.driver_user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": cls.driver_user,
					"first_name": "Test Van Daily Log Driver",
					"user_type": "System User",
					"send_welcome_email": 0,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("Van Profile", TEST_PREFIX):
			frappe.get_doc(
				{
					"doctype": "Van Profile",
					"profile_name": TEST_PREFIX,
					"company": cls.company,
					"is_active": 1,
					"source_warehouse": warehouses[0].name,
					"van_warehouse": warehouses[1].name,
					"assigned_drivers": [{"driver_user": cls.driver_user}],
					"allowed_payment_modes": [{"mode_of_payment": cls.cash_mode}],
				}
			).insert(ignore_permissions=True)

	def setUp(self):
		frappe.set_user(self.driver_user)
		self.addCleanup(frappe.set_user, "Administrator")

	def _make_submitted_sales_order(self):
		today = nowdate()
		# Built through the real endpoint: Sales Order writes no longer go through
		# the DocPerm layer, so a direct .insert() as a driver is refused by design.
		so = frappe.get_doc("Sales Order", create_sales_order(self.customer, [{"item_code": self.item_code, "qty": 2, "rate": 50}])["name"])
		submit_sales_order(so.name)
		so.reload()
		return so

	def test_order_paid_via_invoice_shows_zero_outstanding(self):
		so = self._make_submitted_sales_order()
		create_sales_invoice(so.name, mark_as_paid=1, mode_of_payment=self.cash_mode)

		rows = {r["name"]: r for r in get_daily_log("Sales Order")}
		self.assertIn(so.name, rows)
		row = rows[so.name]
		self.assertAlmostEqual(row["invoiced_total"], 100, places=2)
		self.assertAlmostEqual(row["invoiced_outstanding"], 0, places=2)
		# advance_paid must NOT be relied on here — it stays 0 for this path.
		self.assertAlmostEqual(row["advance_paid"], 0, places=2)

	def test_order_not_yet_invoiced_has_no_invoice_totals(self):
		so = self._make_submitted_sales_order()
		rows = {r["name"]: r for r in get_daily_log("Sales Order")}
		self.assertIn(so.name, rows)
		row = rows[so.name]
		self.assertEqual(row.get("invoiced_total") or 0, 0)
		self.assertEqual(row.get("invoiced_outstanding") or 0, 0)
