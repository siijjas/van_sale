import frappe

DRIVER_ROLE = "Van Sales Driver"

# ─────────────────────────────────────────────────────────────────────────────
# Minimum permissions the Van Sales Driver role needs on standard ERPNext
# doctypes that the PWA accesses via direct /api/resource/* REST calls.
#
# We use Custom DocPerm (the Frappe permission-manager layer) rather than
# touching the standard per-doctype permission table so that ERPNext upgrades
# cannot overwrite our additions.
# ─────────────────────────────────────────────────────────────────────────────
REST_DOCTYPE_PERMISSIONS: dict[str, dict[str, int]] = {
	# Item catalogue and pricing — read-only
	"Item":             {"read": 1, "report": 1},
	"Item Price":       {"read": 1, "report": 1},
	"Bin":              {"read": 1, "report": 1},

	# Customer directory — read-only (creation/editing stays in back-office)
	"Customer":         {"read": 1, "report": 1},

	# System / company configuration — read-only
	"Company":          {"read": 1},
	"Global Defaults":  {"read": 1},
	"Selling Settings": {"read": 1},

	# Payment configuration — read-only
	"Mode of Payment":  {"read": 1},

	# Van Profile — drivers may read their assigned profile
	"Van Profile":      {"read": 1},

	# Transactional doctypes the PWA reads/writes via REST or custom endpoints
	"Sales Order":      {"read": 1, "write": 1, "create": 1},
	"Payment Entry":    {"read": 1},
	"Sales Invoice":    {"read": 1},
}


def setup_van_sales_driver_permissions():
	"""Idempotent setup: ensure Van Sales Driver has the minimum ERPNext
	permissions required for the PWA to function.

	Called automatically after every ``bench migrate`` via the
	``after_migrate`` hook declared in hooks.py.

	Uses frappe.permissions helpers so the entries are created as
	Custom DocPerm records (same as the Frappe desk's Role Permissions
	Manager) and survive ERPNext upgrades.
	"""
	if not frappe.db.exists("Role", DRIVER_ROLE):
		frappe.log_error(
			title="van_sale setup",
			message=f"Role '{DRIVER_ROLE}' not found — skipping permission setup. "
			        "Run bench migrate again after the fixtures have been imported.",
		)
		return

	from frappe.permissions import add_permission, update_permission_property

	for doctype, perms in REST_DOCTYPE_PERMISSIONS.items():
		# add_permission is a no-op if the Custom DocPerm already exists
		try:
			add_permission(doctype, DRIVER_ROLE, 0)
		except Exception:
			pass  # record exists — proceed to property updates

		for ptype, value in perms.items():
			try:
				update_permission_property(doctype, DRIVER_ROLE, 0, ptype, value)
			except Exception as exc:
				frappe.log_error(
					title=f"van_sale: permission update failed",
					message=f"Could not set {ptype}={value} on '{doctype}' "
					        f"for role '{DRIVER_ROLE}': {exc}",
				)

	frappe.db.commit()
