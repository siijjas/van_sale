"""
Van Profile API endpoints.

Van Profile is a named, reusable configuration record (analogous to POS Profile)
that can be shared across multiple drivers. Each Van Profile stores:

- Warehouses (source + van)
- Allowed payment modes
- Pricing & tax configuration
- Operational controls
- Print & accounting settings
- A list of assigned drivers

Drivers are linked to a profile via the assigned_drivers child table. The
profile is the single source of truth for a driver's runtime configuration —
get_van_profile_for_driver() resolves a driver to their active profile and
returns the payload consumed by the app (see _build_van_profile_payload).
"""

import json
import frappe
from van_sale.van_sale.utils import (
	_manager_only, _coerce_list, _to_float, _coerce_check,
	_default_company, _driver_cache_key, _driver_stock_cache_key,
)


# ─── Setup Options ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_van_profile_options():
	"""Return all option lists needed to build/edit a Van Profile form."""
	_manager_only()

	company_filter = {"is_group": 0}

	return {
		"warehouses": frappe.get_all(
			"Warehouse",
			filters={"is_group": 0, "disabled": 0},
			fields=["name", "company"],
			limit_page_length=500,
			order_by="name asc",
		),
		"payment_modes": frappe.get_all(
			"Mode of Payment",
			filters={"enabled": 1},
			fields=["name", "type"],
			limit_page_length=200,
			order_by="name asc",
		),
		"routes": frappe.get_all(
			"Territory",
			fields=["name"],
			limit_page_length=200,
			order_by="name asc",
		),
		"customer_groups": frappe.get_all(
			"Customer Group",
			fields=["name"],
			limit_page_length=200,
			order_by="name asc",
		),
		"companies": frappe.get_all(
			"Company",
			fields=["name", "default_currency"],
			limit_page_length=50,
			order_by="name asc",
		),
		"price_lists": frappe.get_all(
			"Price List",
			filters={"selling": 1, "enabled": 1},
			fields=["name"],
			limit_page_length=100,
			order_by="name asc",
		),
		"tax_templates": frappe.get_all(
			"Sales Taxes and Charges Template",
			fields=["name", "company"],
			limit_page_length=100,
			order_by="name asc",
		),
		"currencies": frappe.get_all(
			"Currency",
			filters={"enabled": 1},
			fields=["name"],
			limit_page_length=100,
			order_by="name asc",
		),
		"print_formats": frappe.get_all(
			"Print Format",
			fields=["name", "doc_type"],
			limit_page_length=200,
			order_by="name asc",
		),
		"users": frappe.get_all(
			"User",
			filters={"enabled": 1, "user_type": "System User"},
			fields=["name", "full_name"],
			limit_page_length=200,
			order_by="full_name asc",
		),
	}


# ─── CRUD ───────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def list_van_profiles():
	"""Return all Van Profile records with their assigned drivers and payment modes."""
	_manager_only()

	rows = frappe.get_all(
		"Van Profile",
		fields=[
			"name",
			"profile_name",
			"company",
			"source_warehouse",
			"van_warehouse",
			"delivery_route",
			"default_cash_mode",
			"selling_price_list",
			"currency",
			"taxes_and_charges",
			"apply_discount_on",
			"daily_credit_limit",
			"low_stock_threshold",
			"allow_rate_change",
			"allow_discount_change",
			"validate_stock_on_save",
			"allow_offline_stock_dashboard",
			"ignore_pricing_rule",
			"disable_rounded_total",
			"print_format",
			"letter_head",
			"income_account",
			"expense_account",
			"cost_center",
			"write_off_account",
			"is_active",
		],
		order_by="profile_name asc",
	)

	for row in rows:
		row.assigned_drivers = [
			{
				"driver_user": child.driver_user,
				"driver_full_name": child.driver_full_name,
			}
			for child in frappe.get_all(
				"Van Profile Driver",
				filters={"parent": row.name},
				fields=["driver_user", "driver_full_name"],
				order_by="idx asc",
			)
		]
		row.allowed_payment_modes = [
			child.mode_of_payment
			for child in frappe.get_all(
				"Van Profile Payment Mode",
				filters={"parent": row.name},
				fields=["mode_of_payment"],
				order_by="idx asc",
			)
		]
		row.allowed_customer_groups = [
			child.customer_group
			for child in frappe.get_all(
				"Van Profile Customer Group",
				filters={"parent": row.name},
				fields=["customer_group"],
				order_by="idx asc",
			)
		]
		# Coerce booleans
		for check_field in (
			"allow_rate_change", "allow_discount_change", "validate_stock_on_save",
			"allow_offline_stock_dashboard", "ignore_pricing_rule", "disable_rounded_total",
			"is_active",
		):
			row[check_field] = _coerce_check(row.get(check_field))

	return rows


