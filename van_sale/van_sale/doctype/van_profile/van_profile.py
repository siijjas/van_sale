import frappe
from frappe.model.document import Document


class VanProfile(Document):
	def validate(self):
		if self.source_warehouse and self.van_warehouse and self.source_warehouse == self.van_warehouse:
			frappe.throw("Main Warehouse and Van Warehouse must be different")

		# Ensure no duplicate drivers in the assigned_drivers table
		seen_users = set()
		for row in self.assigned_drivers or []:
			if row.driver_user in seen_users:
				frappe.throw(f"Driver {row.driver_user} is already assigned to this profile")
			seen_users.add(row.driver_user)

		# Ensure no duplicate payment modes
		seen_modes = set()
		for row in self.allowed_payment_modes or []:
			if row.mode_of_payment in seen_modes:
				frappe.throw("Allowed payment modes cannot contain duplicates")
			seen_modes.add(row.mode_of_payment)

	def after_insert(self):
		_clear_van_profile_cache(self)

	def on_update(self):
		_clear_van_profile_cache(self)
		if self.is_active:
			_auto_assign_driver_role(self)

	def on_trash(self):
		_clear_van_profile_cache(self)


def _clear_van_profile_cache(doc, method=None):
	"""Clear driver config cache for all drivers assigned to this profile."""
	from van_sale.van_sale.utils import _driver_cache_key, _driver_stock_cache_key

	for row in doc.assigned_drivers or []:
		if row.driver_user:
			frappe.cache.delete_value(_driver_cache_key(row.driver_user))
			frappe.cache.delete_value(_driver_stock_cache_key(row.driver_user))


def _auto_assign_driver_role(doc):
	"""Ensure every driver assigned to an active Van Profile has the Van Sales Driver role."""
	for row in doc.assigned_drivers or []:
		if not row.driver_user:
			continue
		if "Van Sales Driver" not in frappe.get_roles(row.driver_user):
			try:
				user_doc = frappe.get_doc("User", row.driver_user)
				user_doc.append("roles", {"role": "Van Sales Driver"})
				user_doc.save(ignore_permissions=True)
			except Exception as e:
				frappe.log_error(
					title="van_sale: auto-role assignment failed",
					message=f"Could not assign 'Van Sales Driver' role to {row.driver_user}: {e}",
				)
