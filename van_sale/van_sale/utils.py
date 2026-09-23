import json
import frappe
from frappe.utils import flt

MANAGER_ROLES = {"System Manager", "Sales Manager"}
DRIVER_CACHE_TTL = 300


def _default_naming_series():
	for field in frappe.get_meta("Sales Order").fields:
		if field.fieldname == "naming_series" and field.default:
			return field.default
	return "SO-"


def _default_company():
	return frappe.defaults.get_defaults().get("company") or frappe.db.get_default("company")


def _is_manager(user: str | None = None) -> bool:
	roles = set(frappe.get_roles(user or frappe.session.user))
	return bool(MANAGER_ROLES & roles)


def _driver_cache_key(user: str) -> str:
	return f"van_sale:driver_config:{user}"


def _driver_stock_cache_key(user: str) -> str:
	return f"van_sale:driver_stock:{user}"


def _coerce_check(value):
	if isinstance(value, bool):
		return value
	if value is None:
		return False
	return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _coerce_list(value):
	if value is None:
		return []
	if isinstance(value, list):
		return value
	if isinstance(value, str):
		text = value.strip()
		if not text:
			return []
		if text.startswith("["):
			return json.loads(text)
		return [row.strip() for row in text.split(",") if row.strip()]
	return list(value)


def _to_float(value, precision: int | None = None) -> float:
	number = flt(value)
	if precision is None:
		return number
	return round(number, precision)

def _get_driver_config(user: str | None = None, required: bool = True, use_cache: bool = True):
	current_user = user or frappe.session.user
	if use_cache:
		# expires=True because this key is written with expires_in_sec. Without it
		# get_value() writes the result — including a MISS, as None — into
		# frappe.local.cache, while set_value() with an expiry writes only to redis.
		# The poisoned None then shadows redis for the rest of the request, so every
		# later _get_driver_config() call in the same request rebuilds the whole Van
		# Profile payload from the database.
		cached = frappe.cache.get_value(_driver_cache_key(current_user), expires=True)
		if cached:
			return cached

	from van_sale.van_sale.van_profile import get_van_profile_for_driver
	payload = get_van_profile_for_driver(current_user)

	if not payload:
		if required:
			frappe.throw("No active driver configuration found for the current user")
		return None

	frappe.cache.set_value(_driver_cache_key(current_user), payload, expires_in_sec=DRIVER_CACHE_TTL)
	return payload


def _get_allowed_payment_modes(user: str | None = None, all_modes: bool = False) -> list[str] | None:
	if all_modes:
		return None
	config = _get_driver_config(user=user, required=False)
	if not config:
		return None
	return config.get("allowed_payment_modes") or []


def _ensure_driver_mode_allowed(mode_of_payment: str, user: str | None = None):
	allowed_modes = _get_allowed_payment_modes(user=user)
	if allowed_modes is None:
		return
	if mode_of_payment not in allowed_modes:
		frappe.throw(f"Mode of payment {mode_of_payment} is not allowed for this driver")


def _manager_only():
	if frappe.session.user == "Administrator" or _is_manager():
		return
	frappe.throw("Only managers can perform this action", frappe.PermissionError)


# ─── NEW: Van Sales authorization helpers ─────────────────────────────────────

def _is_driver(user: str | None = None) -> bool:
	"""Returns True if the user is assigned to an active Van Profile.

	Uses the cached driver config path so repeated calls within a request are cheap.
	"""
	return bool(_get_driver_config(user=user, required=False))


def _is_van_user(user: str | None = None) -> bool:
	"""Returns True if the user is Administrator, a Manager, or an active Driver."""
	current_user = user or frappe.session.user
	if current_user == "Administrator":
		return True
	return _is_manager(current_user) or _is_driver(current_user)


def _require_van_user(user: str | None = None):
	"""Primary authorization gate for all van_sale whitelisted endpoints.

	Raises PermissionError unless the caller is Administrator, holds a manager
	role (System Manager / Sales Manager), or is an active Van Sales Driver
	(i.e. is assigned to an active Van Profile).

	Call this at the very top of every @frappe.whitelist() function to prevent
	arbitrary ERPNext users from invoking field-operations APIs.
	"""
	if not _is_van_user(user):
		frappe.throw(
			"Access denied. You must be an active Van Sales Driver or Manager to use this application.",
			frappe.PermissionError,
		)


def _validate_customer_access(customer: str, user: str | None = None):
	"""Restrict a driver's customer access to their Van Profile's delivery route and/or
	allowed customer groups. Both checks come from the SAME Van Profile record (the
	single source of truth for what a driver can see) rather than from standalone
	Frappe User Permission records, which are easy to leave out of sync with a
	driver's actual profile/van assignment.

	- Administrators and Managers: unrestricted.
	- delivery_route (Territory): if set, the customer's territory must match it
	  exactly or be a descendant of it. Example: route = "All Territories" covers
	  "Qatar", "Dubai", etc.
	- allowed_customer_groups: if set, the customer's customer_group must be one of
	  them.
	- Either restriction left unset on the Van Profile means unrestricted on that
	  dimension; both apply together (AND) when both are configured.

	Assumes _require_van_user() has already been called.
	"""
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return

	config = _get_driver_config(user=current_user, required=False)
	if not config:
		return

	delivery_route = config.get("delivery_route")
	allowed_groups = config.get("allowed_customer_groups") or []
	if not delivery_route and not allowed_groups:
		return  # No restriction configured for this driver

	customer_doc = frappe.db.get_value(
		"Customer", customer, ["territory", "customer_group"], as_dict=True
	)
	if not customer_doc:
		return

	if delivery_route and customer_doc.territory and customer_doc.territory != delivery_route:
		# Ancestry match: allow if the delivery route is a parent of the customer
		# territory (e.g. delivery_route = "All Territories" should include child
		# territory "Qatar").
		is_descendant = False
		try:
			from frappe.utils.nestedset import get_ancestors_of
			is_descendant = delivery_route in get_ancestors_of("Territory", customer_doc.territory)
		except Exception:
			# If the nestedset check fails for any reason, be permissive rather than
			# blocking a legitimate field operation.
			is_descendant = True
		if not is_descendant:
			frappe.throw(
				f"Customer territory '{customer_doc.territory}' is outside your assigned delivery "
				f"route '{delivery_route}'. Contact your manager if this is incorrect.",
				frappe.PermissionError,
			)

	if allowed_groups and customer_doc.customer_group and customer_doc.customer_group not in allowed_groups:
		frappe.throw(
			f"Customer group '{customer_doc.customer_group}' is not assigned to your van profile. "
			f"Contact your manager if this is incorrect.",
			frappe.PermissionError,
		)
