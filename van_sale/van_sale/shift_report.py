"""
X and Y shift reports.

- X report: a read-only snapshot of a shift that is still open. It runs the same
  aggregation close_shift() would (shift._compute_closing) without writing
  anything, so a driver can check their numbers as often as they like mid-route.
- Y report: the final report of a closed shift, read from its Van Shift Closing.
  Totals and the per-mode reconciliation come straight off the closing doc, and the
  breakdowns are built from the closing's frozen `transactions` list, so the report
  reads the same whenever it is reprinted.

Both share one shape (see _build_report), rendered by ShiftReportView.vue in the app
and by the "Van Shift X Report" / "Van Shift Y Report" print formats, which call
get_shift_report_for_print() through the jinja hook.
"""

import frappe
from frappe.utils import cint, flt, now_datetime

from van_sale.van_sale.shift import _compute_closing, _find_open_shift, _serialize_opening
from van_sale.van_sale.utils import _is_manager, _require_van_user


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _check_access(doc):
	if frappe.session.user != "Administrator" and not _is_manager() and doc.driver != frappe.session.user:
		frappe.throw("You can only view reports for your own shifts.", frappe.PermissionError)


def _names(transactions: list[dict], doctype: str) -> list[str]:
	return [t["reference_name"] for t in transactions if t["reference_doctype"] == doctype]


def _amounts(transactions: list[dict], doctype: str) -> dict[str, float]:
	return {t["reference_name"]: flt(t["amount"]) for t in transactions if t["reference_doctype"] == doctype}


# How _compute_closing() selects each doctype for a driver's day: (date field, owner
# field, extra filters, amount field).
_LEGACY_SOURCES = {
	"Sales Order": ("transaction_date", "owner", {"docstatus": 1}, "grand_total"),
	"Sales Invoice": ("posting_date", "owner", {"docstatus": 1}, "grand_total"),
	"Payment Entry": ("posting_date", "owner", {"docstatus": 1, "payment_type": "Receive"}, "paid_amount"),
	"Van Expense Log": ("expense_date", "driver", {}, "amount"),
}


def _legacy_transactions(doctypes: list[str], driver: str, shift_date, period_end) -> list[dict]:
	"""Rebuild references for closings that predate them being stored on the closing.

	Closings made before `transactions` existed hold none at all, and ones made before
	invoices were recorded hold no Sales Invoice rows. Matched the way _compute_closing()
	selects them, by date and owner, limited to records created before the shift closed.
	"""
	transactions = []
	for doctype in doctypes:
		date_field, owner_field, filters, amount_field = _LEGACY_SOURCES[doctype]
		filters = {**filters, date_field: shift_date, owner_field: driver}
		if period_end:
			filters["creation"] = ["<=", period_end]
		transactions += [
			{"reference_doctype": doctype, "reference_name": row.name, "amount": flt(row.get(amount_field))}
			for row in frappe.get_all(doctype, filters=filters, fields=["name", amount_field])
		]
	return transactions


def _item_rows(sales_orders: list[str], returns: list[str]) -> list[dict]:
	"""Per-item quantities sold (on the shift's Sales Orders) and returned (credit notes).

	Quantities are in stock UOM so lines sold in different UOMs add up; amounts are
	net_amount, i.e. after any order-level discount and before tax.
	"""
	items: dict[str, dict] = {}

	def add(parenttype: str, parents: list[str], qty_key: str, amount_key: str):
		if not parents:
			return
		for row in frappe.get_all(
			f"{parenttype} Item",
			filters={"parent": ["in", parents], "parenttype": parenttype},
			fields=["item_code", "item_name", "stock_uom", "stock_qty", "net_amount"],
			order_by="idx asc",
		):
			entry = items.setdefault(
				row.item_code,
				{
					"item_code": row.item_code,
					"item_name": row.item_name,
					"uom": row.stock_uom,
					"sold_qty": 0.0,
					"sold_amount": 0.0,
					"returned_qty": 0.0,
					"returned_amount": 0.0,
				},
			)
			# Credit notes carry negative quantities and amounts.
			entry[qty_key] += abs(flt(row.stock_qty))
			entry[amount_key] += abs(flt(row.net_amount))

	add("Sales Order", sales_orders, "sold_qty", "sold_amount")
	add("Sales Invoice", returns, "returned_qty", "returned_amount")

	rows = sorted(items.values(), key=lambda r: (-r["sold_qty"], r["item_name"] or r["item_code"]))
	for row in rows:
		row["net_qty"] = row["sold_qty"] - row["returned_qty"]
	return rows


