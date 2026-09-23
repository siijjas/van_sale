import frappe
from frappe.model.document import Document

DRIVER_ROLE = "Van Sales Driver"


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

		self._validate_drivers_are_enabled()
		self._validate_one_active_profile_per_driver()

	def _validate_drivers_are_enabled(self):
		"""Reject a disabled User: they can never log in, so the assignment does
		nothing except grant the driver role to a dormant account."""
		for row in self.assigned_drivers or []:
			if not row.driver_user:
				continue
			if not frappe.db.get_value("User", row.driver_user, "enabled"):
				frappe.throw(f"User {row.driver_user} is disabled and cannot be assigned as a driver")

	def _validate_one_active_profile_per_driver(self):
		"""A driver may belong to at most one ACTIVE Van Profile.

		get_van_profile_for_driver() resolves a driver to a single profile, so a
		driver sitting on two active profiles would silently get whichever one the
		query happened to return — a different warehouse, price list and payment
		mode set from one request to the next. Reject it at the source instead.

		Inactive profiles are exempt: parking an old profile with its driver list
		intact is a legitimate way to retire a van.
		"""
		if not self.is_active:
			return
		for row in self.assigned_drivers or []:
			if not row.driver_user:
				continue
			clash = _active_profiles_for_driver(row.driver_user, exclude=self.name)
			if clash:
				frappe.throw(
					f"Driver {row.driver_user} is already assigned to the active Van Profile "
					f"'{clash[0]}'. Deactivate that profile, or remove the driver from it first."
				)

	def on_update(self):
		# Union of before + after: a driver REMOVED from the table (or left behind by
		# a profile that was just deactivated) must have their cached config dropped
		# too, or they keep full access to a van they are no longer on for up to
		# DRIVER_CACHE_TTL. on_update also runs on insert, so this covers both.
		_clear_driver_caches(_previous_driver_users(self) | _driver_users(self))
		_sync_driver_roles(self)

	def on_trash(self):
		_clear_driver_caches(_driver_users(self))

	def after_delete(self):
		# Runs after the child rows are deleted, so _active_profiles_for_driver()
		# below no longer sees this profile and the revoke decision is accurate.
		for user in _driver_users(self):
			_revoke_driver_role_if_unassigned(user)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _driver_users(doc) -> set[str]:
	"""Driver users currently on this profile's child table."""
	return {row.driver_user for row in (doc.assigned_drivers or []) if row.driver_user}


def _previous_driver_users(doc) -> set[str]:
	"""Driver users on this profile as last persisted (empty for a new doc)."""
	before = doc.get_doc_before_save()
	return _driver_users(before) if before else set()


def _clear_driver_caches(users):
	from van_sale.van_sale.utils import _driver_cache_key, _driver_stock_cache_key

	for user in users:
		frappe.cache.delete_value(_driver_cache_key(user))
		frappe.cache.delete_value(_driver_stock_cache_key(user))


def _active_profiles_for_driver(driver_user: str, exclude: str | None = None) -> list[str]:
	"""Names of ACTIVE Van Profiles this user is assigned to, oldest first.

	parenttype/parentfield are pinned because `parent` alone is not unique across
	doctypes — another doctype's child row could carry a Van Profile's name.
	"""
	params = {"driver_user": driver_user}
	exclude_condition = ""
	if exclude:
		exclude_condition = "and vp.name != %(exclude)s"
		params["exclude"] = exclude

	rows = frappe.db.sql(
		f"""
		select vp.name
		from `tabVan Profile Driver` vpd
		inner join `tabVan Profile` vp on vp.name = vpd.parent
		where vpd.driver_user = %(driver_user)s
			and vpd.parenttype = 'Van Profile'
			and vpd.parentfield = 'assigned_drivers'
			and vp.is_active = 1
			{exclude_condition}
		order by vp.creation asc
		""",
		params,
	)
	return [row[0] for row in rows]


def _sync_driver_roles(doc):
	"""Grant the driver role to everyone on an active profile, and take it back from
	anyone this save left without any active profile.

	Without the revoke half, a driver removed from a profile — or one left behind by a
	profile that was deactivated — keeps the Van Sales Driver role, and with it the
	Custom DocPerms setup.py grants that role, which include create/write/submit on
	Sales Order through plain /api/resource. The van_sale endpoints would refuse them
	(_is_van_user() is profile-based, not role-based) but the REST layer would not.
	"""
	current = _driver_users(doc)
	grant = current if doc.is_active else set()
	for user in grant:
		_grant_driver_role(user)
	for user in (_previous_driver_users(doc) | current) - grant:
		_revoke_driver_role_if_unassigned(user)


def _grant_driver_role(user: str):
	if DRIVER_ROLE in frappe.get_roles(user):
		return
	try:
		user_doc = frappe.get_doc("User", user)
		# A Sales Manager editing a profile has no write permission on User, so the
		# role change has to bypass it — the manager gate is _manager_only() upstream.
		user_doc.flags.ignore_permissions = True
		user_doc.add_roles(DRIVER_ROLE)
	except Exception as e:
		frappe.log_error(
			title="van_sale: driver role grant failed",
			message=f"Could not assign '{DRIVER_ROLE}' to {user}: {e}",
		)


def _revoke_driver_role_if_unassigned(user: str):
	"""Remove the driver role, but only once the user holds no active profile at all.

	Note this is per-save: moving a driver between vans as two separate saves does
	revoke the role on the first save and re-grant it on the second, so the driver is
	briefly locked out in between. That is accurate — at that moment they are on no
	van — and the end state is correct either way.
	"""
	if _active_profiles_for_driver(user):
		return
	if DRIVER_ROLE not in frappe.get_roles(user):
		return
	try:
		user_doc = frappe.get_doc("User", user)
		user_doc.flags.ignore_permissions = True
		user_doc.remove_roles(DRIVER_ROLE)
	except Exception as e:
		frappe.log_error(
			title="van_sale: driver role revoke failed",
			message=f"Could not remove '{DRIVER_ROLE}' from {user}: {e}",
		)
	finally:
		_clear_driver_caches({user})
