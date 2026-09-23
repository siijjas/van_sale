"""Regression tests for the Van Sale driver permission model.

These cover four real bugs found (and fixed) in production, all of which
manifested only when exercised as an actual "Van Sales Driver" user hitting
Frappe's real permission engine — none of them would be caught by mocking
`frappe` out, since the bug was in how Frappe's own permission checks reacted
to this app's role/DocPerm/has_permission configuration:

1. Sales Order was missing the "submit" role permission for Van Sales Driver,
   so `submit_sales_order()` failed even though create/write worked.
2. Van Shift Opening/Closing had "submit" but not "write"; `doc.submit()`
   internally calls `save()`, which always checks "write" first — so drivers
   could create a shift but never submit it.
3. The `has_permission` hook for shift doctypes denied "write" unconditionally,
   which (after fixing #2's DocPerm) still blocked submit for the same reason.

SINCE SUPERSEDED — do not re-add those DocPerms on the strength of #1-#3. Every
write to Sales Order and to the shift doctypes now goes through a whitelisted
endpoint that authorizes the caller itself and then uses flags.ignore_permissions,
so the Van Sales Driver role deliberately holds read-only DocPerms on all three.
Granting create/write/submit back would let anyone holding the role write those
documents straight through /api/resource without passing a single van_sale check.
test_driver_cannot_write_sales_order_through_docperms() below guards that.
4. `_compute_closing()` defaulted to the literal Mode of Payment "Cash" when a
   driver had no collections yet, which fails for a driver whose Van Profile
   uses a differently-named cash mode (e.g. "Van - 02 - Cash").

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_shift_and_access
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from van_sale.van_sale.sales import create_sales_order, submit_sales_order
from van_sale.van_sale.shift import close_shift, open_shift
from van_sale.van_sale.utils import _validate_customer_access

TEST_PREFIX = "_Test Van Sale"


def _root_group(doctype: str) -> str | None:
	"""Return any existing group-type node for a tree doctype (e.g. the root
	"All Customer Groups" / "All Item Groups"), whatever it happens to be
	named on this site."""
	return frappe.db.get_value(doctype, {"is_group": 1}, "name")


class TestShiftAndAccessRegressions(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		company_row = frappe.get_all("Company", fields=["name", "default_currency"], limit=1)
		if not company_row:
			raise unittest.SkipTest("No Company configured on this site")
		cls.company = company_row[0].name

		item_group = _root_group("Item Group")
		customer_group_root = _root_group("Customer Group")
		uom_row = frappe.get_all("UOM", limit=1)
		if not (item_group and customer_group_root and uom_row):
			raise unittest.SkipTest("Item Group / Customer Group / UOM setup missing on this site")
		cls.uom = uom_row[0].name

		# Warehouses (source + van) — Warehouse.insert() auto-suffixes " - <company abbr>".
		cls.source_warehouse = cls._get_or_create_warehouse(f"{TEST_PREFIX} Source")
		cls.van_warehouse = cls._get_or_create_warehouse(f"{TEST_PREFIX} Van")

		# A cash-type Mode of Payment that is NOT named "Cash" — this is what
		# exposes bug #4 if the hardcoded fallback regresses.
		cls.cash_mode = f"{TEST_PREFIX} Cash"
		if not frappe.db.exists("Mode of Payment", cls.cash_mode):
			frappe.get_doc(
				{"doctype": "Mode of Payment", "mode_of_payment": cls.cash_mode, "type": "Cash", "enabled": 1}
			).insert(ignore_permissions=True)

		# Two customer groups so we can test the allowed_customer_groups restriction.
		cls.group_allowed = cls._get_or_create_customer_group(f"{TEST_PREFIX} Allowed", customer_group_root)
		cls.group_denied = cls._get_or_create_customer_group(f"{TEST_PREFIX} Denied", customer_group_root)

		cls.customer_allowed = cls._get_or_create_customer(f"{TEST_PREFIX} Customer Allowed", cls.group_allowed)
		cls.customer_denied = cls._get_or_create_customer(f"{TEST_PREFIX} Customer Denied", cls.group_denied)

		cls.item_code = f"{TEST_PREFIX} Item"
		if not frappe.db.exists("Item", cls.item_code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": cls.item_code,
					"item_name": cls.item_code,
					"item_group": item_group,
					"stock_uom": cls.uom,
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)

		cls.driver_user = "_test_van_sale_driver@example.com"
		if not frappe.db.exists("User", cls.driver_user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": cls.driver_user,
					"first_name": "Test Van Driver",
					"user_type": "System User",
					"send_welcome_email": 0,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

		# Creating this Van Profile with the driver assigned triggers the same
		# on_update -> _sync_driver_roles() path used in production, so the test
		# exercises the real role-assignment pipeline, not a shortcut.
		cls.van_profile = f"{TEST_PREFIX} Profile"
		if frappe.db.exists("Van Profile", cls.van_profile):
			frappe.delete_doc("Van Profile", cls.van_profile, ignore_permissions=True, force=True)
		frappe.get_doc(
			{
				"doctype": "Van Profile",
				"profile_name": cls.van_profile,
				"company": cls.company,
				"is_active": 1,
				"source_warehouse": cls.source_warehouse,
				"van_warehouse": cls.van_warehouse,
				"default_cash_mode": cls.cash_mode,
				"assigned_drivers": [{"driver_user": cls.driver_user}],
				"allowed_payment_modes": [{"mode_of_payment": cls.cash_mode}],
				"allowed_customer_groups": [{"customer_group": cls.group_allowed}],
			}
		).insert(ignore_permissions=True)

	@classmethod
	def _get_or_create_warehouse(cls, warehouse_name: str) -> str:
		existing = frappe.db.get_value("Warehouse", {"warehouse_name": warehouse_name, "company": cls.company}, "name")
		if existing:
			return existing
		doc = frappe.get_doc(
			{"doctype": "Warehouse", "warehouse_name": warehouse_name, "company": cls.company}
		).insert(ignore_permissions=True)
		return doc.name

	@classmethod
	def _get_or_create_customer_group(cls, name: str, parent: str) -> str:
		if frappe.db.exists("Customer Group", name):
			return name
		frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": name,
				"parent_customer_group": parent,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		return name

	@classmethod
	def _get_or_create_customer(cls, name: str, customer_group: str) -> str:
		if frappe.db.exists("Customer", name):
			return name
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": customer_group,
				"customer_type": "Company",
			}
		).insert(ignore_permissions=True)
		return name

	def setUp(self):
		frappe.set_user(self.driver_user)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_driver_cannot_write_sales_order_through_docperms(self):
		"""Sales Order writes go through whitelisted endpoints only. The Van Sales Driver
		role holds read-only DocPerms, so a direct insert — which is what the frontend
		used to do via frappe.client.insert — must be refused. If this ever passes again,
		anyone holding the role can write orders without passing a single van_sale check
		and can dictate their own totals."""
		frappe.set_user(self.driver_user)
		self.addCleanup(frappe.set_user, "Administrator")

		self.assertTrue(frappe.has_permission("Sales Order", "read"))
		self.assertFalse(frappe.has_permission("Sales Order", "create"))
		self.assertFalse(frappe.has_permission("Sales Order", "write"))
		self.assertFalse(frappe.has_permission("Sales Order", "submit"))

		today = nowdate()
		so = frappe.new_doc("Sales Order")
		so.customer = self.customer_allowed
		so.company = self.company
		so.transaction_date = today
		so.delivery_date = today
		so.append("items", {"item_code": self.item_code, "qty": 1, "rate": 1, "delivery_date": today})
		with self.assertRaises(frappe.PermissionError):
			so.insert()

	def test_customer_access_respects_allowed_customer_groups(self):
		"""Regression: this restriction now lives on Van Profile instead of a
		standalone User Permission record, which is what caused the Van-01 vs
		Van-02 mismatch bug — one source of truth instead of two."""
		# Should not raise for a customer in the driver's allowed group.
		_validate_customer_access(self.customer_allowed)

		with self.assertRaises(frappe.PermissionError):
			_validate_customer_access(self.customer_denied)

	def test_driver_can_run_full_shift_and_sales_cycle(self):
		"""End-to-end: place + submit a Sales Order, open a shift, close it,
		and verify the closing correctly reflects both — the same sequence a
		real driver's PWA session performs."""
		today = nowdate()

		# Built through the real endpoint: Sales Order writes no longer go through
		# the DocPerm layer, so a direct .insert() as a driver is refused by design.
		so = frappe.get_doc("Sales Order", create_sales_order(self.customer_allowed, [{"item_code": self.item_code, "qty": 1, "rate": 100}])["name"])

		# Regression #1: Sales Order was missing "submit" role permission.
		submit_sales_order(so.name)
		so.reload()
		self.assertEqual(so.docstatus, 1)

		# Regressions #2/#3: shift docs had "submit" but not "write" (and the
		# has_permission hook denied "write" outright) — doc.submit() calls
		# save() internally, which always checks "write" first.
		opening = open_shift(balance_details="[]", notes=None)
		self.assertEqual(opening["status"], "Open")

		closing = close_shift(opening_shift=opening["name"], reconciliation="[]", notes=None)
		closing_doc = frappe.get_doc("Van Shift Closing", closing["name"])
		self.assertEqual(closing_doc.docstatus, 1)
		self.assertAlmostEqual(closing_doc.total_sales, 100, places=2)

		# Regression #4: must use the driver's own configured cash mode, not
		# the hardcoded literal "Cash".
		modes_used = {row.mode_of_payment for row in closing_doc.payment_reconciliation}
		self.assertIn(self.cash_mode, modes_used)
		self.assertNotIn("Cash", modes_used)

		# The Sales Order should show up in the closing's audit trail.
		transaction_refs = {
			(row.reference_doctype, row.reference_name) for row in closing_doc.transactions
		}
		self.assertIn(("Sales Order", so.name), transaction_refs)
