"""
Van Sale shift lifecycle API.

Replaces the single date-keyed Van EOD Report with a POS Awesome-style
Opening -> Closing shift pair:

- Opening records the start-of-day cash float (per payment mode) and a start time.
- Closing aggregates the day's transactions (by date + owner, matching the old
  EOD behaviour) and reconciles each payment mode: opening float, expected
  (from collections), counted (entered by the driver) and the difference.

This is the "lightweight" model: transactions are NOT stamped with the shift and
selling is NOT blocked when no shift is open. Aggregation is purely by date, at
close time — but each closing keeps a durable `transactions` reference list (the
exact Sales Order/Payment Entry/Van Expense Log names it summed) so the totals can
be re-verified later even if a same-day record changes after the shift closes.
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


def _default_cash_mode(cash_modes: set[str], user: str) -> str:
	"""Pick a cash-type Mode of Payment to use when the driver has no cash
	collections/opening float yet. Prefers the Van Profile's own explicit
	`default_cash_mode` (mirrors POS Profile's `posa_cash_mode_of_payment` in
	posawesome), then falls back to one of the driver's allowed payment modes,
	then the generic "Cash" record. Avoiding a hardcoded "Cash" here matters
	because a driver restricted to their own Mode of Payment (e.g.
	"Van - 01 - Cash") doesn't have access to a generic "Cash" record with a
	different name.
	"""
	config = _get_driver_config(user=user, required=False)
	if config and config.get("default_cash_mode") in cash_modes:
		return config["default_cash_mode"]

	allowed = _get_allowed_payment_modes(user=user)
	if allowed:
		for mode in allowed:
			if mode in cash_modes:
				return mode
	return "Cash"


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


def _todays_payment_entries(user: str) -> list:
	"""Today's submitted receive Payment Entries for the user."""
	return frappe.get_all(
		"Payment Entry",
		filters={
			"docstatus": 1,
			"posting_date": nowdate(),
			"payment_type": "Receive",
			"owner": user,
		},
		fields=["name", "mode_of_payment", "paid_amount", "posting_date"],
	)


def _collections_by_mode(entries: list) -> dict[str, float]:
	"""Today's Payment Entry collections, summed per mode."""
	totals: dict[str, float] = {}
	for row in entries:
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
	payment_entries = _todays_payment_entries(user)
	collections = _collections_by_mode(payment_entries)

	# Sales = submitted Sales Orders for today (single source of truth, matching the
	# superseded get_eod_summary). Fetched itemized (not a raw sum()) so the exact
	# records can be recorded on the closing doc as an audit trail (see `transactions`
	# below) — recomputing "today's records by this owner" after the fact can't be
	# re-verified later if a record changes, but a durable reference list can.
	sales_orders = frappe.get_all(
		"Sales Order",
		filters={"docstatus": 1, "transaction_date": today, "owner": user},
		fields=["name", "grand_total", "transaction_date"],
	)
	total_sales = flt(sum(flt(so.grand_total) for so in sales_orders))

	expenses = frappe.get_all(
		"Van Expense Log",
		filters={"driver": user, "expense_date": today},
		fields=["name", "amount", "expense_date"],
	)
	total_expenses = flt(sum(flt(e.amount) for e in expenses))

	transactions = (
		[
			{
				"reference_doctype": "Sales Order",
				"reference_name": so.name,
				"posting_date": so.transaction_date,
				"amount": flt(so.grand_total),
			}
			for so in sales_orders
		]
		+ [
			{
				"reference_doctype": "Payment Entry",
				"reference_name": pe.name,
				"posting_date": pe.posting_date,
				"amount": flt(pe.paid_amount),
			}
			for pe in payment_entries
		]
		+ [
			{
				"reference_doctype": "Van Expense Log",
				"reference_name": e.name,
				"posting_date": e.expense_date,
				"amount": flt(e.amount),
			}
			for e in expenses
		]
	)

	cash_modes = _cash_modes()
	modes = list(dict.fromkeys(list(opening_floats) + list(collections)))
	if not any(m in cash_modes or m == "Cash" for m in modes):
		# Ensure a cash row exists so expenses have somewhere to land. Prefer the
		# driver's own allowed cash mode (e.g. "Van - 01 - Cash") over the generic
		# "Cash" literal: a driver restricted via User Permissions to their own
		# Mode of Payment can't even reference the generic "Cash" record, and
		# doing so silently fails doc-level permission checks on submit.
		modes.insert(0, _default_cash_mode(cash_modes, user))

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
		"transactions": transactions,
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

	# Van Shift Opening is created/submitted entirely under application control
	# (authorization already enforced above via _require_van_user() and the
	# per-mode allowlist check), matching how Payment Entry/Sales Invoice/Stock
	# Entry are handled elsewhere in this app — rather than relying on a Custom
	# DocPerm + has_permission hook to grant exactly the right slice of write/
	# submit access, which is easy to get subtly wrong (see _has_shift_permission).
	doc.flags.ignore_permissions = True
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

	for txn in computed["transactions"]:
		doc.append("transactions", txn)

	# Same rationale as open_shift(): authorization is already enforced above
	# (_require_van_user(), the "own shift only" ownership check, and driver-scoped
	# amounts recomputed server-side by _compute_closing), so we bypass the DocPerm/
	# has_permission layer entirely rather than depending on it to line up exactly.
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()  # on_submit flips the opening shift to Closed
	return {"name": doc.name, "net_difference": net_difference}
