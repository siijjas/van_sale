import json
import frappe
from van_sale.van_sale.utils import (
	_ensure_driver_mode_allowed,
	_get_allowed_payment_modes,
	_default_company,
	_require_van_user,
	_validate_customer_access,
	_is_manager,
)


@frappe.whitelist()
def get_outstanding_invoices(customer: str):
	_require_van_user()
	_validate_customer_access(customer)
	return frappe.get_list(
		"Sales Invoice",
		filters={
			"customer": customer,
			"docstatus": 1,
			"outstanding_amount": [">", 0]
		},
		fields=["name", "posting_date", "grand_total", "outstanding_amount"],
		order_by="posting_date asc"
	)


@frappe.whitelist()
def get_payment_modes():
	_require_van_user()
	modes = frappe.get_list("Mode of Payment", filters={"enabled": 1}, fields=["name", "type"])
	allowed_modes = _get_allowed_payment_modes(user=frappe.session.user, all_modes=False)
	if allowed_modes is not None:
		modes = [mode for mode in modes if mode["name"] in allowed_modes]
	# Sort: Cash first, then alphabetically
	return sorted(modes, key=lambda x: (x["name"] != "Cash", x["name"]))


@frappe.whitelist()
def get_customer_summary(customer: str):
	_require_van_user()
	_validate_customer_access(customer)
	company = _default_company()

	# Outstanding balance
	outstanding = frappe.db.sql(
		"""
		select sum(debit - credit) as outstanding
		from `tabGL Entry`
		where party_type = 'Customer'
			and party = %s
			and company = %s
		""",
		(customer, company),
		as_dict=1
	)
	outstanding_balance = (outstanding and outstanding[0].outstanding) or 0.0

	# Last invoice
	last_invoice = frappe.db.sql(
		"""
		select name, posting_date, grand_total
		from `tabSales Invoice`
		where customer = %s
			and docstatus = 1
			and company = %s
		order by posting_date desc, creation desc
		limit 1
		""",
		(customer, company),
		as_dict=1
	)

	# Last payment
	last_payment = frappe.db.sql(
		"""
		select name, posting_date, paid_amount
		from `tabPayment Entry`
		where party_type = 'Customer'
			and party = %s
			and payment_type = 'Receive'
			and docstatus = 1
			and company = %s
		order by posting_date desc, creation desc
		limit 1
		""",
		(customer, company),
		as_dict=1
	)

	return {
		"outstanding_balance": outstanding_balance,
		"last_invoice": last_invoice[0] if last_invoice else None,
		"last_payment": last_payment[0] if last_payment else None
	}


@frappe.whitelist()
def create_payment_entry(
	customer: str,
	mode_of_payment: str,
	paid_amount: float,
	references: str,
	sales_order: str = None,
):
	_require_van_user()
	_validate_customer_access(customer)
	# Enforce the per-driver payment mode allowlist
	_ensure_driver_mode_allowed(mode_of_payment)

	refs = json.loads(references)
	company = _default_company()

	curr = frappe.get_cached_value("Company", company, "default_currency")
	paid_to = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": company},
		"default_account"
	)
	if not paid_to:
		frappe.throw(
			f"No default account found for mode of payment {mode_of_payment} in company {company}"
		)

	from erpnext.accounts.party import get_party_account
	party_account = get_party_account("Customer", customer, company)

	pe = frappe.new_doc("Payment Entry")
	# Payment Entry is a standard ERPNext financial doctype. Van Sales Driver does not hold
	# broad ERPNext accounts permissions. Authorization is enforced explicitly above via
	# _require_van_user(), _validate_customer_access(), and _ensure_driver_mode_allowed().
	# flags.ignore_permissions lets us insert/submit without requiring the Accounts User role.
	pe.flags.ignore_permissions = True
	pe.payment_type = "Receive"
	pe.party_type = "Customer"
	pe.party = customer
	pe.mode_of_payment = mode_of_payment
	pe.paid_amount = paid_amount
	pe.received_amount = paid_amount
	pe.target_exchange_rate = 1.0
	pe.company = company
	pe.paid_to = paid_to
	pe.paid_to_account_currency = frappe.db.get_value("Account", paid_to, "account_currency")
	pe.paid_from = party_account
	pe.paid_from_account_currency = (
		frappe.db.get_value("Account", party_account, "account_currency") or curr
	)

	# Allocate to Sales Invoices
	for ref in refs:
		pe.append(
			"references",
			{
				"reference_doctype": "Sales Invoice",
				"reference_name": ref["name"],
				"total_amount": ref["grand_total"],
				"outstanding_amount": ref["outstanding_amount"],
				"allocated_amount": ref["allocated_amount"],
			},
		)

	# Link to Sales Order for advance payment
	if sales_order:
		so_doc = frappe.get_doc("Sales Order", sales_order)
		pe.append(
			"references",
			{
				"reference_doctype": "Sales Order",
				"reference_name": sales_order,
				"total_amount": so_doc.grand_total,
				"allocated_amount": paid_amount,
			},
		)

	pe.insert()
	pe.submit()
	return pe.name


@frappe.whitelist()
def get_customer_ledger(customer: str, from_date: str = None, to_date: str = None):
	_require_van_user()
	_validate_customer_access(customer)
	company = _default_company()

	filters = {
		"party_type": "Customer",
		"party": customer,
		"company": company,
		"is_cancelled": 0,
		"voucher_type": ["in", ["Sales Invoice", "Payment Entry", "Sales Order", "Journal Entry"]],
	}

	if from_date and to_date:
		filters["posting_date"] = ["between", [from_date, to_date]]
	elif from_date:
		filters["posting_date"] = [">=", from_date]
	elif to_date:
		filters["posting_date"] = ["<=", to_date]

	opening_balance = 0.0
	if from_date:
		before_filters = {
			"party_type": "Customer",
			"party": customer,
			"company": company,
			"is_cancelled": 0,
			"posting_date": ["<", from_date],
			"voucher_type": ["in", ["Sales Invoice", "Payment Entry", "Sales Order", "Journal Entry"]],
		}
		result = frappe.get_all(
			"GL Entry",
			filters=before_filters,
			fields=["sum(debit) as debit", "sum(credit) as credit"]
		)
		if result:
			opening_balance = (result[0].debit or 0.0) - (result[0].credit or 0.0)

	entries = frappe.get_all(
		"GL Entry",
		filters=filters,
		fields=["posting_date", "voucher_type", "voucher_no", "debit", "credit", "account"],
		order_by="posting_date asc, creation asc"
	)

	return {
		"opening_balance": opening_balance,
		"entries": entries
	}


@frappe.whitelist()
def get_route_expenses():
	_require_van_user()
	user = frappe.session.user
	from frappe.utils import nowdate
	today = nowdate()

	return frappe.get_all(
		"Van Expense Log",
		filters={"driver": user, "expense_date": today},
		fields=["name", "expense_type", "amount", "notes", "creation"],
		order_by="creation desc"
	)


@frappe.whitelist()
def submit_route_expense(expense_type: str, amount: float, notes: str = None):
	_require_van_user()
	user = frappe.session.user
	from frappe.utils import nowdate
	today = nowdate()

	doc = frappe.new_doc("Van Expense Log")
	doc.driver = user
	doc.expense_date = today
	doc.expense_type = expense_type
	doc.amount = float(amount)
	doc.notes = notes

	# Van Sales Driver role has create permission on Van Expense Log — no bypass needed.
	doc.insert()
	return doc.name
