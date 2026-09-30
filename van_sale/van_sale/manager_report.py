"""
Manager views across the whole van fleet.

- get_manager_dashboard(): today, per van — shift status, sales, collections,
  expenses, expected cash on open shifts — plus alerts that need a manager's eye.
- get_period_report(): any date range, optionally narrowed to one driver or van,
  compared with the period of the same length just before it (the watch_doctor
  monthly-report pattern).

Van documents carry no van/shift stamp, so activity is attributed the same way the
shift closing does it: by the driver who created the record. "The fleet" is every
user assigned as a driver on a Van Profile. Sales are submitted Sales Orders, as on
the shift closing; returns are submitted credit notes (return Sales Invoices).
"""

from collections import defaultdict

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, nowdate

from van_sale.van_sale.shift import _compute_closing, _serialize_opening
from van_sale.van_sale.utils import _manager_only

MAX_PERIOD_DAYS = 366


# ─── Scope ────────────────────────────────────────────────────────────────────

def _fleet(driver: str | None = None, van_profile: str | None = None) -> dict[str, dict]:
	"""Drivers on Van Profiles, keyed by user. A driver on several profiles keeps the
	first active one, so each driver's activity is counted once."""
	filters = {}
	if van_profile:
		filters["name"] = van_profile
	profiles = frappe.get_all(
		"Van Profile",
		filters=filters,
		fields=["name", "profile_name", "delivery_route", "is_active"],
		order_by="is_active desc, profile_name asc",
	)
	fleet: dict[str, dict] = {}
	for profile in profiles:
		for row in frappe.get_all(
			"Van Profile Driver",
			filters={"parent": profile.name, "parenttype": "Van Profile"},
			fields=["driver_user"],
			order_by="idx asc",
		):
			user = row.driver_user
			if not user or user in fleet or (driver and user != driver):
				continue
			fleet[user] = {
				"driver": user,
				"driver_name": frappe.utils.get_fullname(user),
				"van_profile": profile.name,
				"van_name": profile.profile_name or profile.name,
				"delivery_route": profile.delivery_route,
			}
	return fleet


def _plural(count: int, noun: str) -> str:
	return f"{count} {noun}{'' if count == 1 else 's'}"


def _sum_by_owner(sql: str, params: dict) -> dict[str, dict]:
	return {row.owner: row for row in frappe.db.sql(sql, params, as_dict=True)}


# ─── Period aggregation ───────────────────────────────────────────────────────

def _period_totals(owners: tuple, from_date, to_date) -> dict:
	"""Headline figures for one period, plus the per-driver split they add up from."""
	params = {"owners": owners, "from": from_date, "to": to_date}
	sales = _sum_by_owner(
		"""select owner, count(*) as count, sum(base_grand_total) as amount
		from `tabSales Order`
		where docstatus = 1 and transaction_date between %(from)s and %(to)s and owner in %(owners)s
		group by owner""",
		params,
	)
	invoices = _sum_by_owner(
		"""select owner,
			sum(case when is_return = 0 then 1 else 0 end) as count,
			sum(case when is_return = 0 then base_grand_total else 0 end) as amount,
			sum(case when is_return = 1 then 1 else 0 end) as return_count,
			-sum(case when is_return = 1 then base_grand_total else 0 end) as return_amount
		from `tabSales Invoice`
		where docstatus = 1 and posting_date between %(from)s and %(to)s and owner in %(owners)s
		group by owner""",
		params,
	)
	collections = _sum_by_owner(
		"""select owner, count(*) as count, sum(base_paid_amount) as amount
		from `tabPayment Entry`
		where docstatus = 1 and payment_type = 'Receive'
			and posting_date between %(from)s and %(to)s and owner in %(owners)s
		group by owner""",
		params,
	)
	expenses = _sum_by_owner(
		"""select driver as owner, count(*) as count, sum(amount) as amount
		from `tabVan Expense Log`
		where docstatus < 2 and expense_date between %(from)s and %(to)s and driver in %(owners)s
		group by driver""",
		params,
	)
	shifts = _sum_by_owner(
		"""select driver as owner, count(*) as count, sum(net_difference) as variance,
			sum(case when abs(net_difference) >= 0.005 then 1 else 0 end) as variance_count
		from `tabVan Shift Closing`
		where docstatus = 1 and shift_date between %(from)s and %(to)s and driver in %(owners)s
		group by driver""",
		params,
	)

	def pick(source, owner, key="amount"):
		row = source.get(owner)
		return flt(row.get(key)) if row else 0.0

	by_driver = {}
	for owner in owners:
		by_driver[owner] = {
			"orders_count": int(pick(sales, owner, "count")),
			"sales": pick(sales, owner),
			"invoices_count": int(pick(invoices, owner, "count")),
			"invoiced": pick(invoices, owner),
			"returns_count": int(pick(invoices, owner, "return_count")),
			"returns": pick(invoices, owner, "return_amount"),
			"payments_count": int(pick(collections, owner, "count")),
			"collections": pick(collections, owner),
			"expenses_count": int(pick(expenses, owner, "count")),
			"expenses": pick(expenses, owner),
			"shifts_count": int(pick(shifts, owner, "count")),
			"variance": pick(shifts, owner, "variance"),
			"variance_shifts": int(pick(shifts, owner, "variance_count")),
		}

	totals: dict = {}
	for row in by_driver.values():
		for key, value in row.items():
			totals[key] = totals.get(key, 0) + value
	totals = _with_derived(totals)
	return {"totals": totals, "by_driver": by_driver}


