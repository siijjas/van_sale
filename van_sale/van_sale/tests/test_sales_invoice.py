"""Regression tests for create_sales_invoice()'s mark_as_paid option.

Covers: a Sales Order invoiced normally stays outstanding (existing credit-sale
behaviour, unchanged), while mark_as_paid=1 raises a Payment Entry fully
allocated against the new invoice in the same request, so the invoice shows
Paid immediately and the collection is picked up by shift reconciliation
(which sums Payment Entry documents).

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_sales_invoice
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from van_sale.van_sale.sales import create_sales_invoice, create_sales_order, submit_sales_order

TEST_PREFIX = "_Test Van Sale Invoice"


def _root_group(doctype: str) -> str | None:
	return frappe.db.get_value(doctype, {"is_group": 1}, "name")


class TestSalesInvoiceMarkAsPaid(FrappeTestCase):
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
		if not (item_group and customer_group and uom_row):
			raise unittest.SkipTest("Item Group / Customer Group / UOM setup missing on this site")

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

		cls.driver_user = "_test_van_sale_invoice_driver@example.com"
		if not frappe.db.exists("User", cls.driver_user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": cls.driver_user,
					"first_name": "Test Van Invoice Driver",
					"user_type": "System User",
					"send_welcome_email": 0,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

		warehouses = frappe.get_all(
			"Warehouse", filters={"company": cls.company, "is_group": 0}, fields=["name"], limit=2
		)
		if len(warehouses) < 2:
			raise unittest.SkipTest("Need at least two Warehouses on this company to test against")

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

	def _make_submitted_sales_order(self, rate=100):
		today = nowdate()
		# Built through the real endpoint: Sales Order writes no longer go through
		# the DocPerm layer, so a direct .insert() as a driver is refused by design.
		so = frappe.get_doc("Sales Order", create_sales_order(self.customer, [{"item_code": self.item_code, "qty": 1, "rate": rate}])["name"])
		submit_sales_order(so.name)
		so.reload()
		return so

	def test_invoice_without_mark_as_paid_stays_outstanding(self):
		"""Existing behaviour must be unchanged: no options -> credit sale."""
		so = self._make_submitted_sales_order()
		invoice_name = create_sales_invoice(so.name)
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		self.assertEqual(invoice.docstatus, 1)
		self.assertAlmostEqual(invoice.outstanding_amount, invoice.grand_total, places=2)

	def test_mark_as_paid_creates_fully_allocated_payment_entry(self):
		so = self._make_submitted_sales_order()
		invoice_name = create_sales_invoice(so.name, mark_as_paid=1, mode_of_payment=self.cash_mode)
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		self.assertEqual(invoice.docstatus, 1)
		self.assertAlmostEqual(invoice.outstanding_amount, 0, places=2)

		payment_entries = frappe.get_all(
			"Payment Entry",
			filters={"docstatus": 1, "party": self.customer, "mode_of_payment": self.cash_mode},
			fields=["name", "paid_amount"],
		)
		self.assertTrue(payment_entries, "Expected a submitted Payment Entry for the paid invoice")
		self.assertAlmostEqual(payment_entries[-1].paid_amount, invoice.grand_total, places=2)

		references = frappe.get_all(
			"Payment Entry Reference",
			filters={"parent": payment_entries[-1].name, "reference_name": invoice_name},
			fields=["allocated_amount"],
		)
		self.assertTrue(references, "Payment Entry should reference the new invoice")
		self.assertAlmostEqual(references[0].allocated_amount, invoice.grand_total, places=2)

	def test_mark_as_paid_requires_mode_of_payment(self):
		so = self._make_submitted_sales_order()
		with self.assertRaises(frappe.ValidationError):
			create_sales_invoice(so.name, mark_as_paid=1)

	def test_mark_as_paid_handles_rounding_adjustment(self):
		"""Regression: a rate that produces a rounding_adjustment (e.g. grand_total
		12.5 -> rounded_total 12.0) must not raise "Allocated Amount cannot be
		greater than outstanding amount" — the invoice's own outstanding_amount
		(post-rounding) must be what gets allocated, not the raw grand_total."""
		so = self._make_submitted_sales_order(rate=12.5)
		invoice_name = create_sales_invoice(so.name, mark_as_paid=1, mode_of_payment=self.cash_mode)
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		self.assertEqual(invoice.docstatus, 1)
		self.assertAlmostEqual(invoice.outstanding_amount, 0, places=2)
