import frappe


def execute():
	"""Drop the orphaned Driver Configuration doctypes.

	Driver Configuration (and its child Driver Allowed Payment Mode) were never
	read or written by application code. The runtime driver config is derived
	entirely from Van Profile via get_van_profile_for_driver(), so these tables
	are dead schema. Removing them makes Van Profile the single source of truth
	and eliminates the risk of the two configurations drifting apart.
	"""
	for doctype in ("Driver Configuration", "Driver Allowed Payment Mode"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
		# delete_doc can leave the physical table behind; drop it explicitly.
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")