def _with_derived(row: dict) -> dict:
	for key in (
		"orders_count", "sales", "invoices_count", "invoiced", "returns_count", "returns",
		"payments_count", "collections", "expenses_count", "expenses", "shifts_count",
		"variance", "variance_shifts",
	):
		row.setdefault(key, 0)
	row["net_sales"] = flt(row["sales"]) - flt(row["returns"])
	row["net_cash"] = flt(row["collections"]) - flt(row["expenses"])
	row["avg_order"] = flt(row["sales"]) / row["orders_count"] if row["orders_count"] else 0.0
	row["return_rate"] = flt(row["returns"]) / flt(row["sales"]) * 100 if flt(row["sales"]) else 0.0
	return row


def _daily(owners: tuple, from_date, to_date) -> list[dict]:
	params = {"owners": owners, "from": from_date, "to": to_date}
	series = {
		"sales": """select transaction_date as d, sum(base_grand_total) as v from `tabSales Order`
			where docstatus = 1 and transaction_date between %(from)s and %(to)s and owner in %(owners)s
			group by transaction_date""",
		"collections": """select posting_date as d, sum(base_paid_amount) as v from `tabPayment Entry`
			where docstatus = 1 and payment_type = 'Receive' and posting_date between %(from)s and %(to)s
				and owner in %(owners)s
			group by posting_date""",
		"expenses": """select expense_date as d, sum(amount) as v from `tabVan Expense Log`
			where docstatus < 2 and expense_date between %(from)s and %(to)s and driver in %(owners)s
			group by expense_date""",
		"returns": """select posting_date as d, -sum(base_grand_total) as v from `tabSales Invoice`
			where docstatus = 1 and is_return = 1 and posting_date between %(from)s and %(to)s
				and owner in %(owners)s
			group by posting_date""",
	}
	values = {key: {str(r.d): flt(r.v) for r in frappe.db.sql(sql, params, as_dict=True)} for key, sql in series.items()}
	days = []
	for offset in range(date_diff(to_date, from_date) + 1):
		day = str(add_days(from_date, offset))
		days.append({"date": day, **{key: values[key].get(day, 0.0) for key in series}})
	return days


