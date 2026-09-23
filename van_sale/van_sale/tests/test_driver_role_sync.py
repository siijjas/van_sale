"""Regression tests for Van Profile ↔ Van Sales Driver role synchronisation.

The role is not decorative: setup.py attaches Custom DocPerms to it that include
create/write/submit on Sales Order, reachable through plain /api/resource without
going near a van_sale endpoint. So the role has to track profile assignment in
*both* directions. Previously it only ever got granted:

1. Removing a driver from a profile left the role (and the Sales Order write access
   that comes with it) in place indefinitely.
2. Deactivating a profile did the same.
3. _clear_van_profile_cache() iterated the *new* assigned_drivers list, so a removed
   driver's cached config survived for up to DRIVER_CACHE_TTL — they kept working
   against a van they were no longer on.
4. get_van_profile_for_driver() read any one assignment row and only then checked
   is_active, so a leftover assignment to a deactivated profile could resolve to
   None ("No active driver configuration found") while an active profile existed.
5. Nothing stopped a driver being assigned to two active profiles at once, which
   made the resolution above nondeterministic.

Run with: bench run-tests --site <site> --module van_sale.van_sale.tests.test_driver_role_sync
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from van_sale.van_sale.doctype.van_profile.van_profile import DRIVER_ROLE
from van_sale.van_sale.utils import _driver_cache_key, _get_driver_config, _is_driver
from van_sale.van_sale.van_profile import audit_driver_roles, get_van_profile_for_driver

TEST_PREFIX = "_Test Van Role Sync"


class TestDriverRoleSync(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		company_row = frappe.get_all("Company", fields=["name"], limit=1)
		if not company_row:
			raise unittest.SkipTest("No Company configured on this site")
		cls.company = company_row[0].name

		cls.source_warehouse = cls._warehouse(f"{TEST_PREFIX} Source")
		cls.van_a = cls._warehouse(f"{TEST_PREFIX} Van A")
		cls.van_b = cls._warehouse(f"{TEST_PREFIX} Van B")

		cls.driver = cls._user("_test_van_role_sync_driver@example.com", "Role Sync Driver")
		cls.other_driver = cls._user("_test_van_role_sync_other@example.com", "Role Sync Other")

	def setUp(self):
		frappe.set_user("Administrator")
		self.profile_a = self._profile(f"{TEST_PREFIX} A", self.van_a, [self.driver])
		self.profile_b = None

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in (f"{TEST_PREFIX} A", f"{TEST_PREFIX} B"):
			if frappe.db.exists("Van Profile", name):
				frappe.delete_doc("Van Profile", name, ignore_permissions=True, force=True)

	# ─── fixtures ──────────────────────────────────────────────────────────────

	@classmethod
	def _warehouse(cls, warehouse_name: str) -> str:
		existing = frappe.db.get_value(
			"Warehouse", {"warehouse_name": warehouse_name, "company": cls.company}, "name"
		)
		if existing:
			return existing
		return frappe.get_doc(
			{"doctype": "Warehouse", "warehouse_name": warehouse_name, "company": cls.company}
		).insert(ignore_permissions=True).name

	@classmethod
	def _user(cls, email: str, first_name: str) -> str:
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": first_name,
					"user_type": "System User",
					"send_welcome_email": 0,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		return email

	def _profile(self, profile_name: str, van_warehouse: str, drivers: list[str], is_active: int = 1) -> str:
		if frappe.db.exists("Van Profile", profile_name):
			frappe.delete_doc("Van Profile", profile_name, ignore_permissions=True, force=True)
		doc = frappe.get_doc(
			{
				"doctype": "Van Profile",
				"profile_name": profile_name,
				"company": self.company,
				"is_active": is_active,
				"source_warehouse": self.source_warehouse,
				"van_warehouse": van_warehouse,
				"assigned_drivers": [{"driver_user": u} for u in drivers],
			}
		).insert(ignore_permissions=True)
		return doc.name

	def _has_role(self, user: str) -> bool:
		frappe.clear_cache(user=user)
		return DRIVER_ROLE in frappe.get_roles(user)

	# ─── tests ─────────────────────────────────────────────────────────────────

	def test_assignment_grants_role(self):
		self.assertTrue(self._has_role(self.driver))
		self.assertEqual(get_van_profile_for_driver(self.driver)["name"], self.profile_a)

	def test_removing_driver_revokes_role(self):
		doc = frappe.get_doc("Van Profile", self.profile_a)
		doc.set("assigned_drivers", [])
		doc.save(ignore_permissions=True)

		self.assertFalse(self._has_role(self.driver))
		self.assertIsNone(get_van_profile_for_driver(self.driver))
		self.assertFalse(_is_driver(self.driver))

	def test_removing_driver_clears_cached_config(self):
		"""The removed driver is absent from the NEW child table, so a cache clear that
		only walks the new rows would leave their config live for DRIVER_CACHE_TTL."""
		self.assertIsNotNone(_get_driver_config(user=self.driver, required=False))
		self.assertIsNotNone(frappe.cache.get_value(_driver_cache_key(self.driver)))

		doc = frappe.get_doc("Van Profile", self.profile_a)
		doc.set("assigned_drivers", [])
		doc.save(ignore_permissions=True)

		self.assertIsNone(frappe.cache.get_value(_driver_cache_key(self.driver)))
		self.assertIsNone(_get_driver_config(user=self.driver, required=False))

	def test_deactivating_profile_revokes_role(self):
		doc = frappe.get_doc("Van Profile", self.profile_a)
		doc.is_active = 0
		doc.save(ignore_permissions=True)

		self.assertFalse(self._has_role(self.driver))
		self.assertIsNone(get_van_profile_for_driver(self.driver))

	def test_reactivating_profile_regrants_role(self):
		doc = frappe.get_doc("Van Profile", self.profile_a)
		doc.is_active = 0
		doc.save(ignore_permissions=True)
		doc.reload()
		doc.is_active = 1
		doc.save(ignore_permissions=True)

		self.assertTrue(self._has_role(self.driver))
		self.assertEqual(get_van_profile_for_driver(self.driver)["name"], self.profile_a)

	def test_deleting_profile_revokes_role(self):
		frappe.delete_doc("Van Profile", self.profile_a, ignore_permissions=True, force=True)

		self.assertFalse(self._has_role(self.driver))
		self.assertIsNone(get_van_profile_for_driver(self.driver))

	def test_second_active_profile_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._profile(f"{TEST_PREFIX} B", self.van_b, [self.driver])

		# The original assignment is untouched by the rejected save.
		self.assertEqual(get_van_profile_for_driver(self.driver)["name"], self.profile_a)

	def test_stale_inactive_assignment_does_not_mask_active_profile(self):
		"""A leftover assignment on a deactivated profile must not resolve to None and
		surface as "No active driver configuration found"."""
		self._profile(f"{TEST_PREFIX} B", self.van_b, [self.driver], is_active=0)

		config = get_van_profile_for_driver(self.driver)
		self.assertIsNotNone(config)
		self.assertEqual(config["name"], self.profile_a)

	def test_moving_driver_between_profiles(self):
		doc = frappe.get_doc("Van Profile", self.profile_a)
		doc.set("assigned_drivers", [])
		doc.save(ignore_permissions=True)
		self._profile(f"{TEST_PREFIX} B", self.van_b, [self.driver])

		self.assertTrue(self._has_role(self.driver))
		self.assertEqual(get_van_profile_for_driver(self.driver)["name"], f"{TEST_PREFIX} B")

	def test_disabled_user_cannot_be_assigned(self):
		user_doc = frappe.get_doc("User", self.other_driver)
		user_doc.enabled = 0
		user_doc.flags.ignore_permissions = True
		user_doc.save()
		try:
			with self.assertRaises(frappe.ValidationError):
				self._profile(f"{TEST_PREFIX} B", self.van_b, [self.other_driver])
		finally:
			user_doc.reload()
			user_doc.enabled = 1
			user_doc.flags.ignore_permissions = True
			user_doc.save()

	def test_audit_reports_orphaned_role(self):
		doc = frappe.get_doc("Van Profile", self.profile_a)
		doc.set("assigned_drivers", [])
		doc.save(ignore_permissions=True)

		# Re-grant out of band, the way pre-fix drift (or a manual desk edit) leaves it.
		user_doc = frappe.get_doc("User", self.driver)
		user_doc.flags.ignore_permissions = True
		user_doc.add_roles(DRIVER_ROLE)
		self.assertTrue(self._has_role(self.driver))

		report = audit_driver_roles()
		self.assertIn(self.driver, report["orphaned_role"])
		self.assertNotIn(self.driver, report["active_drivers"])

		audit_driver_roles(repair=1)
		self.assertFalse(self._has_role(self.driver))

	def test_audit_regrants_missing_role(self):
		user_doc = frappe.get_doc("User", self.driver)
		user_doc.flags.ignore_permissions = True
		user_doc.remove_roles(DRIVER_ROLE)
		self.assertFalse(self._has_role(self.driver))

		report = audit_driver_roles()
		self.assertIn(self.driver, report["missing_role"])

		audit_driver_roles(repair=1)
		self.assertTrue(self._has_role(self.driver))
