"""
Van Sale shift lifecycle API.

A POS Awesome-style Opening -> Closing shift pair:

- Opening records the start-of-shift cash float (per payment mode) and a start time.
- Closing aggregates the shift's activity and reconciles each payment mode: opening
  float, expected (from collections), counted (entered by the driver) and the
  difference, flagged against the Van Profile's variance tolerance.

Aggregation is by the shift's time window, not by calendar date: everything the
driver created between the opening's period_start and the moment of closing (the
closing's period_end) belongs to the shift. ERPNext documents are NOT stamped with
the shift (a product decision: no custom fields on Sales Order / Sales Invoice /
Payment Entry), so "created by this driver inside the window" is the attribution.
Each closing keeps a durable `transactions` reference list (the exact Sales Order /
Sales Invoice / Payment Entry / Van Cash Movement names it summed) so the totals
can be re-verified later even if a record changes after the shift closes.

Selling is only blocked without an open shift when the Van Profile turns on
require_open_shift (see require_open_shift()). Anything the driver does on the
shift's date outside the window (with that setting off) is reported to them on the
closing screen as "outside this shift" rather than silently dropped.

A shift left open past midnight is closed as the day it was opened, and blocks
opening a new shift until it is. Managers can close any driver's shift and reopen
a closed one (which cancels the closing and lets the shift continue).
"""

import json

import frappe
from frappe.utils import flt, formatdate, get_datetime, getdate, now_datetime, nowdate

