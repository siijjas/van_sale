import frappe


def execute():
	"""Every Van Profile that existed before profile types were introduced is a van:
	both warehouses were mandatory and the shift screens were always on. Stamp them
	explicitly so the new Field Sales branch can never match an old row by accident
	(an empty profile_type / use_shifts would otherwise read as falsy)."""
	if not frappe.db.has_column("Van Profile", "profile_type"):
		return
	frappe.db.sql(
		"""update `tabVan Profile`
		set profile_type = 'Van Sales'
		where ifnull(profile_type, '') = ''"""
	)
	frappe.db.sql("""update `tabVan Profile` set use_shifts = 1 where ifnull(use_shifts, 0) = 0""")
	frappe.cache.delete_keys("van_sale:driver_config:")