@frappe.whitelist()
def save_van_profile(payload):
	"""Create or update a Van Profile record."""
	_manager_only()
	data = payload if isinstance(payload, dict) else json.loads(payload)

	name = data.get("name") or frappe.db.get_value(
		"Van Profile", {"profile_name": data.get("profile_name")}, "name"
	)
	doc = frappe.get_doc("Van Profile", name) if name else frappe.new_doc("Van Profile")

	# Scalar fields
	doc.profile_name = data.get("profile_name")
	doc.company = data.get("company") or _default_company()
	doc.source_warehouse = data.get("source_warehouse")
	doc.van_warehouse = data.get("van_warehouse")
	doc.delivery_route = data.get("delivery_route") or None
	doc.default_cash_mode = data.get("default_cash_mode") or None
	doc.selling_price_list = data.get("selling_price_list") or None
	doc.currency = data.get("currency") or None
	doc.taxes_and_charges = data.get("taxes_and_charges") or None
	doc.apply_discount_on = data.get("apply_discount_on") or "Grand Total"
	doc.daily_credit_limit = _to_float(data.get("daily_credit_limit"))
	doc.low_stock_threshold = _to_float(data.get("low_stock_threshold") or 5)
	doc.allow_rate_change = 1 if _coerce_check(data.get("allow_rate_change")) else 0
	doc.allow_discount_change = 1 if _coerce_check(data.get("allow_discount_change")) else 0
	doc.validate_stock_on_save = 1 if _coerce_check(data.get("validate_stock_on_save")) else 0
	doc.allow_offline_stock_dashboard = 1 if _coerce_check(data.get("allow_offline_stock_dashboard", True)) else 0
	doc.ignore_pricing_rule = 1 if _coerce_check(data.get("ignore_pricing_rule")) else 0
	doc.disable_rounded_total = 1 if _coerce_check(data.get("disable_rounded_total")) else 0
	doc.print_format = data.get("print_format") or None
	doc.letter_head = data.get("letter_head") or None
	doc.income_account = data.get("income_account") or None
	doc.expense_account = data.get("expense_account") or None
	doc.cost_center = data.get("cost_center") or None
	doc.write_off_account = data.get("write_off_account") or None
	doc.is_active = 1 if _coerce_check(data.get("is_active", True)) else 0

	# Assigned drivers child table
	doc.set("assigned_drivers", [])
	for driver in _coerce_list(data.get("assigned_drivers")):
		if isinstance(driver, dict):
			driver_user = driver.get("driver_user")
		else:
			driver_user = driver
		if driver_user:
			doc.append("assigned_drivers", {"driver_user": driver_user})

	# Payment modes child table (Table MultiSelect)
	doc.set("allowed_payment_modes", [])
	for mode in _coerce_list(data.get("allowed_payment_modes")):
		if isinstance(mode, str) and mode.strip():
			doc.append("allowed_payment_modes", {"mode_of_payment": mode.strip()})

	# Customer groups child table (Table MultiSelect)
	doc.set("allowed_customer_groups", [])
	for group in _coerce_list(data.get("allowed_customer_groups")):
		if isinstance(group, str) and group.strip():
			doc.append("allowed_customer_groups", {"customer_group": group.strip()})

	if doc.is_new():
		doc.insert()
	else:
		doc.save()

	return _build_van_profile_payload(doc)


@frappe.whitelist()
def delete_van_profile(name: str):
	"""Delete a Van Profile record. Managers only."""
	_manager_only()
	if not frappe.db.exists("Van Profile", name):
		frappe.throw(f"Van Profile '{name}' not found")
	frappe.delete_doc("Van Profile", name, ignore_permissions=True)
	return {"status": "deleted", "name": name}


@frappe.whitelist()
def assign_driver_to_profile(driver_user: str, van_profile: str):
	"""Add a driver to a Van Profile's assigned_drivers child table if not already present.

	Idempotent — calling twice for the same (driver, profile) pair is a no-op.
	Clears the driver's config cache so the next API call picks up the new profile.
	"""
	_manager_only()

	if not frappe.db.exists("User", driver_user):
		frappe.throw(f"User '{driver_user}' not found")
	if not frappe.db.exists("Van Profile", van_profile):
		frappe.throw(f"Van Profile '{van_profile}' not found")

	already_assigned = frappe.db.exists(
		"Van Profile Driver", {"parent": van_profile, "driver_user": driver_user}
	)
	if not already_assigned:
		doc = frappe.get_doc("Van Profile", van_profile)
		doc.append("assigned_drivers", {"driver_user": driver_user})
		doc.save()

	frappe.cache.delete_value(_driver_cache_key(driver_user))
	frappe.cache.delete_value(_driver_stock_cache_key(driver_user))
	return {"status": "ok", "driver_user": driver_user, "van_profile": van_profile}