from van_sale.van_sale.doctype.van_shift_closing.van_shift_closing import variance_status
from van_sale.van_sale.utils import (
	_default_company,
	_get_allowed_payment_modes,
	_get_driver_config,
	_is_manager,
	_manager_only,
	_require_capability,
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


def _find_open_shift(user: str, today_only: bool = True) -> str | None:
	"""The user's open Van Shift Opening.

	By default only one opened today. With today_only=False, the oldest one still open
	from any day: a shift left open past midnight is what the driver has to close
	before they can open another.
	"""
	filters = {"driver": user, "status": "Open", "docstatus": 1}
	if today_only:
		filters["shift_date"] = nowdate()
	return frappe.db.get_value(
		"Van Shift Opening", filters, "name", order_by="shift_date asc, creation asc"
	)


def _check_can_close(opening_doc):
	"""A driver closes their own shift; a manager can close anyone's (e.g. a shift
	the driver forgot, or a driver who is away)."""
	user = frappe.session.user
	if opening_doc.driver != user and user != "Administrator" and not _is_manager():
		frappe.throw("You can only close your own shift.", frappe.PermissionError)
	if opening_doc.docstatus != 1 or opening_doc.status != "Open":
		frappe.throw("This shift is already closed.")


def require_open_shift(action: str, user: str | None = None):
	"""Enforce the Van Profile's require_open_shift setting before a driver records
	sales, collections, returns or expenses.

	Only a shift opened today counts: one left open from an earlier day has to be
	closed first, otherwise today's activity would land on no shift at all.
	`action` completes the sentence "Open your shift before you ...".
	"""
	user = user or frappe.session.user
	config = _get_driver_config(user=user, required=False)
	# A profile without shifts (typically Field Sales) never has one to require.
	if not config or not config.get("use_shifts") or not config.get("require_open_shift"):
		return
	if _find_open_shift(user):
		return
	stale = _find_open_shift(user, today_only=False)
	if stale:
		since = formatdate(frappe.db.get_value("Van Shift Opening", stale, "shift_date"))
		frappe.throw(
			f"Close your shift from {since} and open today's before you {action}.",
			title="Shift required",
		)
	frappe.throw(f"Open your shift before you {action}.", title="Shift required")


def _shift_window(opening: dict) -> tuple:
	"""(start, end) of the shift: period_start to period_end, or to now while open.

	An opening with no period_start (none exist since shifts got a start time, but
	be safe) starts at midnight of its shift date.
	"""
	start = opening.get("period_start")
	start = get_datetime(start) if start else get_datetime(f"{opening.get('shift_date') or nowdate()} 00:00:00")
	end = opening.get("period_end")
	end = get_datetime(end) if end else now_datetime()
	return start, end


def _in_window(user: str, start, end, **extra) -> dict:
	return {"owner": user, "creation": ["between", [start, end]], **extra}


def _shift_payment_entries(user: str, start, end) -> list:
	"""The user's submitted receive Payment Entries created inside the window."""
	return frappe.get_all(
		"Payment Entry",
		filters=_in_window(user, start, end, docstatus=1, payment_type="Receive"),
		fields=["name", "mode_of_payment", "paid_amount", "posting_date"],
	)


def _collections_by_mode(entries: list) -> dict[str, float]:
	"""Collections summed per mode."""
	totals: dict[str, float] = {}
	for row in entries:
		mode = row.mode_of_payment or "Cash"
		totals[mode] = totals.get(mode, 0.0) + flt(row.paid_amount)
	return totals


def _order_taxes(order_names: list[str]) -> list[dict]:
	"""Tax rows of the shift's Sales Orders, grouped by account head and rate (the
	POS Closing Shift taxes table)."""
	if not order_names:
		return []
	grouped: dict[tuple, dict] = {}
	for row in frappe.get_all(
		"Sales Taxes and Charges",
		filters={"parent": ["in", order_names], "parenttype": "Sales Order"},
		fields=["account_head", "rate", "base_tax_amount", "tax_amount"],
		order_by="idx asc",
	):
		key = (row.account_head, flt(row.rate))
		entry = grouped.setdefault(key, {"account_head": row.account_head, "rate": flt(row.rate), "amount": 0.0})
		entry["amount"] += flt(row.base_tax_amount if row.base_tax_amount is not None else row.tax_amount)
	return list(grouped.values())


def _order_quantity(order_names: list[str]) -> float:
	if not order_names:
		return 0.0
	rows = frappe.get_all(
		"Sales Order Item",
		filters={"parent": ["in", order_names], "parenttype": "Sales Order"},
		fields=["sum(stock_qty) as qty"],
	)
	return flt(rows[0].qty) if rows else 0.0


def _draft_orders(user: str, start, end) -> list[dict]:
	"""Draft Sales Orders the driver made during the shift and has not submitted.
	They are not in any total; the closing screen warns about them (flag only)."""
	return [
		{
			"name": row.name,
			"customer": row.customer,
			"customer_name": row.customer_name,
			"grand_total": flt(row.grand_total),
			"creation": str(row.creation),
		}
		for row in frappe.get_all(
			"Sales Order",
			filters=_in_window(user, start, end, docstatus=0),
			fields=["name", "customer", "customer_name", "grand_total", "creation"],
			order_by="creation asc",
		)
	]


def _unclaimed(doctype: str, rows: list) -> list:
	"""Drop records a submitted closing has already summed. Shift windows of one driver
	normally never overlap, but a reopened shift's window runs on to its new close and
	could otherwise re-count what a later shift closed on; a cancelled closing (the one
	reopen cancels) is not a claim."""
	if not rows:
		return []
	claimed = {
		r.reference_name
		for r in frappe.db.sql(
			"""select t.reference_name from `tabVan Shift Transaction` t
			join `tabVan Shift Closing` c on c.name = t.parent and c.docstatus = 1
			where t.parenttype = 'Van Shift Closing' and t.reference_doctype = %(doctype)s
				and t.reference_name in %(names)s""",
			{"doctype": doctype, "names": tuple(r.name for r in rows)},
			as_dict=True,
		)
	}
	return [r for r in rows if r.name not in claimed]


def _outside_window(user: str, shift_date, start) -> dict:
	"""Submitted orders and collections the driver made on the shift's date before the
	shift opened, and that no other closing has picked up. With require_open_shift
	off this can happen; the closing screen says so instead of silently dropping them.
	"""
	def unclaimed(doctype: str, date_field: str, amount_field: str, **extra) -> list:
		return _unclaimed(
			doctype,
			frappe.get_all(
				doctype,
				filters={"owner": user, "docstatus": 1, date_field: shift_date, "creation": ["<", start], **extra},
				fields=["name", amount_field],
			),
		)

	orders = unclaimed("Sales Order", "transaction_date", "grand_total")
	payments = unclaimed("Payment Entry", "posting_date", "paid_amount", payment_type="Receive")
	return {
		"orders_count": len(orders),
		"orders_total": flt(sum(flt(r.grand_total) for r in orders)),
		"payments_count": len(payments),
		"payments_total": flt(sum(flt(r.paid_amount) for r in payments)),
	}


def _compute_closing(opening: dict) -> dict:
	"""Build the per-mode reconciliation rows and headline totals for a closing.

	The driver-entered counted amounts are NOT part of this — they are layered on
	top in get_shift_closing_summary (default = expected) and close_shift (actual).
	"""
	# The opening's own driver and window rather than the session user and today: the
	# same thing in close_shift()/get_shift_closing_summary(), which only ever reach an
	# opening the caller owns, but it lets a manager's shift summary (shift_report.py)
	# compute another driver's open shift correctly.
	user = opening.get("driver") or frappe.session.user
	shift_date = opening.get("shift_date") or nowdate()
	start, end = _shift_window(opening)

	opening_floats: dict[str, float] = {
		row.get("mode_of_payment"): flt(row.get("opening_amount"))
		for row in (opening.get("balance_details") or [])
		if row.get("mode_of_payment")
	}
	payment_entries = _unclaimed("Payment Entry", _shift_payment_entries(user, start, end))
	collections = _collections_by_mode(payment_entries)

	# Sales = submitted Sales Orders created inside the window (single source of truth).
	# Fetched itemized (not a raw sum()) so the exact records can be recorded on the
	# closing doc as an audit trail (see `transactions` below).
	sales_orders = _unclaimed(
		"Sales Order",
		frappe.get_all(
			"Sales Order",
			filters=_in_window(user, start, end, docstatus=1),
			fields=["name", "grand_total", "net_total", "total_taxes_and_charges", "transaction_date"],
		),
	)
	order_names = [so.name for so in sales_orders]
	total_sales = flt(sum(flt(so.grand_total) for so in sales_orders))
	net_total = flt(sum(flt(so.net_total) for so in sales_orders))
	total_taxes = flt(sum(flt(so.total_taxes_and_charges) for so in sales_orders))

	# Legacy expense logs (no accounting, no shift link: matched by date) plus cash
	# movements, which carry the shift link and are matched by it: both leave the
	# drawer with less.
	expenses = frappe.get_all(
		"Van Expense Log",
		filters={"driver": user, "expense_date": shift_date},
		fields=["name", "amount", "expense_date"],
	)
	cash_movements = (
		frappe.get_all(
			"Van Cash Movement",
			filters={"opening_shift": opening.get("name"), "docstatus": 1},
			fields=["name", "movement_type", "amount", "posting_date"],
		)
		if opening.get("name")
		else []
	)
	total_expenses = flt(
		sum(flt(e.amount) for e in expenses)
		+ sum(flt(m.amount) for m in cash_movements if m.movement_type == "Expense")
	)
	total_deposits = flt(sum(flt(m.amount) for m in cash_movements if m.movement_type == "Deposit"))

	# Invoices and credit notes don't feed the sales total (counted on the Sales Order),
	# but recording them lets the closing report break down invoiced vs returned from
	# the same frozen list as everything else, and returns get their own total.
	sales_invoices = _unclaimed(
		"Sales Invoice",
		frappe.get_all(
			"Sales Invoice",
			filters=_in_window(user, start, end, docstatus=1),
			fields=["name", "grand_total", "posting_date", "is_return"],
		),
	)
	total_returns = flt(abs(sum(flt(si.grand_total) for si in sales_invoices if si.is_return)))

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
				"reference_doctype": "Sales Invoice",
				"reference_name": si.name,
				"posting_date": si.posting_date,
				"amount": flt(si.grand_total),
			}
			for si in sales_invoices
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
		+ [
			{
				"reference_doctype": "Van Cash Movement",
				"reference_name": m.name,
				"posting_date": m.posting_date,
				"amount": flt(m.amount),
			}
			for m in cash_movements
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

	# Expenses and deposits are paid out of the cash drawer — deduct from the first cash mode.
	cash_row_mode = next((m for m in modes if m in cash_modes or m == "Cash"), None)

	rows = []
	for mode in modes:
		opening_amount = opening_floats.get(mode, 0.0)
		expected = opening_amount + collections.get(mode, 0.0)
		if mode == cash_row_mode:
			expected -= total_expenses + total_deposits
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
		"period_start": str(start),
		"period_end": str(end),
		"rows": rows,
		"total_sales": total_sales,
		"net_total": net_total,
		"total_taxes": total_taxes,
		"total_quantity": _order_quantity(order_names),
		"total_returns": total_returns,
		"taxes": _order_taxes(order_names),
		"total_collections": sum(collections.values()),
		"total_expenses": total_expenses,
		"total_deposits": total_deposits,
		"total_opening_float": sum(opening_floats.values()),
		"expected_cash": expected_cash,
		"transactions": transactions,
		"draft_orders": _draft_orders(user, start, end),
		"outside_window": _outside_window(user, shift_date, start),
	}


