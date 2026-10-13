import frappe


def execute():
	"""Shift closings now carry a variance status (flag-only, against the profile's
	tolerance) and openings point back at their closing with the period end. Fill
	both in for closings made before these fields existed. Old closings get a zero
	tolerance, so any difference reads as Exceeds Tolerance, which is what the manager
	dashboard alerted on before tolerances existed."""
	if not frappe.db.has_column("Van Shift Closing", "variance_status"):
		return
	frappe.db.sql(
		"""update `tabVan Shift Closing`
		set variance_tolerance = ifnull(variance_tolerance, 0),
			variance_status = case
				when abs(ifnull(net_difference, 0)) < 0.005 then 'Balanced'
				when abs(ifnull(net_difference, 0)) <= ifnull(variance_tolerance, 0) + 0.005 then 'Within Tolerance'
				else 'Exceeds Tolerance' end
		where ifnull(variance_status, '') = ''"""
	)
	if frappe.db.has_column("Van Shift Opening", "closing_shift"):
		frappe.db.sql(
			"""update `tabVan Shift Opening` o
			join `tabVan Shift Closing` c on c.opening_shift = o.name and c.docstatus = 1
			set o.closing_shift = c.name, o.period_end = c.period_end
			where ifnull(o.closing_shift, '') = ''"""
		)
