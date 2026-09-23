import json
import frappe
from frappe.utils import flt, now_datetime, nowdate, nowtime
from erpnext.stock.doctype.batch.batch import get_batch_qty as get_batch_qty_for_warehouse
from van_sale.van_sale.utils import (
	_get_driver_config, _coerce_check, _to_float, _default_company,
	_coerce_list, _driver_stock_cache_key, DRIVER_CACHE_TTL, _require_van_user
)

def _set_driver_stock_cache(user: str, payload: dict):
	frappe.cache.set_value(_driver_stock_cache_key(user), payload, expires_in_sec=DRIVER_CACHE_TTL)

def _get_item_warehouse_qty(item_code: str, warehouse: str) -> float:
	qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
	return _to_float(qty)

def _get_serial_numbers(item_code: str, warehouse: str, limit: int = 100):
	serial_rows = frappe.get_all(
		"Serial No",
		filters={"item_code": item_code, "warehouse": warehouse, "status": "Active"},
		fields=["name"],
		limit_page_length=limit,
		order_by="creation asc",
	)
	return [row.name for row in serial_rows]

def _get_batch_options(item_code: str, warehouse: str):
	batches = []
	for row in frappe.get_all("Batch", filters={"item": item_code}, fields=["name"], order_by="expiry_date asc, creation asc"):
		qty = _to_float(get_batch_qty_for_warehouse(row.name, warehouse, item_code), 4)
		if qty > 0:
			batches.append({"batch_no": row.name, "available_qty": qty})
	return batches

def _parse_stock_transfer_lines(items):
	parsed_items = items
	if isinstance(items, str):
		parsed_items = json.loads(items)
	if not isinstance(parsed_items, list) or not parsed_items:
		frappe.throw("At least one transfer line is required")
	return parsed_items

def _get_stock_snapshot(config: dict):
	rows = frappe.db.sql(
		"""
		select
			bin.item_code,
			item.item_name,
			item.stock_uom,
			item.has_batch_no,
			item.has_serial_no,
			item.image,
			bin.actual_qty,
			bin.reserved_qty,
			bin.projected_qty
		from `tabBin` bin
		inner join `tabItem` item on item.name = bin.item_code
		where bin.warehouse = %(warehouse)s
			and item.disabled = 0
			and item.is_stock_item = 1
			and (bin.actual_qty != 0 or bin.reserved_qty != 0 or bin.projected_qty != 0)
		order by item.item_name asc
		""",
		{"warehouse": config["van_warehouse"]},
		as_dict=1,
	)

	threshold = flt(config.get("low_stock_threshold") or 0)
	items = []
	for row in rows:
		actual_qty = _to_float(row.actual_qty)
		reserved_qty = _to_float(row.reserved_qty)
		projected_qty = _to_float(row.projected_qty)
		items.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"stock_uom": row.stock_uom,
				"image": row.image,
				"actual_qty": actual_qty,
				"reserved_qty": reserved_qty,
				"projected_qty": projected_qty,
				"has_batch_no": _coerce_check(row.has_batch_no),
				"has_serial_no": _coerce_check(row.has_serial_no),
				"is_low_stock": actual_qty <= threshold,
			}
		)

	return {
		"warehouse": config["van_warehouse"],
		"source_warehouse": config["source_warehouse"],
		"company": config["company"],
		"low_stock_threshold": threshold,
		"generated_at": now_datetime().isoformat(),
		"summary": {
			"item_count": len(items),
			"low_stock_count": len([row for row in items if row["is_low_stock"]]),
			"total_available_qty": _to_float(sum(row["actual_qty"] for row in items), 2),
			"total_reserved_qty": _to_float(sum(row["reserved_qty"] for row in items), 2),
		},
		"items": items,
	}

@frappe.whitelist()
def get_driver_stock_dashboard(force_refresh: int = 0):
	# Gate first, before the cache read: this was the only whitelisted endpoint in the
	# app without it, relying on _get_driver_config() throwing instead. utils.py states
	# the convention — call _require_van_user() at the very top of every one.
	_require_van_user()
	user = frappe.session.user
	use_cache = not _coerce_check(force_refresh)
	if use_cache:
		# expires=True — this key carries an expiry, see the note in _get_driver_config().
		cached = frappe.cache.get_value(_driver_stock_cache_key(user), expires=True)
		if cached:
			return cached

	# Unlike create_sales_return(), there is no sensible fallback here — a van stock
	# snapshot is meaningless without a van warehouse — so this still requires a
	# profile. It just says so in terms the caller can act on, rather than surfacing
	# the bare "No active driver configuration found".
	config = _get_driver_config(user=user, required=False)
	if not config:
		frappe.throw(
			"Van stock is only available to a driver assigned to an active Van Profile. "
			"Ask a manager to assign you to one."
		)
	payload = _get_stock_snapshot(config)
	_set_driver_stock_cache(user, payload)
	return payload

