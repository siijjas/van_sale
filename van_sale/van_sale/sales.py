import json
import frappe
from frappe.utils import nowdate, flt
from van_sale.van_sale.utils import (
	_coerce_check,
	_default_company,
	_ensure_driver_mode_allowed,
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


DEFAULT_SELLING_PRICE_LIST = "Standard Selling"


def _catalog_reference_rate(item_code: str, customer: str | None, price_list: str | None) -> float:
	"""The rate the catalog would have quoted for this item.

	Mirrors the client's resolution order in listItems() (frontend/src/api/frappe.ts):
	a customer-specific Item Price, then the driver's own price list, then Standard
	Selling, then any selling price, and finally Item.standard_rate. The rate guard has
	to walk the same ladder — checking only the profile's price list rejects sales at
	the very price the driver was shown.
	"""
	def lookup(filters):
		return flt(frappe.db.get_value("Item Price", filters, "price_list_rate"))

	if customer:
		rate = lookup({"item_code": item_code, "customer": customer, "selling": 1})
		if rate:
			return rate
	if price_list:
		rate = lookup({"item_code": item_code, "price_list": price_list, "selling": 1})
		if rate:
			return rate
	rate = lookup({"item_code": item_code, "price_list": DEFAULT_SELLING_PRICE_LIST, "selling": 1})
	if rate:
		return rate
	rate = lookup({"item_code": item_code, "selling": 1})
	if rate:
		return rate
	return flt(frappe.db.get_value("Item", item_code, "standard_rate"))


def _check_rate_change_allowed(doc):
	"""Raise if any item rate deviates from its price list rate and the driver's profile
	has allow_rate_change disabled. Managers and drivers without a profile are exempt."""
	if _is_manager():
		return
	config = _get_driver_config(required=False)
	if not config or config.get("allow_rate_change"):
		return
	for item in doc.items:
		# Accept any rate the catalog could legitimately have quoted. Comparing against a
		# single reference is wrong in both directions: price_list_rate alone is 0 on a
		# site with no Item Price rows, making the guard a no-op (a driver could sell a
		# 15.00 item for 1.00), while falling back to standard_rate alone rejects the
		# price the driver was actually shown whenever the catalog sourced it from a
		# different tier than the profile's own price list.
		candidates = {
			flt(item.price_list_rate),
			_catalog_reference_rate(item.item_code, doc.customer, doc.selling_price_list),
		}
		candidates = {rate for rate in candidates if rate}
		if not candidates:
			continue
		if not any(abs(flt(item.rate) - rate) <= 0.001 for rate in candidates):
			expected = ", ".join(f"{rate:g}" for rate in sorted(candidates))
			frappe.throw(
				f"Rate change is not allowed for this driver profile. "
				f"Item '{item.item_code}' has rate {item.rate} but the catalog price is {expected}.",
				frappe.PermissionError,
			)


def _check_discount_change_allowed(doc):
	"""Raise if an overall discount is applied and the driver's profile has
	allow_discount_change disabled. Managers and drivers without a profile are exempt.

	The discount value itself (additional_discount_percentage / discount_amount) is
	trusted from the draft here only to decide whether to block the submit — the
	actual grand_total is always recomputed from it via calculate_taxes_and_totals()
	below, so a driver can't under-total an order by setting a discount and then
	having it silently ignored; either the discount is allowed and applied, or it's
	rejected outright.
	"""
	if _is_manager():
		return
	config = _get_driver_config(required=False)
	if not config or config.get("allow_discount_change"):
		return
	if flt(doc.additional_discount_percentage) or flt(doc.discount_amount):
		frappe.throw(
			"Discounts are not allowed for this driver profile.",
			frappe.PermissionError,
		)


def _coerce_order_lines(items):
	"""Normalise the items payload into [{item_code, qty, rate}] dicts."""
	lines = items if isinstance(items, list) else json.loads(items)
	out = []
	for row in lines:
		item_code = row.get("item_code")
		qty = flt(row.get("qty"))
		if not item_code or qty <= 0:
			continue
		out.append({"item_code": item_code, "qty": qty, "rate": flt(row.get("rate"))})
	if not out:
		frappe.throw("Add at least one item with a quantity before saving this order.")
	return out


def _apply_order_payload(doc, customer, items, discount_percent, discount_amount):
	"""Build a Sales Order server-side from a driver's cart.

	The frontend used to assemble the whole document — company, price list, currency,
	payment schedule and every total — and POST it to frappe.client.insert. That meant
	the Van Sales Driver role needed create/write on Sales Order through plain
	/api/resource, so anything holding that role could write orders without passing a
	single van_sale check, and the totals were whatever the client said they were.

	Here the client sends only customer, items and an optional discount; everything
	else comes from the driver's Van Profile and ERPNext computes the totals.
	"""
	config = _get_driver_config(required=False) or {}
	lines = _coerce_order_lines(items)

	doc.customer = customer
	doc.transaction_date = doc.transaction_date or nowdate()
	doc.delivery_date = doc.delivery_date or doc.transaction_date
	doc.order_type = doc.order_type or "Sales"
	doc.company = doc.company or config.get("company") or _default_company()

	# Sell from the driver's own van. Neither the old client-built document nor the
	# first version of this endpoint set a warehouse, so every line fell through to the
	# item/company default — typically the source warehouse. That reserved stock in the
	# wrong place and disagreed with create_sales_invoice(), which does bill against the
	# van warehouse, so the invoice could then fail stock validation for an item that is
	# sitting in the van but not in the default warehouse.
	if config.get("van_warehouse"):
		doc.set_warehouse = config["van_warehouse"]

	if config.get("selling_price_list"):
		doc.selling_price_list = config["selling_price_list"]
	if config.get("currency"):
		doc.currency = config["currency"]

	# An empty taxes_and_charges on the profile means "no tax template" — clear any
	# rows ERPNext may have defaulted in, rather than leaving a stale template behind.
	doc.taxes_and_charges = config.get("taxes_and_charges") or None
	if not doc.taxes_and_charges:
		doc.set("taxes", [])

	# Percentage takes priority over a flat amount, matching ERPNext's own
	# set_discount_amount() precedence. Both are handed to ERPNext rather than
	# pre-multiplied here, so calculate_taxes_and_totals() owns the arithmetic.
	doc.apply_discount_on = config.get("apply_discount_on") or "Grand Total"
	percent = flt(discount_percent)
	if percent > 0:
		doc.additional_discount_percentage = percent
		doc.discount_amount = 0
	else:
		doc.additional_discount_percentage = 0
		doc.discount_amount = flt(discount_amount)

	doc.set("items", [])
	for row in lines:
		line = {
			"item_code": row["item_code"],
			"qty": row["qty"],
			"delivery_date": doc.delivery_date,
		}
		if row["rate"] > 0:
			line["rate"] = row["rate"]
		doc.append("items", line)

	doc.run_method("set_missing_values")
	# Same fallback as create_sales_return(): with no Item Price row set_missing_values()
	# leaves rate 0, which would both zero the order and trip _check_rate_change_allowed()
	# against the standard_rate the catalog actually quoted.
	for line in doc.items:
		if not flt(line.rate):
			line.rate = flt(frappe.db.get_value("Item", line.item_code, "standard_rate"))
	# Clamp before the totals are computed. The client clamps for display, but the whole
	# point of building the order server-side is not to trust it: an unclamped amount
	# produces a negative grand total, and a percentage over 100 does the same.
	doc.additional_discount_percentage = min(max(flt(doc.additional_discount_percentage), 0), 100)
	line_total = sum(flt(line.qty) * flt(line.rate) for line in doc.items)
	doc.discount_amount = min(max(flt(doc.discount_amount), 0), line_total)

	doc.run_method("calculate_taxes_and_totals")

	# Enforced here as well as at submit: a rate or discount the driver's profile
	# forbids is now rejected when the draft is saved, not only when it is confirmed.
	_check_rate_change_allowed(doc)
	_check_discount_change_allowed(doc)
	_ensure_payment_schedule(doc)

	# Sales Order writes go through this endpoint precisely so the Van Sales Driver
	# role does not need create/write on the doctype. Authorization is _require_van_user()
	# plus _validate_customer_access() in the callers below.
	doc.flags.ignore_permissions = True
	return doc


@frappe.whitelist()
def create_sales_order(customer: str, items, discount_percent: float = 0, discount_amount: float = 0):
	"""Create a draft Sales Order from the driver's cart."""
	_require_van_user()
	_validate_customer_access(customer)

	doc = frappe.new_doc("Sales Order")
	_apply_order_payload(doc, customer, items, discount_percent, discount_amount)
	doc.insert()
	return doc.as_dict()


@frappe.whitelist()
def update_sales_order(name: str, customer: str, items, discount_percent: float = 0, discount_amount: float = 0):
	"""Replace the contents of an existing DRAFT Sales Order."""
	_require_van_user()
	_validate_customer_access(customer)

	doc = frappe.get_doc("Sales Order", name)
	if not _is_manager() and doc.owner != frappe.session.user:
		frappe.throw("You can only edit your own sales orders.", frappe.PermissionError)
	if doc.docstatus != 0:
		frappe.throw("Only a draft sales order can be edited.")

	_apply_order_payload(doc, customer, items, discount_percent, discount_amount)
	doc.save()
	return doc.as_dict()


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
	_check_discount_change_allowed(doc)
	_apply_defaults(doc)
	doc.run_method("set_missing_values")
	doc.run_method("calculate_taxes_and_totals")
	_ensure_payment_schedule(doc)
	# Same reasoning as _apply_order_payload(): the driver role holds only read on
	# Sales Order now, so the save/submit pair has to bypass the DocPerm layer. The
	# caller was authorized above by _require_van_user() and the ownership check.
	doc.flags.ignore_permissions = True
	doc.save()
	doc.submit()
	return doc.as_dict()


@frappe.whitelist()
def create_customer(customer_name: str, mobile_no: str = None):
	"""Let a driver quick-add a new customer met in the field.

	Only name and mobile number are collected from the driver — customer_group
	and territory are taken from their own Van Profile (the first of
	allowed_customer_groups, and delivery_route) so the new customer is
	immediately visible to them under _validate_customer_access(), falling
	back to Selling Settings' defaults for a driver with no such restriction
	configured. Customer is a standard ERPNext doctype Van Sales Driver only
	has read access to, so this uses ignore_permissions like the rest of the
	app's driver-facing writes to other ERPNext doctypes — authorization is
	_require_van_user() above.
	"""
	_require_van_user()
	customer_name = (customer_name or "").strip()
	if not customer_name:
		frappe.throw("Customer name is required")

	config = _get_driver_config(required=False) or {}
	selling_settings = frappe.get_single("Selling Settings")
	allowed_groups = config.get("allowed_customer_groups") or []
	customer_group = allowed_groups[0] if allowed_groups else selling_settings.customer_group
	territory = config.get("delivery_route") or selling_settings.territory
	if not customer_group or not territory:
		frappe.throw(
			"No default Customer Group/Territory is configured. Set one on your Van Profile "
			"or ask a manager to set the defaults in Selling Settings."
		)

	doc = frappe.new_doc("Customer")
	doc.customer_name = customer_name
	doc.customer_type = "Individual"
	doc.customer_group = customer_group
	doc.territory = territory
	if mobile_no and mobile_no.strip():
		# Customer.mobile_no is a fetched/read-only field, but setting it here
		# lets ERPNext's own Customer.create_primary_contact() (called from its
		# controller on insert) create the linked Contact automatically.
		doc.mobile_no = mobile_no.strip()
	doc.flags.ignore_permissions = True
	doc.insert()
	return {
		"name": doc.name,
		"customer_name": doc.customer_name,
		"customer_group": doc.customer_group,
		"territory": doc.territory,
	}


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
def get_item_sales_history(item_code: str, customer: str = None, limit: int = 20):
	"""Who this item was sold to and at what rate, most recent first.

	When customer is given (the normal case — the catalog is always entered
	after picking a customer), scoped to that one customer's own past rates for
	this item, since the question at that point is "what did I charge them
	last time", not a general item report.

	Scoped to the current driver's own submitted Sales Orders — matching every
	other reporting endpoint in this app (get_daily_summary, get_sales_orders,
	etc.) — since drivers only have role-level read on Sales Order with no
	row-level restriction, so this app-layer owner filter is what keeps a
	driver from seeing another driver's customers/pricing. Managers see all.
	"""
	_require_van_user()
	if customer:
		_validate_customer_access(customer)
	limit = max(1, min(int(limit or 20), 100))
	params = {"item_code": item_code, "limit": limit}
	owner_condition = ""
	if not _is_manager():
		owner_condition = "and so.owner = %(owner)s"
		params["owner"] = frappe.session.user
	customer_condition = ""
	if customer:
		customer_condition = "and so.customer = %(customer)s"
		params["customer"] = customer

	return frappe.db.sql(
		f"""
		select
			so.name as sales_order,
			so.transaction_date,
			so.customer,
			so.customer_name,
			soi.qty,
			soi.rate,
			soi.amount
		from `tabSales Order Item` soi
		inner join `tabSales Order` so on so.name = soi.parent
		where soi.item_code = %(item_code)s
			and so.docstatus = 1
			{owner_condition}
			{customer_condition}
		order by so.transaction_date desc, so.creation desc
		limit %(limit)s
		""",
		params,
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
		orders = frappe.get_list(
			"Sales Order",
			filters={
				"docstatus": ["!=", 2],
				"transaction_date": today,
				"owner": user,
			},
			# per_billed/advance_paid let the frontend show invoice/payment status
			# alongside the order's own status, since neither is a single field.
			fields=[
				"name", "customer_name", "grand_total", "status", "transaction_date",
				"docstatus", "per_billed", "advance_paid",
			],
			order_by="creation desc"
		)

		if orders:
			# A paid-at-invoicing order (create_sales_invoice's mark_as_paid) is
			# settled on the Sales Invoice, not as a direct advance against the
			# Sales Order — so advance_paid alone reads as "Unpaid" even for a
			# fully paid, fully invoiced order. Pull the linked invoices'
			# outstanding_amount so the frontend can tell the difference.
			# Grouped in Python (not SQL) to dedupe correctly when an order has
			# multiple line items billed onto the same invoice.
			invoice_rows = frappe.get_all(
				"Sales Invoice Item",
				filters={"sales_order": ["in", [o.name for o in orders]], "docstatus": 1},
				fields=["sales_order", "parent as sales_invoice", "amount"],
			)
			invoice_names = {row.sales_invoice for row in invoice_rows if row.sales_invoice}
			invoice_totals = {}
			if invoice_names:
				invoice_totals = {
					inv.name: inv
					for inv in frappe.get_all(
						"Sales Invoice",
						filters={"name": ["in", list(invoice_names)], "docstatus": 1},
						fields=["name", "outstanding_amount", "grand_total", "net_total"],
					)
				}
			# Attribute per (order, invoice) rather than per invoice. One Sales Invoice can
			# bill several of the day's orders, and summing its whole grand_total onto each
			# of them inflated every row and could make a genuinely paid order read as
			# "Unpaid" in DailyLogView's paymentStatus().
			billed: dict[tuple[str, str], float] = {}
			for row in invoice_rows:
				if not row.sales_invoice:
					continue
				key = (row.sales_order, row.sales_invoice)
				billed[key] = billed.get(key, 0) + flt(row.amount)

			for order in orders:
				invoiced_total = 0.0
				invoiced_outstanding = 0.0
				for (order_name, invoice_name), amount in billed.items():
					if order_name != order.name:
						continue
					invoice = invoice_totals.get(invoice_name)
					if not invoice:
						continue
					invoiced_total += amount
					# Outstanding is invoice-level, so pro-rate it by this order's share of
					# the invoice's net total (not of the lines linked to orders in this
					# batch — the invoice may carry lines belonging to no sales order).
					net_total = flt(invoice.net_total)
					share = (amount / net_total) if net_total else 0
					invoiced_outstanding += flt(invoice.outstanding_amount) * share
				order["invoiced_total"] = invoiced_total
				order["invoiced_outstanding"] = invoiced_outstanding

		return orders
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
def create_sales_invoice(sales_order: str, mark_as_paid: int = 0, mode_of_payment: str = None):
	"""Create (and submit) a Sales Invoice from a submitted Sales Order.

	By default the invoice is left outstanding (a credit sale, collected later
	via create_payment_entry()). Pass mark_as_paid=1 with a mode_of_payment to
	collect payment immediately — this raises a Payment Entry fully allocated
	against the new invoice in the same request, so the invoice shows Paid
	right away and the collection is correctly picked up by shift reconciliation
	(which sums Payment Entry, not any invoice-level payment fields).
	"""
	_require_van_user()
	mark_as_paid = _coerce_check(mark_as_paid)
	if mark_as_paid:
		if not mode_of_payment:
			frappe.throw("Select a mode of payment to mark this invoice as paid.")
		_ensure_driver_mode_allowed(mode_of_payment)

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

	# Carry the order-level discount across. Without this the invoice is raised at the
	# UNDISCOUNTED total — a 100.00 order with 10% off bills 100.00, and with mark_as_paid
	# the customer is charged the full amount while the order and invoice totals diverge
	# permanently. Copied verbatim, which is exact for the normal path (creation is
	# refused once per_billed reaches 100, so the invoice bills the whole order); if
	# returns have reduced what is being billed, a flat discount_amount is proportionally
	# generous, though ERPNext still caps it at the invoice total.
	sinv.apply_discount_on = so.apply_discount_on or "Grand Total"
	sinv.additional_discount_percentage = flt(so.additional_discount_percentage)
	sinv.discount_amount = flt(so.discount_amount)

	sinv.run_method("set_missing_values")
	sinv.run_method("calculate_taxes_and_totals")

	# Sales Invoice is a standard ERPNext financial doctype. Van Sales Driver does not hold
	# broad ERPNext accounting permissions, so we use flags.ignore_permissions after
	# explicitly authorizing the user above via _require_van_user().
	sinv.flags.ignore_permissions = True
	sinv.insert()
	sinv.submit()

	# `> 0` guard: Payment Entry's paid_amount is reqd, so allocating 0 raises
	# "Paid Amount is mandatory" AFTER sinv.submit() has run — rolling back the whole
	# request, so the driver loses the invoice as well to an error that explains
	# nothing. A zero-outstanding invoice (a fully discounted order, or one whose
	# advances were auto-allocated) is already settled, so there is nothing to collect.
	if mark_as_paid and flt(sinv.outstanding_amount) > 0:
		# Use sinv.outstanding_amount (the real, post-submit figure ERPNext itself
		# computed — rounded_total minus anything already paid), not grand_total.
		# When a rounding adjustment applies (e.g. grand_total 12.5, rounded_total
		# 12.0), grand_total is the pre-rounding figure and does NOT equal what the
		# invoice's own outstanding_amount field holds. Payment Entry re-validates
		# allocated_amount against the reference doc's live outstanding_amount at
		# submit time (validate_allocated_amount_with_latest_data()), so allocating
		# grand_total here fails with "Allocated Amount cannot be greater than
		# outstanding amount" even though this invoice was created microseconds ago.
		from van_sale.van_sale.finance import make_receive_payment_entry
		make_receive_payment_entry(
			customer=sinv.customer,
			mode_of_payment=mode_of_payment,
			paid_amount=sinv.outstanding_amount,
			reference_rows=[{
				"reference_doctype": "Sales Invoice",
				"reference_name": sinv.name,
				"total_amount": sinv.grand_total,
				"outstanding_amount": sinv.outstanding_amount,
				"allocated_amount": sinv.outstanding_amount,
			}],
			company=sinv.company,
		)

	return sinv.name


@frappe.whitelist()
def create_sales_return(customer: str, items):
	_require_van_user()
	_validate_customer_access(customer)

	from van_sale.van_sale.inventory import _parse_stock_transfer_lines

	# Managers pass _require_van_user() without being assigned to a Van Profile, so the
	# van warehouse is optional here — same fallback as create_sales_invoice_from_order().
	# Without it ERPNext resolves the item/company default warehouse.
	config = _get_driver_config(required=False)
	van_warehouse = config.get("van_warehouse") if config else None
	lines = items if isinstance(items, list) else _parse_stock_transfer_lines(items)

	doc = frappe.new_doc("Sales Invoice")
	doc.customer = customer
	doc.is_return = 1
	doc.update_stock = 1
	if van_warehouse:
		doc.set_warehouse = van_warehouse
	# _apply_defaults() is Sales Order shaped (order_type / transaction_date / delivery_date)
	# and raises AttributeError on a Sales Invoice, so set the invoice defaults directly.
	doc.company = config.get("company") if config else None
	if not doc.company:
		doc.company = _default_company()
	doc.posting_date = nowdate()
	if config:
		if config.get("selling_price_list"):
			doc.selling_price_list = config["selling_price_list"]
		if config.get("currency"):
			doc.currency = config["currency"]

	for idx, row in enumerate(lines, start=1):
		item_code = row.get("item_code")
		qty = abs(float(row.get("qty", 0)))
		if not item_code or qty <= 0:
			continue
		line = {"item_code": item_code, "qty": -qty}
		rate = flt(row.get("rate"))
		if rate > 0:
			line["rate"] = rate
		doc.append("items", line)

	doc.run_method("set_missing_values")
	# The catalog prices items from Item.standard_rate when no Item Price row exists, but
	# set_missing_values() only consults the price list — so a return of an unpriced item
	# lands on rate 0 and issues a zero-value credit note. Apply the same fallback here so
	# the credit matches the amount the app showed.
	for line in doc.items:
		if not flt(line.rate):
			line.rate = flt(frappe.db.get_value("Item", line.item_code, "standard_rate"))
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
