"""
Van Sale shift lifecycle API.

Replaces the single date-keyed Van EOD Report with a POS Awesome-style
Opening -> Closing shift pair:

- Opening records the start-of-day cash float (per payment mode) and a start time.
- Closing aggregates the day's transactions (by date + owner, matching the old
  EOD behaviour) and reconciles each payment mode: opening float, expected
  (from collections), counted (entered by the driver) and the difference.

This is the "lightweight" model: transactions are NOT stamped with the shift and
selling is NOT blocked when no shift is open. Aggregation is purely by date.
"""

import json

import frappe
from frappe.utils import flt, now_datetime, nowdate

from van_sale.van_sale.utils import (
	_default_company,
	_get_allowed_payment_modes,
	_get_driver_config,
	_require_van_user,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _coerce(value):
	"""Accept either a JSON string (from the REST layer) or an already-parsed value."""
	if isinstance(value, str):
		return json.loads(value) if value.strip() else []
	return value or []


def _cash_modes() -> set[str]:
	"""Names of all Mode of Payment records of type 'Cash'."""
	return {
		row.name
		for row in frappe.get_all(
			"Mode of Payment", filters={"type": "Cash"}, fields=["name"]
		)
	}


def _find_open_shift(user: str) -> str | None:
	"""Return the name of the user's open Van Shift Opening for today, if any."""
	return frappe.db.get_value(
		"Van Shift Opening",
		{
			"driver": user,
			"shift_date": nowdate(),
			"status": "Open",
			"docstatus": 1,
		},
		"name",
	)


def _collections_by_mode(user: str) -> dict[str, float]:
	"""Today's submitted receive Payment Entries for the user, summed per mode."""
	rows = frappe.get_all(
		"Payment Entry",
		filters={
			"docstatus": 1,
			"posting_date": nowdate(),
			"payment_type": "Receive",
			"owner": user,
		},
		fields=["mode_of_payment", "paid_amount"],
	)
	totals: dict[str, float] = {}
	for row in rows:
		mode = row.mode_of_payment or "Cash"
		totals[mode] = totals.get(mode, 0.0) + flt(row.paid_amount)
	return totals


def _compute_closing(opening: dict) -> dict:
	"""Build the per-mode reconciliation rows and headline totals for a closing.

	The driver-entered counted amounts are NOT part of this — they are layered on
	top in get_shift_closing_summary (default = expected) and close_shift (actual).
	"""
	user = frappe.session.user
	today = nowdate()

	opening_floats: dict[str, float] = {
		row.get("mode_of_payment"): flt(row.get("opening_amount"))
		for row in (opening.get("balance_details") or [])
		if row.get("mode_of_payment")
	}
	collections = _collections_by_mode(user)

	total_expenses = flt(
		frappe.db.get_value(
			"Van Expense Log",
			{"driver": user, "expense_date": today},
			"sum(amount)",
		)
	)

	# Sales = submitted Sales Orders for today (single source of truth, matching the
	# superseded get_eod_summary).
	total_sales = flt(
		frappe.db.get_value(
			"Sales Order",
			{"docstatus": 1, "transaction_date": today, "owner": user},
			"sum(grand_total)",
		)
	)

	cash_modes = _cash_modes()
	modes = list(dict.fromkeys(list(opening_floats) + list(collections)))
	if not any(m in cash_modes or m == "Cash" for m in modes):
		# Ensure a Cash row exists so expenses have somewhere to land.
		modes.insert(0, "Cash")

	# Expenses are paid out of the cash drawer — deduct from the first cash mode.
	cash_row_mode = next((m for m in modes if m in cash_modes or m == "Cash"), None)

	rows = []
	for mode in modes:
		opening_amount = opening_floats.get(mode, 0.0)
		expected = opening_amount + collections.get(mode, 0.0)
		if mode == cash_row_mode:
			expected -= total_expenses
		rows.append(
			{
				"mode_of_payment": mode,
				"opening_amount": opening_amount,
				"expected_amount": expected,
			}
		)

	expected_cash = next(
		(r["expected_amount"] for r in rows if r["mode_of_payment"] == cash_row_mode),
		0.0,
	)

	return {
		"rows": rows,
		"total_sales": total_sales,
		"total_collections": sum(collections.values()),
		"total_expenses": total_expenses,
		"total_opening_float": sum(opening_floats.values()),
		"expected_cash": expected_cash,
	}


def _serialize_opening(doc) -> dict:
	return {
		"name": doc.name,
		"driver": doc.driver,
		"shift_date": str(doc.shift_date),
		"status": doc.status,
		"company": doc.company,
		"van_profile": doc.van_profile,
		"period_start": str(doc.period_start) if doc.period_start else None,
		"opening_float": flt(doc.opening_float),
		"balance_details": [
			{"mode_of_payment": r.mode_of_payment, "opening_amount": flt(r.opening_amount)}
			for r in (doc.balance_details or [])
		],
		"notes": doc.notes,
	}


# ─── Endpoints ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_active_shift():
	"""Return the current user's open shift for today, or None."""
	_require_van_user()
	name = _find_open_shift(frappe.session.user)
	if not name:
		return None
	return _serialize_opening(frappe.get_doc("Van Shift Opening", name))


@frappe.whitelist()
def open_shift(balance_details, notes: str = None):
	"""Create and submit a Van Shift Opening with per-mode opening floats."""
	_require_van_user()
	user = frappe.session.user

	if _find_open_shift(user):
		frappe.throw("You already have an open shift for today. Close it before opening a new one.")

	config = _get_driver_config(required=False) or {}
	doc = frappe.new_doc("Van Shift Opening")
	doc.driver = user
	doc.shift_date = nowdate()
	doc.status = "Open"
	doc.company = config.get("company") or _default_company()
	doc.van_profile = config.get("name")
	doc.period_start = now_datetime()
	if notes:
		doc.notes = notes

	allowed = _get_allowed_payment_modes(user=user)
	for row in _coerce(balance_details):
		mode = row.get("mode_of_payment")
		if not mode:
			continue
		if allowed is not None and mode not in allowed:
			frappe.throw(f"Mode of payment {mode} is not allowed for this driver")
		doc.append(
			"balance_details",
			{"mode_of_payment": mode, "opening_amount": flt(row.get("opening_amount"))},
		)

	doc.insert()
	doc.submit()
	return _serialize_opening(doc)


@frappe.whitelist()
def get_shift_closing_summary():
	"""Pre-fill the closing screen: per-mode reconciliation rows + headline totals.

	Counted (closing_amount) defaults to expected; the driver edits it on screen.
	"""
	_require_van_user()
	name = _find_open_shift(frappe.session.user)
	if not name:
		frappe.throw("No open shift found. Open a shift before closing one.")

	opening = _serialize_opening(frappe.get_doc("Van Shift Opening", name))
	computed = _compute_closing(opening)

	for row in computed["rows"]:
		row["closing_amount"] = row["expected_amount"]
		row["difference"] = 0.0

	return {
		"opening_shift": name,
		"period_start": opening["period_start"],
		"payment_reconciliation": computed["rows"],
		"total_sales": computed["total_sales"],
		"total_collections": computed["total_collections"],
		"total_expenses": computed["total_expenses"],
		"total_opening_float": computed["total_opening_float"],
		"expected_cash": computed["expected_cash"],
	}


@frappe.whitelist()
def close_shift(opening_shift: str, reconciliation, notes: str = None):
	"""Create and submit a Van Shift Closing, reconciling counted vs expected per mode."""
	_require_van_user()
	user = frappe.session.user

	opening_doc = frappe.get_doc("Van Shift Opening", opening_shift)
	if opening_doc.driver != user:
		frappe.throw("You can only close your own shift.", frappe.PermissionError)
	if opening_doc.status != "Open":
		frappe.throw("This shift is already closed.")

	opening = _serialize_opening(opening_doc)
	# Recompute opening/expected server-side; never trust the client for those.
	computed = _compute_closing(opening)
	expected_by_mode = {r["mode_of_payment"]: r for r in computed["rows"]}

	# Driver-entered counted amounts, keyed by mode.
	counted_by_mode = {
		row.get("mode_of_payment"): flt(row.get("closing_amount"))
		for row in _coerce(reconciliation)
		if row.get("mode_of_payment")
	}

	doc = frappe.new_doc("Van Shift Closing")
	doc.opening_shift = opening_shift
	doc.driver = user
	doc.shift_date = nowdate()
	doc.status = "Closed"
	doc.company = opening_doc.company
	doc.van_profile = opening_doc.van_profile
	doc.period_start = opening_doc.period_start
	doc.period_end = now_datetime()
	doc.total_sales = computed["total_sales"]
	doc.total_collections = computed["total_collections"]
	doc.total_expenses = computed["total_expenses"]
	doc.total_opening_float = computed["total_opening_float"]
	doc.expected_cash = computed["expected_cash"]
	if notes:
		doc.notes = notes

	net_difference = 0.0
	for mode, base in expected_by_mode.items():
		counted = counted_by_mode.get(mode, base["expected_amount"])
		difference = counted - base["expected_amount"]
		net_difference += difference
		doc.append(
			"payment_reconciliation",
			{
				"mode_of_payment": mode,
				"opening_amount": base["opening_amount"],
				"expected_amount": base["expected_amount"],
				"closing_amount": counted,
				"difference": difference,
			},
		)
	doc.net_difference = net_difference

	doc.insert()
	doc.submit()  # on_submit flips the opening shift to Closed
	return {"name": doc.name, "net_difference": net_difference}