def _build_report(report_type: str, header: dict, totals: dict, reconciliation: list[dict], transactions: list[dict]) -> dict:
	"""Assemble the shared X/Y report shape from a shift's transaction references.

	`transactions` is the reference list shift._compute_closing() produces (and a
	closing stores). Amounts are taken from it rather than re-read, so a Y report
	shows what the shift actually closed on.
	"""
	order_names = _names(transactions, "Sales Order")
	payment_amounts = _amounts(transactions, "Payment Entry")
	expense_amounts = _amounts(transactions, "Van Expense Log")
	invoice_amounts = _amounts(transactions, "Sales Invoice")

	# Invoices vs credit notes.
	return_flags = {}
	if invoice_amounts:
		return_flags = {
			r.name: cint(r.is_return)
			for r in frappe.get_all(
				"Sales Invoice", filters={"name": ["in", list(invoice_amounts)]}, fields=["name", "is_return"]
			)
		}
	invoices = [n for n in invoice_amounts if not return_flags.get(n)]
	returns = [n for n in invoice_amounts if return_flags.get(n)]
	invoiced_total = sum(invoice_amounts[n] for n in invoices)
	returns_total = abs(sum(invoice_amounts[n] for n in returns))

	# Collections, grouped by mode in first-seen order.
	collections: dict[str, dict] = {}
	if payment_amounts:
		for pe in frappe.get_all(
			"Payment Entry",
			filters={"name": ["in", list(payment_amounts)]},
			fields=["name", "mode_of_payment"],
			order_by="creation asc",
		):
			mode = pe.mode_of_payment or "Cash"
			row = collections.setdefault(mode, {"mode_of_payment": mode, "count": 0, "amount": 0.0})
			row["count"] += 1
			row["amount"] += payment_amounts[pe.name]

	expenses = []
	if expense_amounts:
		expenses = [
			{
				"name": e.name,
				"expense_type": e.expense_type,
				"notes": e.notes,
				"amount": expense_amounts[e.name],
			}
			for e in frappe.get_all(
				"Van Expense Log",
				filters={"name": ["in", list(expense_amounts)]},
				fields=["name", "expense_type", "notes"],
				order_by="creation asc",
			)
		]

	return {
		"report_type": report_type,
		"generated_at": str(now_datetime()),
		"shift": header,
		"totals": {
			**totals,
			"sales_orders_count": len(order_names),
			"invoices_count": len(invoices),
			"invoiced_total": invoiced_total,
			"returns_count": len(returns),
			"returns_total": returns_total,
			"net_invoiced": invoiced_total - returns_total,
			"payments_count": len(payment_amounts),
			"expenses_count": len(expense_amounts),
		},
		"payment_reconciliation": reconciliation,
		"collections": list(collections.values()),
		"expenses": expenses,
		"items": _item_rows(order_names, returns),
	}


def _header(doc, opening_shift: str, closing_shift: str | None) -> dict:
	return {
		"opening_shift": opening_shift,
		"closing_shift": closing_shift,
		"driver": doc.driver,
		"driver_name": frappe.utils.get_fullname(doc.driver),
		"van_profile": doc.van_profile,
		"company": doc.company,
		"currency": frappe.get_cached_value("Company", doc.company, "default_currency") if doc.company else None,
		"shift_date": str(doc.shift_date),
		"period_start": str(doc.period_start) if doc.period_start else None,
		"period_end": str(doc.period_end) if doc.get("period_end") else None,
		"status": doc.status,
		"notes": doc.notes,
	}


# ─── Builders ─────────────────────────────────────────────────────────────────