def _variance_tolerance(van_profile: str | None) -> float:
	if not van_profile:
		return 0.0
	return flt(frappe.db.get_value("Van Profile", van_profile, "variance_tolerance"))


def _serialize_opening(doc) -> dict:
	return {
		"name": doc.name,
		"driver": doc.driver,
		"shift_date": str(doc.shift_date),
		"status": doc.status,
		"company": doc.company,
		"van_profile": doc.van_profile,
		"period_start": str(doc.period_start) if doc.period_start else None,
		"period_end": str(doc.period_end) if doc.get("period_end") else None,
		"closing_shift": doc.get("closing_shift"),
		"opening_float": flt(doc.opening_float),
		"balance_details": [
			{"mode_of_payment": r.mode_of_payment, "opening_amount": flt(r.opening_amount)}
			for r in (doc.balance_details or [])
		],
		"notes": doc.notes,
		"is_stale": doc.status == "Open" and getdate(doc.shift_date) < getdate(nowdate()),
	}


# ─── Endpoints ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_active_shift():
	"""The current user's open shift, or None.

	A shift left open from an earlier day comes back (with is_stale) ahead of anything
	else, so the app sends the driver to close it before they carry on.
	"""
	_require_van_user()
	name = _find_open_shift(frappe.session.user, today_only=False)
	if not name:
		return None
	return _serialize_opening(frappe.get_doc("Van Shift Opening", name))