def _items(owners: tuple, from_date, to_date) -> list[dict]:
	"""Items sold (Sales Orders) and returned (credit notes), in stock UOM, net of order
	discounts and before tax — the same basis as the shift report."""
	params = {"owners": owners, "from": from_date, "to": to_date}
	items: dict[str, dict] = {}
	for row in frappe.db.sql(
		"""select i.item_code, max(i.item_name) as item_name, max(i.item_group) as item_group,
			max(i.stock_uom) as uom, sum(i.stock_qty) as qty, sum(i.base_net_amount) as amount
		from `tabSales Order Item` i join `tabSales Order` p on p.name = i.parent
		where p.docstatus = 1 and p.transaction_date between %(from)s and %(to)s and p.owner in %(owners)s
		group by i.item_code""",
		params,
		as_dict=True,
	):
		items[row.item_code] = {
			"item_code": row.item_code, "item_name": row.item_name, "item_group": row.item_group,
			"uom": row.uom, "sold_qty": flt(row.qty), "sold_amount": flt(row.amount),
			"returned_qty": 0.0, "returned_amount": 0.0,
		}
	for row in frappe.db.sql(
		"""select i.item_code, max(i.item_name) as item_name, max(i.item_group) as item_group,
			max(i.stock_uom) as uom, -sum(i.stock_qty) as qty, -sum(i.base_net_amount) as amount
		from `tabSales Invoice Item` i join `tabSales Invoice` p on p.name = i.parent
		where p.docstatus = 1 and p.is_return = 1 and p.posting_date between %(from)s and %(to)s
			and p.owner in %(owners)s
		group by i.item_code""",
		params,
		as_dict=True,
	):
		entry = items.setdefault(row.item_code, {
			"item_code": row.item_code, "item_name": row.item_name, "item_group": row.item_group,
			"uom": row.uom, "sold_qty": 0.0, "sold_amount": 0.0,
		})
		entry["returned_qty"] = flt(row.qty)
		entry["returned_amount"] = flt(row.amount)
	for entry in items.values():
		entry["net_qty"] = entry["sold_qty"] - entry["returned_qty"]
		entry["net_amount"] = entry["sold_amount"] - entry["returned_amount"]
	return sorted(items.values(), key=lambda r: -r["net_amount"])


def _item_groups(items: list[dict]) -> list[dict]:
	groups: dict[str, dict] = defaultdict(lambda: {"sold_amount": 0.0, "returned_amount": 0.0, "net_amount": 0.0, "items": 0})
	for item in items:
		group = groups[item["item_group"] or "Uncategorised"]
		group["sold_amount"] += item["sold_amount"]
		group["returned_amount"] += item["returned_amount"]
		group["net_amount"] += item["net_amount"]
		group["items"] += 1
	return sorted(({"item_group": k, **v} for k, v in groups.items()), key=lambda r: -r["net_amount"])


def _customers(owners: tuple, from_date, to_date, limit: int = 15) -> list[dict]:
	return frappe.db.sql(
		"""select customer, max(customer_name) as customer_name, count(*) as orders_count,
			sum(base_grand_total) as sales
		from `tabSales Order`
		where docstatus = 1 and transaction_date between %(from)s and %(to)s and owner in %(owners)s
		group by customer
		order by sales desc
		limit %(limit)s""",
		{"owners": owners, "from": from_date, "to": to_date, "limit": limit},
		as_dict=True,
	)


def _collections_by_mode(owners: tuple, from_date, to_date) -> list[dict]:
	return frappe.db.sql(
		"""select coalesce(mode_of_payment, 'Unspecified') as mode_of_payment, count(*) as count,
			sum(base_paid_amount) as amount
		from `tabPayment Entry`
		where docstatus = 1 and payment_type = 'Receive' and posting_date between %(from)s and %(to)s
			and owner in %(owners)s
		group by mode_of_payment
		order by amount desc""",
		{"owners": owners, "from": from_date, "to": to_date},
		as_dict=True,
	)


def _expenses_by_type(owners: tuple, from_date, to_date) -> list[dict]:
	return frappe.db.sql(
		"""select coalesce(expense_type, 'Other') as expense_type, count(*) as count, sum(amount) as amount
		from `tabVan Expense Log`
		where docstatus < 2 and expense_date between %(from)s and %(to)s and driver in %(owners)s
		group by expense_type
		order by amount desc""",
		{"owners": owners, "from": from_date, "to": to_date},
		as_dict=True,
	)


