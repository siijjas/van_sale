import frappe

# X/Y reports were renamed to Shift Summary / Closing Report.
RENAMES = {
	"Van Shift X Report": "Van Shift Summary",
	"Van Shift Y Report": "Van Shift Closing Report",
}


def execute():
	"""Rename the print formats in place before the model sync, so the sync updates the
	renamed record instead of creating a second one next to the old. Renaming keeps any
	default_print_format Property Setter pointing at it (Print Format.after_rename)."""
	for old, new in RENAMES.items():
		if not frappe.db.exists("Print Format", old):
			continue
		if frappe.db.exists("Print Format", new):
			frappe.delete_doc("Print Format", old, force=True, ignore_permissions=True)
		else:
			frappe.rename_doc("Print Format", old, new, force=True)