@frappe.whitelist()
def open_shift(balance_details, notes: str = None):
	"""Create and submit a Van Shift Opening with per-mode opening floats."""
	_require_van_user()
	_require_capability("uses_shifts", "open a shift")
	user = frappe.session.user

	pending = _find_open_shift(user, today_only=False)
	if pending:
		pending_date = frappe.db.get_value("Van Shift Opening", pending, "shift_date")
		if getdate(pending_date) == getdate(nowdate()):
			frappe.throw("You already have an open shift for today. Close it before opening a new one.")
		frappe.throw(
			f"You have an unclosed shift from {formatdate(pending_date)}. Close it before opening a new one."
		)

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
def get_shift_closing_summary(opening_shift: str | None = None):
	"""Pre-fill the closing screen: per-mode reconciliation rows + headline totals.

	Without opening_shift, the caller's own oldest open shift (a forgotten one from an
	earlier day first). A manager passes opening_shift to close a driver's shift.
	Counted (closing_amount) defaults to expected; the driver edits it on screen.
	"""
	_require_van_user()
	name = opening_shift or _find_open_shift(frappe.session.user, today_only=False)
	if not name:
		frappe.throw("No open shift found. Open a shift before closing one.")
	opening_doc = frappe.get_doc("Van Shift Opening", name)
	_check_can_close(opening_doc)

	opening = _serialize_opening(opening_doc)
	computed = _compute_closing(opening)

	for row in computed["rows"]:
		row["closing_amount"] = row["expected_amount"]
		row["difference"] = 0.0

	return {
		"opening_shift": name,
		"driver": opening_doc.driver,
		"driver_name": frappe.utils.get_fullname(opening_doc.driver),
		"shift_date": opening["shift_date"],
		"is_stale": opening["is_stale"],
		"period_start": opening["period_start"],
		"payment_reconciliation": computed["rows"],
		"total_sales": computed["total_sales"],
		"net_total": computed["net_total"],
		"total_taxes": computed["total_taxes"],
		"total_quantity": computed["total_quantity"],
		"total_returns": computed["total_returns"],
		"taxes": computed["taxes"],
		"total_collections": computed["total_collections"],
		"total_expenses": computed["total_expenses"],
		"total_deposits": computed["total_deposits"],
		"total_opening_float": computed["total_opening_float"],
		"expected_cash": computed["expected_cash"],
		"variance_tolerance": _variance_tolerance(opening_doc.van_profile),
		"draft_orders": computed["draft_orders"],
		"outside_window": computed["outside_window"],
	}


