import frappe


MANAGER_ROLES = {"System Manager", "Sales Manager"}


def _is_manager(user: str | None = None) -> bool:
	roles = set(frappe.get_roles(user or frappe.session.user))
	return bool(MANAGER_ROLES & roles)


# ─── Van EOD Report ────────────────────────────────────────────────────────────

def get_van_eod_report_permission_query_conditions(user: str | None = None):
	"""Row-level filter: drivers see only their own EOD reports; managers see all."""
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return None
	return f"`tabVan EOD Report`.`driver` = {frappe.db.escape(current_user)}"


def has_van_eod_report_permission(doc, ptype="read", user: str | None = None):
	"""Document-level check: drivers may create/submit/read/print their own EOD reports."""
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return True
	if ptype == "create":
		return True
	if ptype in {"read", "select", "print", "email", "submit"}:
		return getattr(doc, "driver", None) == current_user
	# write, delete, cancel → denied for drivers
	return False


# ─── Van Expense Log ──────────────────────────────────────────────────────────

def get_van_expense_log_permission_query_conditions(user: str | None = None):
	"""Row-level filter: drivers see only their own expense logs; managers see all."""
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return None
	return f"`tabVan Expense Log`.`driver` = {frappe.db.escape(current_user)}"


def has_van_expense_log_permission(doc, ptype="read", user: str | None = None):
	"""Document-level check: drivers may create, read, and edit their own expense logs; no delete."""
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return True
	if ptype == "create":
		return True
	if ptype in {"read", "select", "write", "print", "email"}:
		return getattr(doc, "driver", None) == current_user
	# delete, submit, cancel → denied for drivers
	return False


# ─── Van Shift Opening / Closing ───────────────────────────────────────────────

def _shift_query_conditions(doctype: str, user: str | None = None):
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return None
	return f"`tab{doctype}`.`driver` = {frappe.db.escape(current_user)}"


def _has_shift_permission(doc, ptype, user):
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return True
	if ptype == "create":
		return True
	if ptype in {"read", "select", "print", "email", "submit"}:
		return getattr(doc, "driver", None) == current_user
	# write, delete, cancel → denied for drivers
	return False


def get_van_shift_opening_permission_query_conditions(user: str | None = None):
	"""Row-level filter: drivers see only their own opening shifts; managers see all."""
	return _shift_query_conditions("Van Shift Opening", user)


def has_van_shift_opening_permission(doc, ptype="read", user: str | None = None):
	"""Document-level check: drivers may create/submit/read/print their own opening shifts."""
	return _has_shift_permission(doc, ptype, user)


def get_van_shift_closing_permission_query_conditions(user: str | None = None):
	"""Row-level filter: drivers see only their own closing shifts; managers see all."""
	return _shift_query_conditions("Van Shift Closing", user)


def has_van_shift_closing_permission(doc, ptype="read", user: str | None = None):
	"""Document-level check: drivers may create/submit/read/print their own closing shifts."""
	return _has_shift_permission(doc, ptype, user)


# ─── Van Profile ───────────────────────────────────────────────────────────────

def get_van_profile_permission_query_conditions(user: str | None = None):
	"""Row-level filter: managers see all Van Profiles; drivers only see profiles they are assigned to."""
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return None
	# Driver can read only profiles where they appear in the assigned_drivers child table
	return (
		f"`tabVan Profile`.`name` in ("
		f"  select `parent` from `tabVan Profile Driver`"
		f"  where `driver_user` = {frappe.db.escape(current_user)}"
		f")"
	)


def has_van_profile_permission(doc, ptype="read", user: str | None = None):
	"""Document-level check: managers have full access; drivers can only read assigned profiles."""
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return True
	# Drivers: read-only, and only if they are in the assigned_drivers table
	if ptype not in {"read", "select", "print", "email"}:
		return False
	assigned_users = [
		row.driver_user
		for row in frappe.get_all(
			"Van Profile Driver",
			filters={"parent": doc.name},
			fields=["driver_user"],
		)
	]
	return current_user in assigned_users