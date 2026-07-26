import json
import frappe
from van_sale.van_sale.utils import (
	_manager_only, _coerce_list, _to_float, _coerce_check, _default_company,
	_get_driver_config, _driver_cache_key,
	_driver_stock_cache_key, _is_manager, _is_driver
)

@frappe.whitelist()
def get_driver_setup_options():
	_manager_only()
	return {
		"users": frappe.get_all(
			"User",
			filters={"enabled": 1, "user_type": "System User"},
			fields=["name", "full_name"],
			limit_page_length=200,
			order_by="full_name asc",
		),
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
		"companies": frappe.get_all(
			"Company",
			fields=["name", "default_currency"],
			limit_page_length=50,
			order_by="name asc",
		),
	}


@frappe.whitelist()
def get_app_context():
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("No active session", frappe.PermissionError)

	full_name = frappe.db.get_value("User", user, "full_name") or user
	config = _get_driver_config(user=user, required=False)
	return {
		"user": user,
		"full_name": full_name,
		"sid": frappe.session.sid,
		"roles": frappe.get_roles(user),
		"is_manager": _is_manager(user),
		"is_driver": _is_driver(user),
		"driver_config": config,
	}