@frappe.whitelist()
def close_shift(opening_shift: str, reconciliation, notes: str = None):
	"""Create and submit a Van Shift Closing, reconciling counted vs expected per mode."""
	_require_van_user()
	user = frappe.session.user

	opening_doc = frappe.get_doc("Van Shift Opening", opening_shift)
	_check_can_close(opening_doc)

	# The window closes now: everything the driver created up to this instant belongs
	# to the shift, and the closing stores the same period_end it was computed with.
	opening = _serialize_opening(opening_doc)
	opening["period_end"] = str(now_datetime())
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
	# The shift's own driver and date, not whoever closes it or when: a manager can close
	# a driver's shift, and a forgotten shift closes as the day it was opened.
	doc.driver = opening_doc.driver
	doc.shift_date = opening_doc.shift_date
	if user != opening_doc.driver:
		doc.closed_by = user
	doc.status = "Closed"
	doc.company = opening_doc.company
	doc.van_profile = opening_doc.van_profile
	doc.period_start = opening_doc.period_start
	doc.period_end = get_datetime(opening["period_end"])
	doc.total_sales = computed["total_sales"]
	doc.net_total = computed["net_total"]
	doc.total_taxes = computed["total_taxes"]
	doc.total_quantity = computed["total_quantity"]
	doc.total_returns = computed["total_returns"]
	doc.total_collections = computed["total_collections"]
	doc.total_expenses = computed["total_expenses"]
	doc.total_deposits = computed["total_deposits"]
	doc.total_opening_float = computed["total_opening_float"]
	doc.expected_cash = computed["expected_cash"]
	doc.variance_tolerance = _variance_tolerance(opening_doc.van_profile)
	doc.draft_orders_count = len(computed["draft_orders"])
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

	for tax in computed["taxes"]:
		doc.append("taxes", tax)
	for txn in computed["transactions"]:
		doc.append("transactions", txn)

	# Same rationale as open_shift(): authorization is already enforced above
	# (_require_van_user(), _check_can_close() — own shift, or a manager — and driver-scoped
	# amounts recomputed server-side by _compute_closing), so we bypass the DocPerm/
	# has_permission layer entirely rather than depending on it to line up exactly.
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()  # on_submit flips the opening shift to Closed and links this closing
	return {
		"name": doc.name,
		"net_difference": net_difference,
		"variance_status": doc.variance_status,
		"variance_tolerance": flt(doc.variance_tolerance),
		"draft_orders_count": doc.draft_orders_count,
	}


@frappe.whitelist()
def reopen_shift(closing_shift: str):
	"""Managers only: cancel a closing so the shift is open again.

	The opening goes back to Open with no end time, so the driver can carry on (or
	the manager can fix the counted amounts) and close it again; the new closing
	spans the whole window from the original opening to the new close. Refused while
	the driver has another shift open, since two open shifts can't both be "today's".
	"""
	_require_van_user()
	_manager_only()
	closing = frappe.get_doc("Van Shift Closing", closing_shift)
	if closing.docstatus != 1:
		frappe.throw("Only a submitted shift closing can be reopened.")
	other = frappe.db.get_value(
		"Van Shift Opening",
		{"driver": closing.driver, "status": "Open", "docstatus": 1, "name": ["!=", closing.opening_shift]},
		"name",
	)
	if other:
		frappe.throw(
			f"{frappe.utils.get_fullname(closing.driver)} already has an open shift ({other}). "
			"Close it before reopening this one."
		)
	closing.flags.ignore_permissions = True
	closing.cancel()  # on_cancel reopens the Van Shift Opening
	return _serialize_opening(frappe.get_doc("Van Shift Opening", closing.opening_shift))