@frappe.whitelist()
def audit_driver_roles(repair: int = 0):
	"""Report — and optionally fix — drift between Van Profile assignments and the
	Van Sales Driver role. Managers only; read-only unless repair is truthy.

	The doctype hooks keep the two in sync from now on, but they only act on saves,
	so anything that drifted before (or was changed straight in the User doctype)
	needs this to reconcile. Two kinds:

	- orphaned_role: holds the driver role but sits on no active Van Profile. Every
	  van_sale endpoint already refuses them (_is_van_user() is profile-based), but
	  the role still carries the Custom DocPerms setup.py grants it — including
	  create/write/submit on Sales Order straight through /api/resource.
	- missing_role: sits on an active Van Profile but lacks the role, so the REST
	  calls the PWA makes directly (Item, Bin, Customer, Sales Order) 403 for them.

	Administrator is never touched: the role is meaningless there (Administrator
	bypasses permission checks anyway) and removing it is pure noise.
	"""
	_manager_only()
	repair = _coerce_check(repair)

	from van_sale.van_sale.doctype.van_profile.van_profile import (
		DRIVER_ROLE, _active_profiles_for_driver, _grant_driver_role,
		_revoke_driver_role_if_unassigned,
	)

	assigned_users = {
		row.driver_user
		for row in frappe.get_all(
			"Van Profile Driver",
			filters={"parenttype": "Van Profile", "parentfield": "assigned_drivers"},
			fields=["driver_user"],
		)
		if row.driver_user
	}
	active_users = {user for user in assigned_users if _active_profiles_for_driver(user)}

	role_holders = {
		row.parent
		for row in frappe.get_all(
			"Has Role",
			filters={"role": DRIVER_ROLE, "parenttype": "User"},
			fields=["parent"],
		)
	} - {"Administrator"}

	orphaned = sorted(role_holders - active_users)
	missing = sorted(active_users - role_holders)

	repaired = {"granted": [], "revoked": []}
	if repair:
		for user in missing:
			_grant_driver_role(user)
			repaired["granted"].append(user)
		for user in orphaned:
			_revoke_driver_role_if_unassigned(user)
			repaired["revoked"].append(user)

	return {
		"orphaned_role": orphaned,
		"missing_role": missing,
		"active_drivers": sorted(active_users),
		"repaired": repaired if repair else None,
	}


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _build_van_profile_payload(doc) -> dict:
	"""Serialize a Van Profile document to a clean dict for API responses."""
	return {
		"name": doc.name,
		"profile_name": doc.profile_name,
		"company": doc.company,
		"source_warehouse": doc.source_warehouse,
		"van_warehouse": doc.van_warehouse,
		"delivery_route": doc.delivery_route,
		"default_cash_mode": doc.default_cash_mode,
		"selling_price_list": doc.selling_price_list,
		"currency": doc.currency,
		"taxes_and_charges": doc.taxes_and_charges,
		"apply_discount_on": doc.apply_discount_on or "Grand Total",
		"daily_credit_limit": _to_float(doc.daily_credit_limit),
		"low_stock_threshold": _to_float(doc.low_stock_threshold),
		"allow_rate_change": _coerce_check(doc.allow_rate_change),
		"allow_discount_change": _coerce_check(doc.allow_discount_change),
		"validate_stock_on_save": _coerce_check(doc.validate_stock_on_save),
		"allow_offline_stock_dashboard": _coerce_check(doc.allow_offline_stock_dashboard),
		"ignore_pricing_rule": _coerce_check(doc.ignore_pricing_rule),
		"disable_rounded_total": _coerce_check(doc.disable_rounded_total),
		"print_format": doc.print_format,
		"letter_head": doc.letter_head,
		"income_account": doc.income_account,
		"expense_account": doc.expense_account,
		"cost_center": doc.cost_center,
		"write_off_account": doc.write_off_account,
		"is_active": _coerce_check(doc.is_active),
		"assigned_drivers": [
			{"driver_user": row.driver_user, "driver_full_name": row.driver_full_name}
			for row in (doc.assigned_drivers or [])
		],
		"allowed_payment_modes": [
			row.mode_of_payment
			for row in (doc.allowed_payment_modes or [])
			if row.mode_of_payment
		],
		"allowed_customer_groups": [
			row.customer_group
			for row in (doc.allowed_customer_groups or [])
			if row.customer_group
		],
	}


def get_van_profile_for_driver(driver_user: str) -> dict | None:
	"""Return the Van Profile payload for a given driver.

	Resolves through the assigned_drivers child table, but only ever considers
	ACTIVE profiles and picks deterministically (oldest first). The previous
	version read any one assignment row and then checked is_active on it, so a
	driver with a leftover assignment to a deactivated profile could resolve to
	None — surfacing as "No active driver configuration found" — even while they
	held a perfectly good active profile. VanProfile.validate() also enforces at
	most one active profile per driver, so in practice this returns that one.
	"""
	from van_sale.van_sale.doctype.van_profile.van_profile import _active_profiles_for_driver

	profile_names = _active_profiles_for_driver(driver_user)
	if not profile_names:
		return None

	return _build_van_profile_payload(frappe.get_doc("Van Profile", profile_names[0]))