def _shift_closings(owners: tuple, from_date, to_date) -> list[dict]:
	return frappe.db.sql(
		"""select name, opening_shift, driver, shift_date, period_start, period_end, total_sales,
			total_collections, total_expenses, expected_cash, net_difference
		from `tabVan Shift Closing`
		where docstatus = 1 and shift_date between %(from)s and %(to)s and driver in %(owners)s
		order by period_end desc""",
		{"owners": owners, "from": from_date, "to": to_date},
		as_dict=True,
	)


def _comparison(current: dict, previous: dict) -> list[dict]:
	rows = []
	for metric, label in (
		("sales", "Sales"),
		("orders_count", "Orders"),
		("avg_order", "Average order"),
		("returns", "Returns"),
		("net_sales", "Net sales"),
		("collections", "Collections"),
		("expenses", "Expenses"),
		("net_cash", "Net cash (collections − expenses)"),
		("variance", "Cash variance"),
	):
		cur, prev = flt(current.get(metric)), flt(previous.get(metric))
		rows.append({
			"metric": metric,
			"label": label,
			"current": cur,
			"previous": prev,
			"delta": cur - prev,
			"delta_pct": ((cur - prev) / abs(prev) * 100) if prev else None,
		})
	return rows


# ─── Endpoints ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_fleet():
	"""Drivers and vans, for the report filters."""
	_manager_only()
	fleet = _fleet()
	vans = {}
	for row in fleet.values():
		vans.setdefault(row["van_profile"], {"van_profile": row["van_profile"], "van_name": row["van_name"]})
	return {"drivers": list(fleet.values()), "vans": list(vans.values())}


@frappe.whitelist()
def get_period_report(from_date: str, to_date: str, driver: str | None = None, van_profile: str | None = None):
	_manager_only()
	from_date, to_date = getdate(from_date), getdate(to_date)
	if from_date > to_date:
		frappe.throw("The start date must be on or before the end date.")
	days = date_diff(to_date, from_date) + 1
	if days > MAX_PERIOD_DAYS:
		frappe.throw(f"Pick a period of at most {MAX_PERIOD_DAYS} days.")

	prev_to = add_days(from_date, -1)
	prev_from = add_days(prev_to, -(days - 1))
	fleet = _fleet(driver or None, van_profile or None)
	period = {
		"from_date": str(from_date), "to_date": str(to_date), "days": days,
		"previous_from": str(prev_from), "previous_to": str(prev_to),
	}
	if not fleet:
		empty = _with_derived({})
		return {
			"period": period, "totals": empty, "previous": empty, "comparison": _comparison(empty, empty),
			"daily": [], "by_driver": [], "collections_by_mode": [], "expenses_by_type": [],
			"items": [], "item_groups": [], "customers": [], "shifts": [],
		}

	owners = tuple(fleet)
	current = _period_totals(owners, from_date, to_date)
	previous = _period_totals(owners, prev_from, prev_to)

	by_driver = [
		_with_derived({**fleet[owner], **row})
		for owner, row in current["by_driver"].items()
	]
	by_driver.sort(key=lambda r: (-r["sales"], -r["collections"], r["driver_name"]))

	items = _items(owners, from_date, to_date)
	shifts = _shift_closings(owners, from_date, to_date)
	for shift in shifts:
		shift["driver_name"] = fleet.get(shift.driver, {}).get("driver_name") or shift.driver
		shift["van_name"] = fleet.get(shift.driver, {}).get("van_name")

	return {
		"period": period,
		"totals": current["totals"],
		"previous": previous["totals"],
		"comparison": _comparison(current["totals"], previous["totals"]),
		"daily": _daily(owners, from_date, to_date),
		"by_driver": by_driver,
		"collections_by_mode": _collections_by_mode(owners, from_date, to_date),
		"expenses_by_type": _expenses_by_type(owners, from_date, to_date),
		"items": items,
		"item_groups": _item_groups(items),
		"customers": _customers(owners, from_date, to_date),
		"shifts": shifts,
	}


