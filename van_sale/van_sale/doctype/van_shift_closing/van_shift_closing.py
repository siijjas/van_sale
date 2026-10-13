import frappe
from frappe.model.document import Document
from frappe.utils import flt

VARIANCE_BALANCED = "Balanced"
VARIANCE_WITHIN = "Within Tolerance"
VARIANCE_EXCEEDS = "Exceeds Tolerance"


def variance_status(net_difference: float, tolerance: float) -> str:
	"""Flag-only classification of a closing's cash difference against the profile's
	tolerance. Never blocks a closing; the manager dashboard and reports surface it."""
	diff = abs(flt(net_difference))
	if diff < 0.005:
		return VARIANCE_BALANCED
	if diff <= flt(tolerance) + 0.005:
		return VARIANCE_WITHIN
	return VARIANCE_EXCEEDS


class VanShiftClosing(Document):
	def validate(self):
		self.variance_status = variance_status(self.net_difference, self.variance_tolerance)

	def on_submit(self):
		self._update_opening("Closed", self.name, self.period_end)

	def on_cancel(self):
		# Reopening: the opening goes back to Open with no closing or end time, so the
		# shift carries on until it is closed again (with a fresh period_end).
		self.ignore_linked_doctypes = ("Van Shift Opening",)
		self._update_opening("Open", None, None)

	def _update_opening(self, status: str, closing_shift: str | None, period_end):
		if not self.opening_shift:
			return
		frappe.db.set_value(
			"Van Shift Opening",
			self.opening_shift,
			{"status": status, "closing_shift": closing_shift, "period_end": period_end},
		)
