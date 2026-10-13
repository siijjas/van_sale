"""
Scheduled jobs (see hooks.py scheduler_events).

notify_stale_shifts: once a day, tell managers which shifts are still open from an
earlier day. A forgotten shift means that day's cash was never reconciled and the
driver can't open a new one, so it needs a manager either way (close it from the
manager dashboard, or chase the driver). The alert is a Notification Log per
manager: it shows in the desk bell, and Frappe emails it according to each user's
Notification Settings.
"""

import frappe
from frappe.utils import formatdate, getdate, nowdate

from van_sale.van_sale.utils import MANAGER_ROLES


def _manager_users() -> list[str]:
	"""Enabled, non-system users holding a manager role (what _is_manager() checks)."""
	rows = frappe.db.sql(
		"""select distinct u.name from `tabUser` u
		join `tabHas Role` r on r.parent = u.name and r.parenttype = 'User'
		where u.enabled = 1 and u.user_type = 'System User'
			and u.name not in ('Administrator', 'Guest') and r.role in %(roles)s
		order by u.name""",
		{"roles": tuple(MANAGER_ROLES)},
		as_dict=True,
	)
	return [row.name for row in rows]


def stale_shifts() -> list[dict]:
	"""Open shifts whose date is before today, oldest first."""
	rows = frappe.get_all(
		"Van Shift Opening",
		filters={"docstatus": 1, "status": "Open", "shift_date": ["<", nowdate()]},
		fields=["name", "driver", "shift_date", "van_profile", "period_start"],
		order_by="shift_date asc, creation asc",
	)
	for row in rows:
		row["driver_name"] = frappe.utils.get_fullname(row.driver)
		row["days_open"] = (getdate(nowdate()) - getdate(row.shift_date)).days
	return rows


def notify_stale_shifts() -> dict:
	"""Daily: one notification per manager listing every shift left open from an
	earlier day. Returns what it did so the test (and a bench execute) can see."""
	shifts = stale_shifts()
	managers = _manager_users()
	if not shifts or not managers:
		return {"shifts": shifts, "notified": []}

	count = len(shifts)
	subject = f"{count} van shift{'s' if count != 1 else ''} still open from an earlier day"
	lines = "".join(
		f"<li><b>{frappe.utils.escape_html(s['driver_name'])}</b>: {s['name']} from "
		f"{formatdate(s['shift_date'])} ({s['days_open']} day{'s' if s['days_open'] != 1 else ''} ago)</li>"
		for s in shifts
	)
	body = (
		"<p>These shifts were never closed, so their cash is not reconciled and the drivers "
		"cannot open a new shift until they are:</p>"
		f"<ul>{lines}</ul>"
		"<p>Close them from the manager dashboard in the Van Sale app (oldest first), or ask the driver to.</p>"
	)
	notified = []
	for user in managers:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"subject": subject,
				"for_user": user,
				"type": "Alert",
				"document_type": "Van Shift Opening",
				"document_name": shifts[0]["name"],
				"from_user": "Administrator",
				"email_content": body,
			}
		).insert(ignore_permissions=True)
		notified.append(user)
	return {"shifts": shifts, "notified": notified}
