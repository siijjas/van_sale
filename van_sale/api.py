import frappe
from frappe.utils import nowdate


def _default_naming_series():
	for field in frappe.get_meta("Sales Order").fields:
		if field.fieldname == "naming_series" and field.default:
			return field.default
	return "SO-"


def _default_company():
	return frappe.defaults.get_defaults().get("company") or frappe.db.get_default("company")


def _apply_defaults(doc):
	if not doc.company:
		doc.company = _default_company()
	if not doc.naming_series:
		doc.naming_series = _default_naming_series()
	if not doc.order_type:
		doc.order_type = "Sales"
	if not doc.transaction_date:
		doc.transaction_date = nowdate()
	if not doc.delivery_date:
		doc.delivery_date = doc.transaction_date


def _ensure_payment_schedule(doc):
	if doc.payment_schedule:
		return
	grand = doc.grand_total or doc.net_total or 0
	if not grand:
		return
	doc.append(
		"payment_schedule",
		{
			"due_date": doc.delivery_date or doc.transaction_date or nowdate(),
			"invoice_portion": 100,
			"payment_amount": grand,
			"base_payment_amount": grand,
			"description": "Full Payment",
		},
	)


@frappe.whitelist()
def submit_sales_order(name: str):
	doc = frappe.get_doc("Sales Order", name)
	if not doc.has_permission("read"):
		frappe.throw("Not permitted", frappe.PermissionError)
		
	_apply_defaults(doc)
	doc.run_method("set_missing_values")
	doc.run_method("calculate_taxes_and_totals")
	_ensure_payment_schedule(doc)
	doc.save()
	doc.submit()
	return doc.as_dict()


@frappe.whitelist()
def get_outstanding_invoices(customer: str):
	if not frappe.has_permission("Customer", doc=customer):
		frappe.throw("Not permitted", frappe.PermissionError)
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
	modes = frappe.get_list("Mode of Payment", filters={"enabled": 1}, fields=["name", "type"])
	# Sort: Cash first, then alphabetically
	return sorted(modes, key=lambda x: (x["name"] != "Cash", x["name"]))


@frappe.whitelist()
def get_sales_orders(customer: str):
	if not frappe.has_permission("Customer", doc=customer):
		frappe.throw("Not permitted", frappe.PermissionError)
	company = _default_company()
	
	return frappe.db.sql(
		"""
		select 
			name, 
			transaction_date, 
			if(base_rounded_total, base_rounded_total, base_grand_total) as grand_total,
			advance_paid,
			per_billed
		from `tabSales Order`
		where customer = %s 
			and docstatus = 1
			and company = %s
			and status != 'Closed'
			and if(base_rounded_total, base_rounded_total, base_grand_total) > advance_paid
			and abs(100 - per_billed) > 0.01
		order by transaction_date desc
		limit 50
		""",
		(customer, company),
		as_dict=1,
	)


@frappe.whitelist()
def get_customer_summary(customer: str):
	if not frappe.has_permission("Customer", doc=customer):
		frappe.throw("Not permitted", frappe.PermissionError)
	company = _default_company()
	
	# Get outstanding balance
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
	
	# Get last invoice
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
	
	# Get last payment
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
def create_payment_entry(customer: str, mode_of_payment: str, paid_amount: float, references: str, sales_order: str = None):
	if not frappe.has_permission("Customer", doc=customer):
		frappe.throw("Not permitted", frappe.PermissionError)
	if not frappe.has_permission("Mode of Payment", doc=mode_of_payment):
		frappe.throw("Not permitted", frappe.PermissionError)
	import json

	refs = json.loads(references)
	pe = frappe.new_doc("Payment Entry")
	pe.payment_type = "Receive"
	pe.party_type = "Customer"
	pe.party = customer
	pe.mode_of_payment = mode_of_payment
	pe.paid_amount = paid_amount
	pe.received_amount = paid_amount
	pe.target_exchange_rate = 1.0

	# Set company and default accounts
	company = _default_company()
	pe.company = company
	
	# Fetch default accounts logic
	curr = frappe.get_cached_value("Company", company, "default_currency")
	paid_to = frappe.db.get_value(
		"Mode of Payment Account", 
		{"parent": mode_of_payment, "company": company}, 
		"default_account"
	)
	if not paid_to:
		frappe.throw(f"No default account found for mode of payment {mode_of_payment} in company {company}")
		
	pe.paid_to = paid_to
	pe.paid_to_account_currency = frappe.db.get_value("Account", paid_to, "account_currency")
	
	# Party Account (Debtors)
	from erpnext.accounts.party import get_party_account
	party_account = get_party_account("Customer", customer, company)
	
	pe.paid_from = party_account
	pe.paid_from_account_currency = frappe.db.get_value("Account", party_account, "account_currency") or curr

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
	
	pe.insert(ignore_permissions=True)
	pe.submit()
	return pe.name


@frappe.whitelist()
def get_customer_ledger(customer: str, from_date: str = None, to_date: str = None):
	if not frappe.has_permission("Customer", doc=customer):
		frappe.throw("Not permitted", frappe.PermissionError)
	company = _default_company()
	
	filters = {
		"party_type": "Customer",
		"party": customer,
		"company": company,
		"is_cancelled": 0
	}
	
	if from_date:
		filters["posting_date"] = [">=", from_date]
	if to_date:
		if "posting_date" in filters:
			filters["posting_date"].append("<=")
			filters["posting_date"].append(to_date)
		else:
			filters["posting_date"] = ["<=", to_date]
			
	opening_balance = 0.0
	if from_date:
		before_filters = {
			"party_type": "Customer",
			"party": customer,
			"company": company,
			"is_cancelled": 0,
			"posting_date": ["<", from_date]
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
def get_daily_summary():
	user = frappe.session.user
	today = nowdate()
	
	# Sales Orders
	sos = frappe.get_list(
		"Sales Order",
		filters={
			"docstatus": ["!=", 2],
			"transaction_date": today
		},
		fields=["grand_total"]
	)
	
	# Payment Entries
	pes = frappe.get_list(
		"Payment Entry",
		filters={
			"docstatus": 1,
			"posting_date": today,
			"payment_type": "Receive"
		},
		fields=["paid_amount"]
	)
	
	return {
		"sales_orders": {
			"count": len(sos),
			"total": sum(d.grand_total for d in sos)
		},
		"payments": {
			"count": len(pes),
			"total": sum(d.paid_amount for d in pes)
		}
	}


@frappe.whitelist()
def get_daily_log(doctype: str):
	user = frappe.session.user
	today = nowdate()
	
	if doctype == "Sales Order":
		return frappe.get_list(
			"Sales Order",
			filters={
				"docstatus": ["!=", 2],
				"transaction_date": today
			},
			fields=["name", "customer_name", "grand_total", "status", "transaction_date"],
			order_by="creation desc"
		)
	elif doctype == "Payment Entry":
		return frappe.get_list(
			"Payment Entry",
			filters={
				"docstatus": 1,
				"posting_date": today,
				"payment_type": "Receive"
			},
			fields=["name", "party_name", "paid_amount", "status", "posting_date", "mode_of_payment"],
			order_by="creation desc"
		)
	
	return []
