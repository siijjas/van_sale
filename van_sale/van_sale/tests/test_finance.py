"""Regression test for create_payment_entry()'s Sales Order advance-payment path.

Bug: the "link to Sales Order for advance payment" reference row never set
outstanding_amount, leaving it at the Currency field default of 0. ERPNext's
own Payment Entry row validation then rejects ANY positive allocated_amount
against it with "Allocated Amount cannot be greater than outstanding amount" —
i.e. advance payments against a Sales Order always failed.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_finance
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from van_sale.van_sale.finance import create_payment_entry
from van_sale.van_sale.sales import create_sales_order, submit_sales_order

TEST_PREFIX = "_Test Van Sale Finance"


def _root_group(doctype: str) -> str | None:
	return frappe.db.get_value(doctype, {"is_group": 1}, "name")


class TestSalesOrderAdvancePayment(FrappeTestCase):
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

		cls.driver_user = "_test_van_sale_finance_driver@example.com"
		if not frappe.db.exists("User", cls.driver_user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": cls.driver_user,
					"first_name": "Test Van Finance Driver",
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
		so = frappe.get_doc("Sales Order", create_sales_order(self.customer, [{"item_code": self.item_code, "qty": 1, "rate": 100}])["name"])
		submit_sales_order(so.name)
		so.reload()
		return so

	def test_full_advance_against_sales_order_succeeds(self):
		so = self._make_submitted_sales_order()
		pe_name = create_payment_entry(
			customer=self.customer,
			mode_of_payment=self.cash_mode,
			paid_amount=so.grand_total,
			references="[]",
			sales_order=so.name,
		)
		pe = frappe.get_doc("Payment Entry", pe_name)
		self.assertEqual(pe.docstatus, 1)
		so_refs = [r for r in pe.references if r.reference_doctype == "Sales Order"]
		self.assertEqual(len(so_refs), 1)
		self.assertAlmostEqual(so_refs[0].allocated_amount, so.grand_total, places=2)

		# The submitted Payment Entry should have updated the Sales Order's own
		# advance_paid to reflect the allocation (the real, functional proof
		# that the reference row was accepted and applied, not just present).
		so.reload()
		self.assertAlmostEqual(so.advance_paid, so.grand_total, places=2)

	def test_advance_over_outstanding_is_clamped_not_rejected(self):
		"""Paying more than a Sales Order's outstanding is a normal advance in
		ERPNext (e.g. a driver collecting a round cash amount, or a rounding-
		adjustment mismatch between grand_total and rounded_total) — it must not
		be rejected outright. The excess should land as unallocated_amount on
		the Payment Entry (a standard customer credit), while the Sales Order
		reference itself is still capped at its real outstanding amount, since
		Payment Entry's own row validation enforces allocated <= outstanding no
		matter what we pass in."""
		so = self._make_submitted_sales_order()
		overpay_by = 50
		pe_name = create_payment_entry(
			customer=self.customer,
			mode_of_payment=self.cash_mode,
			paid_amount=so.grand_total + overpay_by,
			references="[]",
			sales_order=so.name,
		)
		pe = frappe.get_doc("Payment Entry", pe_name)
		self.assertEqual(pe.docstatus, 1)
		so_refs = [r for r in pe.references if r.reference_doctype == "Sales Order"]
		self.assertEqual(len(so_refs), 1)
		self.assertAlmostEqual(so_refs[0].allocated_amount, so.grand_total, places=2)
		self.assertAlmostEqual(pe.unallocated_amount, overpay_by, places=2)
