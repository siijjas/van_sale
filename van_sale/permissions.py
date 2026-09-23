import frappe

# Single source of truth for who counts as a manager — utils._is_manager is the same
# check the whitelisted endpoints gate on, and the two drifting apart would mean the
# desk/REST layer and the app layer disagreed about who may see what.
from van_sale.van_sale.utils import MANAGER_ROLES, _is_manager  # noqa: F401


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
	if ptype == "write":
		# Defense in depth only, as things stand: the Van Sales Driver role holds just
		# "read" on the shift doctypes, and shift.py creates/submits them with
		# flags.ignore_permissions, so this branch cannot currently grant anything —
		# has_controller_permissions() is a gate, and the role DocPerm is the binding
		# constraint. It is kept so that widening those DocPerms can never hand a
		# driver write access to someone else's shift, or to their own closed one.
		# `doc.docstatus` is already flipped to the TARGET value (1) by _submit()
		# before this check runs, so it cannot be used to detect "still a draft" —
		# check what is actually persisted in the DB instead.
		if getattr(doc, "driver", None) != current_user:
			return False
		if doc.is_new():
			return True
		return frappe.db.get_value(doc.doctype, doc.name, "docstatus") == 0
	# delete, cancel → denied for drivers
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
	# Driver can read only profiles where they appear in the assigned_drivers child
	# table. parenttype/parentfield are pinned because `parent` alone is not unique
	# across doctypes — another doctype's child row could carry a Van Profile's name.
	return (
		f"`tabVan Profile`.`name` in ("
		f"  select `parent` from `tabVan Profile Driver`"
		f"  where `driver_user` = {frappe.db.escape(current_user)}"
		f"    and `parenttype` = 'Van Profile'"
		f"    and `parentfield` = 'assigned_drivers'"
		f")"
	)


def has_van_profile_permission(doc, ptype="read", user: str | None = None):
	"""Document-level check: managers have full access; drivers can only read assigned profiles."""
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return True
	# Drivers: read-only, and only if they are in the assigned_drivers table.
	if ptype not in {"read", "select", "print", "email"}:
		return False
	# frappe.db.exists() rather than frappe.get_all(): this runs *inside* the
	# permission system, and a permission-checked read of the child doctype from here
	# re-enters it. Raw DB access keeps the check from recursing.
	return bool(
		frappe.db.exists(
			"Van Profile Driver",
			{
				"parent": doc.name,
				"parenttype": "Van Profile",
				"parentfield": "assigned_drivers",
				"driver_user": current_user,
			},
		)
	)