@frappe.whitelist()
def search_transfer_items(search: str | None = None, page_length: int = 20):
	_require_van_user()
	config = _get_driver_config()
	limit = max(1, min(int(page_length or 20), 50))
	text = (search or "").strip()
	params = {"warehouse": config["source_warehouse"], "limit": limit}
	conditions = []
	if text:
		params["search"] = f"%{text}%"
		conditions.append("(item.name like %(search)s or item.item_name like %(search)s or item.description like %(search)s)")

	where_clause = " and " + " and ".join(conditions) if conditions else ""
	rows = frappe.db.sql(
		f"""
		select
			item.name as item_code,
			item.item_name,
			item.description,
			item.stock_uom,
			item.has_batch_no,
			item.has_serial_no,
			bin.actual_qty,
			item.image
		from `tabBin` bin
		inner join `tabItem` item on item.name = bin.item_code
		where bin.warehouse = %(warehouse)s
			and item.disabled = 0
			and item.is_stock_item = 1
			and bin.actual_qty > 0
			{where_clause}
		order by item.item_name asc
		limit %(limit)s
		""",
		params,
		as_dict=1,
	)
	return [
		{
			"item_code": row.item_code,
			"item_name": row.item_name,
			"description": row.description,
			"stock_uom": row.stock_uom,
			"actual_qty": _to_float(row.actual_qty),
			"has_batch_no": _coerce_check(row.has_batch_no),
			"has_serial_no": _coerce_check(row.has_serial_no),
			"image": row.image,
		}
		for row in rows
	]

@frappe.whitelist()
def get_transfer_item_detail(item_code: str):
	_require_van_user()
	config = _get_driver_config()
	if not frappe.db.exists("Item", item_code):
		frappe.throw(f"Item {item_code} was not found")

	item = frappe.db.get_value(
		"Item",
		item_code,
		["name", "item_name", "description", "stock_uom", "has_batch_no", "has_serial_no", "image"],
		as_dict=True,
	)
	return {
		"item_code": item.name,
		"item_name": item.item_name,
		"description": item.description,
		"stock_uom": item.stock_uom,
		"image": item.image,
		"has_batch_no": _coerce_check(item.has_batch_no),
		"has_serial_no": _coerce_check(item.has_serial_no),
		"source_warehouse": config["source_warehouse"],
		"van_warehouse": config["van_warehouse"],
		"source_qty": _get_item_warehouse_qty(item_code, config["source_warehouse"]),
		"van_qty": _get_item_warehouse_qty(item_code, config["van_warehouse"]),
		"batches": _get_batch_options(item_code, config["source_warehouse"]),
		"serial_nos": _get_serial_numbers(item_code, config["source_warehouse"]),
	}

@frappe.whitelist()
def create_stock_transfer(items, remarks: str | None = None, submit: int = 1, posting_date: str | None = None):
	_require_van_user()
	config = _get_driver_config()
	lines = _parse_stock_transfer_lines(items)
	entry = frappe.new_doc("Stock Entry")
	entry.stock_entry_type = "Material Transfer"
	entry.purpose = "Material Transfer"
	entry.company = config["company"] or _default_company()
	entry.from_warehouse = config["source_warehouse"]
	entry.to_warehouse = config["van_warehouse"]
	entry.posting_date = posting_date or nowdate()
	entry.posting_time = nowtime()
	entry.user_remark = remarks or f"Van stock transfer for {frappe.session.user}"

	for idx, row in enumerate(lines, start=1):
		item_code = row.get("item_code")
		qty = _to_float(row.get("qty"), 4)
		if not item_code or qty <= 0:
			frappe.throw(f"Transfer line {idx} is invalid")

		item = frappe.db.get_value(
			"Item",
			item_code,
			["item_name", "stock_uom", "has_batch_no", "has_serial_no"],
			as_dict=True,
		)
		if not item:
			frappe.throw(f"Item {item_code} was not found")

		available_qty = _get_item_warehouse_qty(item_code, config["source_warehouse"])
		if qty > available_qty:
			frappe.throw(
				f"Requested quantity for {item_code} exceeds available stock in {config['source_warehouse']}"
			)

		batch_no = row.get("batch_no") or None
		serial_list = _coerce_list(row.get("serial_nos") or row.get("serial_no"))
		serial_text = "\n".join(serial_list) if serial_list else None

		if _coerce_check(item.has_batch_no) and not batch_no:
			frappe.throw(f"Batch number is required for {item_code}")
		if batch_no:
			batch_qty = _to_float(get_batch_qty_for_warehouse(batch_no, config["source_warehouse"], item_code), 4)
			if qty > batch_qty:
				frappe.throw(f"Batch {batch_no} does not have enough quantity for {item_code}")

		if _coerce_check(item.has_serial_no):
			if not serial_list:
				frappe.throw(f"Serial numbers are required for {item_code}")
			if len(serial_list) != int(qty):
				frappe.throw(f"Serial number count must match quantity for {item_code}")

		entry.append(
			"items",
			{
				"idx": idx,
				"item_code": item_code,
				"item_name": item.item_name,
				"s_warehouse": config["source_warehouse"],
				"t_warehouse": config["van_warehouse"],
				"qty": qty,
				"transfer_qty": qty,
				"uom": item.stock_uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": 1,
				"batch_no": batch_no,
				"serial_no": serial_text,
			},
		)

	# Stock Entry is a standard ERPNext inventory doctype. Van Sales Driver does not hold
	# broad ERPNext stock permissions. Authorization is enforced above via _get_driver_config()
	# (which requires an active driver profile) and quantity/warehouse validation.
	# flags.ignore_permissions lets us insert/submit without requiring the Stock User role.
	entry.flags.ignore_permissions = True
	entry.insert()
	if _coerce_check(submit):
		entry.submit()

	frappe.cache.delete_value(_driver_stock_cache_key(frappe.session.user))
	return {
		"name": entry.name,
		"docstatus": entry.docstatus,
		"posting_date": entry.posting_date,
		"from_warehouse": config["source_warehouse"],
		"to_warehouse": config["van_warehouse"],
	}