def build_x_report(opening_doc) -> dict:
	"""Live snapshot of an open shift. Writes nothing."""
	if opening_doc.docstatus != 1 or opening_doc.status != "Open":
		frappe.throw("The X report is only available while a shift is open. Closed shifts have a Y report.")

	computed = _compute_closing(_serialize_opening(opening_doc))
	totals = {
		key: computed[key]
		for key in ("total_sales", "total_collections", "total_expenses", "total_opening_float", "expected_cash")
	}
	reconciliation = [
		{**row, "closing_amount": None, "difference": None} for row in computed["rows"]
	]
	return _build_report(
		"X", _header(opening_doc, opening_doc.name, None), totals, reconciliation, computed["transactions"]
	)


def build_y_report(closing_doc) -> dict:
	"""Final report of a closed shift, from its Van Shift Closing."""
	if closing_doc.docstatus != 1:
		frappe.throw("The Y report is only available for a submitted shift closing.")

	transactions = [
		{"reference_doctype": t.reference_doctype, "reference_name": t.reference_name, "amount": flt(t.amount)}
		for t in closing_doc.transactions
	]
	recorded = {t["reference_doctype"] for t in transactions}
	missing = list(_LEGACY_SOURCES) if not transactions else [] if "Sales Invoice" in recorded else ["Sales Invoice"]
	transactions += _legacy_transactions(missing, closing_doc.driver, closing_doc.shift_date, closing_doc.period_end)

	totals = {
		key: flt(closing_doc.get(key))
		for key in (
			"total_sales", "total_collections", "total_expenses", "total_opening_float",
			"expected_cash", "net_difference",
		)
	}
	reconciliation = [
		{
			"mode_of_payment": r.mode_of_payment,
			"opening_amount": flt(r.opening_amount),
			"expected_amount": flt(r.expected_amount),
			"closing_amount": flt(r.closing_amount),
			"difference": flt(r.difference),
		}
		for r in closing_doc.payment_reconciliation
	]
	return _build_report(
		"Y", _header(closing_doc, closing_doc.opening_shift, closing_doc.name), totals, reconciliation, transactions
	)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_x_report(opening_shift: str | None = None):
	"""X report for the given open shift, or the caller's own open shift today."""
	_require_van_user()
	if not opening_shift:
		opening_shift = _find_open_shift(frappe.session.user)
		if not opening_shift:
			frappe.throw("No open shift found. Open a shift to run an X report.")
	doc = frappe.get_doc("Van Shift Opening", opening_shift)
	_check_access(doc)
	return build_x_report(doc)


@frappe.whitelist()
def get_y_report(closing_shift: str):
	_require_van_user()
	doc = frappe.get_doc("Van Shift Closing", closing_shift)
	_check_access(doc)
	return build_y_report(doc)


@frappe.whitelist()
def get_shift_closings(limit: int = 30):
	"""Recent closed shifts to pick a Y report from: the caller's own, or everyone's for a manager."""
	_require_van_user()
	filters = {"docstatus": 1}
	if frappe.session.user != "Administrator" and not _is_manager():
		filters["driver"] = frappe.session.user
	rows = frappe.get_all(
		"Van Shift Closing",
		filters=filters,
		fields=[
			"name", "opening_shift", "driver", "shift_date", "period_start", "period_end",
			"total_sales", "total_collections", "net_difference",
		],
		order_by="period_end desc, creation desc",
		limit_page_length=min(max(cint(limit), 1), 100),
	)
	for row in rows:
		row["driver_name"] = frappe.utils.get_fullname(row.driver)
	return rows


def get_shift_report_for_print(doctype: str, name: str) -> dict | None:
	"""Jinja method (see hooks.py) backing the X/Y print formats.

	Returns None when the document can't produce that report (an X report of a shift
	that has since closed, or a draft/cancelled closing), so the template can say so
	rather than failing the whole print.
	"""
	doc = frappe.get_doc(doctype, name)
	if not (frappe.has_permission(doctype, "print", doc) or frappe.has_permission(doctype, "read", doc)):
		frappe.throw("Not permitted to print this shift.", frappe.PermissionError)
	if doctype == "Van Shift Opening":
		if doc.docstatus != 1 or doc.status != "Open":
			return None
		return build_x_report(doc)
	if doctype == "Van Shift Closing":
		if doc.docstatus != 1:
			return None
		return build_y_report(doc)
	frappe.throw(f"No shift report for {doctype}.")
