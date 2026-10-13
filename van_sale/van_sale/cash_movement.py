"""
Cash movement API: expenses paid from the drawer and cash deposits to the office.

See doctype/van_cash_movement for the accounting. The endpoints here are what the
app calls; the Van Sales Driver role holds only read on the doctype, so creation
goes through create_cash_movement() with the same authorize-then-bypass pattern
as shift.open_shift(): the caller is checked, the shift is theirs and open, and the
profile's rules are enforced by the doctype's validate().
"""

import frappe
from frappe.utils import flt

from van_sale.van_sale.doctype.van_cash_movement.van_cash_movement import (
	MOVEMENT_TYPES,
	resolve_back_office_account,
	resolve_cash_account,
)
from van_sale.van_sale.shift import _find_open_shift
from van_sale.van_sale.utils import (
	_get_driver_config,
	_is_manager,
	_manager_only,
	_require_capability,
	_require_van_user,
)


def _open_shift_or_throw(user: str) -> str:
	"""Cash movements always need an open shift (the drawer they come out of),
	regardless of the profile's require_open_shift setting for selling."""
	name = _find_open_shift(user, today_only=False)
	if not name:
		frappe.throw("Open your shift before you record an expense or deposit.", title="Shift required")
	return name


def _expense_accounts(profile, company: str) -> list[dict]:
	allowed = [row.account for row in (profile.allowed_expense_accounts or [])] if profile else []
	filters = {"company": company, "root_type": "Expense", "is_group": 0, "disabled": 0}
	if allowed:
		filters["name"] = ["in", allowed]
	return frappe.get_all(
		"Account", filters=filters, fields=["name", "account_name"], order_by="account_name asc", limit_page_length=200
	)


def _serialize(doc) -> dict:
	return {
		"name": doc.name,
		"movement_type": doc.movement_type,
		"amount": flt(doc.amount),
		"posting_date": str(doc.posting_date),
		"driver": doc.driver,
		"opening_shift": doc.opening_shift,
		"expense_account": doc.expense_account,
		"source_account": doc.source_account,
		"target_account": doc.target_account,
		"against_name": doc.against_name,
		"remarks": doc.remarks,
		"journal_entry": doc.journal_entry,
		"docstatus": doc.docstatus,
		"creation": str(doc.creation),
	}


# ─── Endpoints ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_cash_movement_context():
	"""Everything the Cash Movement screen needs: what the profile allows, the
	accounts to pick from, and the movements already on the open shift."""
	_require_van_user()
	_require_capability("uses_shifts", "record cash movements")
	user = frappe.session.user
	config = _get_driver_config(required=False)
	profile = frappe.get_cached_doc("Van Profile", config["name"]) if config else None
	company = (config or {}).get("company") or frappe.defaults.get_defaults().get("company")

	opening_shift = _find_open_shift(user, today_only=False)
	return {
		"opening_shift": opening_shift,
		"allow_expense": bool(profile.allow_expense) if profile else True,
		"allow_cash_deposit": bool(profile.allow_cash_deposit) if profile else True,
		"require_remarks": bool(profile.require_cash_movement_remarks) if profile else False,
		"max_amount": flt(profile.cash_movement_max_amount) if profile else 0.0,
		"cash_account": resolve_cash_account(profile, company) if company else None,
		"back_office_cash_account": resolve_back_office_account(profile, company) if company else None,
		"default_expense_account": profile.expense_account if profile else None,
		"expense_accounts": _expense_accounts(profile, company) if company else [],
		"movements": get_shift_cash_movements(opening_shift) if opening_shift else [],
	}


@frappe.whitelist()
def create_cash_movement(
	movement_type: str,
	amount: float,
	expense_account: str | None = None,
	against_name: str | None = None,
	remarks: str | None = None,
):
	"""Record and post an expense or deposit on the caller's open shift."""
	_require_van_user()
	_require_capability("uses_shifts", "record cash movements")
	if movement_type not in MOVEMENT_TYPES:
		frappe.throw(f"Movement Type must be one of: {', '.join(MOVEMENT_TYPES)}")
	if flt(amount) <= 0:
		frappe.throw("Amount must be greater than zero.")

	user = frappe.session.user
	opening_shift = _open_shift_or_throw(user)
	config = _get_driver_config(required=False) or {}

	doc = frappe.new_doc("Van Cash Movement")
	doc.movement_type = movement_type
	doc.amount = flt(amount)
	doc.driver = user
	doc.opening_shift = opening_shift
	doc.van_profile = config.get("name")
	doc.company = config.get("company")
	doc.expense_account = expense_account or None
	doc.against_name = (against_name or "").strip() or None
	doc.remarks = (remarks or "").strip() or None
	# Authorization is done above (van user, own open shift) and by validate()
	# (profile rules); the driver role itself holds only read on this doctype.
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return _serialize(doc)


@frappe.whitelist()
def get_shift_cash_movements(opening_shift: str | None = None):
	"""Submitted movements on a shift: the caller's own open shift by default. A manager
	can pass any shift."""
	_require_van_user()
	user = frappe.session.user
	if not opening_shift:
		opening_shift = _find_open_shift(user, today_only=False)
		if not opening_shift:
			return []
	driver = frappe.db.get_value("Van Shift Opening", opening_shift, "driver")
	if driver != user and user != "Administrator" and not _is_manager():
		frappe.throw("You can only view cash movements on your own shift.", frappe.PermissionError)
	return [
		_serialize(frappe.get_doc("Van Cash Movement", row.name))
		for row in frappe.get_all(
			"Van Cash Movement",
			filters={"opening_shift": opening_shift, "docstatus": 1},
			fields=["name"],
			order_by="creation desc",
		)
	]


@frappe.whitelist()
def cancel_cash_movement(name: str):
	"""Managers only: reverse a movement (and its Journal Entry). Only while the shift
	is still open — once closed, the closing's expected cash already counted it."""
	_manager_only()
	doc = frappe.get_doc("Van Cash Movement", name)
	if doc.docstatus != 1:
		frappe.throw("Only a submitted cash movement can be cancelled.")
	status = frappe.db.get_value("Van Shift Opening", doc.opening_shift, "status")
	if status != "Open":
		frappe.throw("This shift is already closed. Reopen the shift before cancelling its cash movements.")
	doc.flags.ignore_permissions = True
	doc.cancel()
	return {"name": doc.name, "docstatus": doc.docstatus}
