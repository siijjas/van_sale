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
		cached = frappe.cache.get_value(_driver_cache_key(current_user))
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
	"""For drivers with an assigned delivery route, restrict access to customers in that territory.

	- Administrators and Managers: unrestricted.
	- Drivers with no delivery_route configured: unrestricted.
	- Drivers with a delivery_route: the customer's ERPNext territory must either
	  match exactly or be a descendant of the route territory.
	  Example: route = "All Territories"  covers "Qatar", "Dubai", etc.

	Assumes _require_van_user() has already been called.
	"""
	current_user = user or frappe.session.user
	if current_user == "Administrator" or _is_manager(current_user):
		return

	config = _get_driver_config(user=current_user, required=False)
	if not config or not config.get("delivery_route"):
		return  # No route restriction configured for this driver

	cust_territory = frappe.db.get_value("Customer", customer, "territory")
	if not cust_territory:
		return  # Customer has no territory — no restriction applied

	# Exact match
	if cust_territory == config["delivery_route"]:
		return

	# Ancestry match: allow if the delivery route is a parent of the customer territory
	# (e.g. delivery_route = "All Territories" should include child territory "Qatar")
	try:
		from frappe.utils.nestedset import get_ancestors_of
		ancestors = get_ancestors_of("Territory", cust_territory)
		if config["delivery_route"] in ancestors:
			return
	except Exception:
		# If the nestedset check fails for any reason, be permissive rather than
		# blocking a legitimate field operation.
		return

	frappe.throw(
		f"Customer territory '{cust_territory}' is outside your assigned delivery route "
		f"'{config['delivery_route']}'. Contact your manager if this is incorrect.",
		frappe.PermissionError,
	)
