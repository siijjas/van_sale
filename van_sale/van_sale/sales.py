import frappe
from frappe.utils import nowdate, flt
from van_sale.van_sale.utils import (
	_default_company,
	_require_van_user,
	_validate_customer_access,
	_is_manager,
	_get_driver_config,
)


def _apply_defaults(doc):
	if not doc.company:
		doc.company = _default_company()
	if not hasattr(doc, "naming_series") or not doc.naming_series:
		from van_sale.van_sale.utils import _default_naming_series
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


def _check_daily_credit_limit(order_grand_total: float):
	"""Raise if submitting this order would exceed the driver's daily credit limit.

	The check sums all today's Sales Orders (draft + submitted) for the current user
	and compares against the configured daily_credit_limit. Managers are exempt.
	"""
	if _is_manager():
		return
	config = _get_driver_config(required=False)
	if not config:
		return
	limit = float(config.get("daily_credit_limit") or 0)
	if not limit:
		return

	today = nowdate()
	user = frappe.session.user
	existing = frappe.get_list(
		"Sales Order",
		filters={"docstatus": ["!=", 2], "transaction_date": today, "owner": user},
		fields=["grand_total"],
	)
	existing_total = sum(d.grand_total for d in existing)
	if existing_total + order_grand_total > limit:
		frappe.throw(
			f"This order would exceed your daily credit limit of {limit}. "
			f"Today's total so far: {existing_total}.",
			frappe.PermissionError,
		)


def _check_rate_change_allowed(doc):
	"""Raise if any item rate deviates from its price list rate and the driver's profile
	has allow_rate_change disabled. Managers and drivers without a profile are exempt."""
	if _is_manager():
		return
	config = _get_driver_config(required=False)
	if not config or config.get("allow_rate_change"):
		return
	for item in doc.items:
		price_list_rate = item.price_list_rate or 0
		if price_list_rate and abs((item.rate or 0) - price_list_rate) > 0.001:
			frappe.throw(
				f"Rate change is not allowed for this driver profile. "
				f"Item '{item.item_code}' has rate {item.rate} but price list rate is {price_list_rate}.",
				frappe.PermissionError,
			)


@frappe.whitelist()
def submit_sales_order(name: str):
	_require_van_user()
	doc = frappe.get_doc("Sales Order", name)
	if not doc.has_permission("read"):
		frappe.throw("Not permitted", frappe.PermissionError)
	# Non-managers may only submit their own orders
	if not _is_manager() and doc.owner != frappe.session.user:
		frappe.throw("You can only submit your own sales orders.", frappe.PermissionError)

	_check_daily_credit_limit(doc.grand_total or 0)
	_check_rate_change_allowed(doc)
	_apply_defaults(doc)
	doc.run_method("set_missing_values")
	doc.run_method("calculate_taxes_and_totals")
	_ensure_payment_schedule(doc)
	doc.save()
	doc.submit()
	return doc.as_dict()


@frappe.whitelist()
def get_sales_orders(customer: str):
	_require_van_user()
	_validate_customer_access(customer)
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
def get_daily_summary():
	_require_van_user()
	user = frappe.session.user
	today = nowdate()

	# Sales Orders
	sos = frappe.get_list(
		"Sales Order",
		filters={
			"docstatus": ["!=", 2],
			"transaction_date": today,
			"owner": user,
		},
		fields=["grand_total"]
	)

	# Payment Entries
	pes = frappe.get_list(
		"Payment Entry",
		filters={
			"docstatus": 1,
			"posting_date": today,
			"payment_type": "Receive",
			"owner": user,
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
	_require_van_user()
	user = frappe.session.user
	today = nowdate()

	if doctype == "Sales Order":
		return frappe.get_list(
			"Sales Order",
			filters={
				"docstatus": ["!=", 2],
				"transaction_date": today,
				"owner": user,
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
				"payment_type": "Receive",
				"owner": user,
			},
			fields=["name", "party_name", "paid_amount", "status", "posting_date", "mode_of_payment"],
			order_by="creation desc"
		)

	return []


@frappe.whitelist()
def create_sales_invoice(sales_order: str):
	_require_van_user()
	so = frappe.get_doc("Sales Order", sales_order)
	if not _is_manager() and so.owner != frappe.session.user:
		frappe.throw("You can only invoice your own sales orders.", frappe.PermissionError)
	if so.docstatus != 1:
		frappe.throw("Sales Order must be submitted before creating an invoice.")
	if (so.per_billed or 0) >= 100:
		frappe.throw("This sales order has already been fully invoiced.")

	config = _get_driver_config(required=False)
	van_warehouse = config.get("van_warehouse") if config else None

	sinv = frappe.new_doc("Sales Invoice")
	sinv.customer = so.customer
	sinv.company = so.company
	sinv.posting_date = nowdate()
	sinv.selling_price_list = so.selling_price_list
	sinv.currency = so.currency
	sinv.conversion_rate = so.conversion_rate or 1
	sinv.update_stock = 1
	if van_warehouse:
		sinv.set_warehouse = van_warehouse
	if so.taxes_and_charges:
		sinv.taxes_and_charges = so.taxes_and_charges

	for so_item in so.items:
		remaining_qty = flt(so_item.qty) - flt(so_item.returned_qty or 0)
		if remaining_qty <= 0:
			continue
		sinv.append("items", {
			"item_code": so_item.item_code,
			"item_name": so_item.item_name,
			"qty": remaining_qty,
			"uom": so_item.uom or so_item.stock_uom,
			"stock_uom": so_item.stock_uom,
			"rate": so_item.rate,
			"sales_order": so.name,
			"so_detail": so_item.name,
			"cost_center": getattr(so_item, "cost_center", None),
			"warehouse": van_warehouse,
		})

	sinv.run_method("set_missing_values")
	sinv.run_method("calculate_taxes_and_totals")

	# Sales Invoice is a standard ERPNext financial doctype. Van Sales Driver does not hold
	# broad ERPNext accounting permissions, so we use flags.ignore_permissions after
	# explicitly authorizing the user above via _require_van_user().
	sinv.flags.ignore_permissions = True
	sinv.insert()
	sinv.submit()
	return sinv.name


@frappe.whitelist()
def create_sales_return(customer: str, items):
	_require_van_user()
	_validate_customer_access(customer)

	from van_sale.van_sale.inventory import _parse_stock_transfer_lines

	config = _get_driver_config()
	lines = items if isinstance(items, list) else _parse_stock_transfer_lines(items)

	doc = frappe.new_doc("Sales Invoice")
	doc.customer = customer
	doc.is_return = 1
	doc.update_stock = 1
	doc.set_warehouse = config["van_warehouse"]
	_apply_defaults(doc)

	for idx, row in enumerate(lines, start=1):
		item_code = row.get("item_code")
		qty = abs(float(row.get("qty", 0)))
		if not item_code or qty <= 0:
			continue
		doc.append("items", {
			"item_code": item_code,
			"qty": -qty,
		})

	doc.run_method("set_missing_values")
	doc.run_method("calculate_taxes_and_totals")

	# Sales Invoice is a standard ERPNext financial doctype. Van Sales Driver does not hold
	# broad ERPNext accounting permissions, so we use flags.ignore_permissions after
	# explicitly authorizing the user above via _require_van_user() and _validate_customer_access().
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc.name


# NOTE: The end-of-day reconciliation endpoints (get_eod_summary / submit_eod_report)
# have been superseded by the shift lifecycle in van_sale.van_sale.shift. The
# Van EOD Report doctype is retained for historical records only.
