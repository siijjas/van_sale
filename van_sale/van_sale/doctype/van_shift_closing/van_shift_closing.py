import frappe
from frappe.model.document import Document


class VanShiftClosing(Document):
	def on_submit(self):
		self._set_opening_status("Closed")

	def on_cancel(self):
		self._set_opening_status("Open")

	def _set_opening_status(self, status: str):
		if not self.opening_shift:
			return
		frappe.db.set_value("Van Shift Opening", self.opening_shift, "status", status)