@frappe.whitelist()
def get_manager_dashboard():
	"""Today across the fleet: one row per van plus what needs attention."""
	_manager_only()
	today = getdate(nowdate())
	fleet = _fleet()
	if not fleet:
		return {"date": str(today), "totals": _with_derived({}), "vans": [], "alerts": []}

	owners = tuple(fleet)
	current = _period_totals(owners, today, today)

	open_today: dict[str, dict] = {}
	stale: dict[str, list] = defaultdict(list)
	for row in frappe.get_all(
		"Van Shift Opening",
		filters={"docstatus": 1, "status": "Open", "driver": ["in", owners]},
		fields=["name", "driver", "shift_date", "period_start"],
		order_by="shift_date asc",
	):
		if getdate(row.shift_date) == today:
			open_today[row.driver] = row
		else:
			stale[row.driver].append(row)
	closed_today = {
		row.driver: row
		for row in frappe.get_all(
			"Van Shift Closing",
			filters={"docstatus": 1, "shift_date": today, "driver": ["in", owners]},
			fields=["name", "driver", "period_end", "net_difference"],
			order_by="period_end asc",
		)
	}

	vans = []
	alerts = []
	for owner, info in fleet.items():
		row = _with_derived({**info, **current["by_driver"][owner]})
		opening = open_today.get(owner)
		closing = closed_today.get(owner)
		row.update({"shift_status": "none", "opening_shift": None, "closing_shift": None,
			"shift_since": None, "expected_cash": None, "net_difference": None})
		if opening:
			row.update({
				"shift_status": "open",
				"opening_shift": opening.name,
				"shift_since": str(opening.period_start) if opening.period_start else None,
				"expected_cash": _compute_closing(
					_serialize_opening(frappe.get_doc("Van Shift Opening", opening.name))
				)["expected_cash"],
			})
		elif closing:
			row.update({
				"shift_status": "closed",
				"closing_shift": closing.name,
				"shift_since": str(closing.period_end) if closing.period_end else None,
				"net_difference": flt(closing.net_difference),
			})
		old = stale.get(owner)
		if old:
			if row["shift_status"] == "none":
				row["shift_status"] = "stale"
				row["opening_shift"] = old[-1].name
			since = frappe.utils.formatdate(old[0].shift_date)
			alerts.append({
				"level": "warning",
				"kind": "stale_shift",
				"driver": owner,
				"reference": old[0].name,
				"title": (
					f"{info['driver_name']} has a shift still open from {since}" if len(old) == 1
					else f"{info['driver_name']} has {len(old)} shifts still open, the oldest from {since}"
				),
				"body": "The app can only close today's shift, so these have to be closed from the desk: "
				+ ", ".join(o.name for o in old) + ".",
			})
		if closing and abs(flt(closing.net_difference)) >= 0.005:
			alerts.append({
				"level": "danger" if flt(closing.net_difference) < 0 else "info",
				"kind": "variance",
				"driver": owner,
				"reference": closing.name,
				"title": f"{info['driver_name']} closed with a cash variance",
				"body": f"{'Short' if flt(closing.net_difference) < 0 else 'Over'} by {frappe.format_value(abs(flt(closing.net_difference)), {'fieldtype': 'Currency'})}.",
				"amount": flt(closing.net_difference),
			})
		if row["shift_status"] in ("none", "stale") and (row["orders_count"] or row["payments_count"]):
			alerts.append({
				"level": "warning",
				"kind": "no_shift",
				"driver": owner,
				"reference": None,
				"title": f"{info['driver_name']} is trading without an open shift",
				"body": f"{_plural(row['orders_count'], 'order')} and {_plural(row['payments_count'], 'payment')} today with no shift opened.",
			})
		vans.append(row)

	status_order = {"open": 0, "stale": 1, "closed": 2, "none": 3}
	vans.sort(key=lambda r: (status_order[r["shift_status"]], -r["sales"], r["driver_name"]))
	totals = current["totals"]
	totals["open_shifts"] = sum(1 for v in vans if v["shift_status"] == "open")
	totals["closed_shifts"] = sum(1 for v in vans if v["shift_status"] == "closed")
	totals["expected_cash_open"] = sum(flt(v["expected_cash"]) for v in vans if v["shift_status"] == "open")
	return {"date": str(today), "totals": totals, "vans": vans, "alerts": alerts}
