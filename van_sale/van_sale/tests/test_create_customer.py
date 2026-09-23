"""Regression tests for the driver "quick-add customer" feature.

A driver only enters name + mobile number; customer_group/territory are
auto-assigned from their own Van Profile so the new customer is immediately
visible to them under _validate_customer_access() — never chosen by the driver.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_create_customer
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from van_sale.van_sale.sales import create_customer
from van_sale.van_sale.utils import _validate_customer_access

TEST_PREFIX = "_Test Van Sale New Customer"


def _root_group(doctype: str) -> str | None:
	return frappe.db.get_value(doctype, {"is_group": 1}, "name")


class TestCreateCustomer(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		company_row = frappe.get_all("Company", fields=["name"], limit=1)
		if not company_row:
			raise unittest.SkipTest("No Company configured on this site")
		cls.company = company_row[0].name

		customer_group_root = _root_group("Customer Group")
		if not customer_group_root:
			raise unittest.SkipTest("No root Customer Group on this site")

		warehouses = frappe.get_all(
			"Warehouse", filters={"company": cls.company, "is_group": 0}, fields=["name"], limit=2
		)
		if len(warehouses) < 2:
			raise unittest.SkipTest("Need at least two Warehouses on this company to test against")

		cls.group = f"{TEST_PREFIX} Group"
		if not frappe.db.exists("Customer Group", cls.group):
			frappe.get_doc(
				{
					"doctype": "Customer Group",
					"customer_group_name": cls.group,
					"parent_customer_group": customer_group_root,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		territory_root = _root_group("Territory")
		cls.territory = territory_root

		cls.driver_user = "_test_van_sale_new_customer_driver@example.com"
		if not frappe.db.exists("User", cls.driver_user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": cls.driver_user,
					"first_name": "Test New Customer Driver",
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
					"delivery_route": cls.territory,
					"assigned_drivers": [{"driver_user": cls.driver_user}],
					"allowed_customer_groups": [{"customer_group": cls.group}],
				}
			).insert(ignore_permissions=True)

	def setUp(self):
		frappe.set_user(self.driver_user)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_create_customer_uses_van_profile_group_and_territory(self):
		result = create_customer(f"{TEST_PREFIX} Walk-in", "+974 555 1234")
		self.assertTrue(result["name"])
		doc = frappe.get_doc("Customer", result["name"])
		self.assertEqual(doc.customer_group, self.group)
		if self.territory:
			self.assertEqual(doc.territory, self.territory)
		# ERPNext's own create_primary_contact() should have linked a Contact
		# with this mobile number.
		self.assertEqual(doc.mobile_no, "+974 555 1234")

		# The new customer must be immediately usable by the same driver —
		# this is the entire point of auto-assigning from the Van Profile.
		_validate_customer_access(doc.name)

	def test_create_customer_requires_a_name(self):
		with self.assertRaises(frappe.ValidationError):
			create_customer("   ")
