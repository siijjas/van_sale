"""
Van Cash Movement: cash leaving the driver's drawer mid-shift, with accounting.

Modelled on POS Awesome's POS Cash Movement. Two kinds:

- Expense: the driver pays something (fuel, tolls, a repair) out of the drawer.
  Journal Entry: debit the expense account, credit the drawer's cash account.
- Deposit: the driver hands cash over to the office before the shift closes.
  Journal Entry: debit the back-office cash account, credit the drawer's cash account.

Either way the drawer holds less, so the shift closing subtracts both from the
expected cash of the cash row (shift._compute_closing). The movement is linked to
the shift it was made in, so the closing picks it up by that link rather than by
date — our own doctype can carry the shift stamp even though the ERPNext documents
don't (see dual-mode decisions: no custom fields on Sales Order / Payment Entry).

The accounts come from the Van Profile at validate time and are frozen on the
document, so a later profile change never alters what a submitted movement posted.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowdate


MOVEMENT_TYPES = ("Expense", "Deposit")


class VanCashMovement(Document):
	def validate(self):
		if self.movement_type not in MOVEMENT_TYPES:
			frappe.throw(f"Movement Type must be one of: {', '.join(MOVEMENT_TYPES)}")
		if flt(self.amount) <= 0:
			frappe.throw("Amount must be greater than zero.")
		self.posting_date = self.posting_date or nowdate()

		self._validate_shift()
		profile = self._profile()
		self._validate_profile_rules(profile)
		self._resolve_accounts(profile)

	def _validate_shift(self):
		"""The movement belongs to an open shift of the same driver: cash can only
		leave a drawer that is currently open, and closing reconciles it."""
		opening = frappe.db.get_value(
			"Van Shift Opening",
			self.opening_shift,
			["driver", "docstatus", "status", "company", "van_profile"],
			as_dict=True,
		)
		if not opening:
			frappe.throw(f"Shift {self.opening_shift} was not found.")
		if opening.docstatus != 1 or opening.status != "Open":
			frappe.throw("Cash movements can only be recorded on an open shift.")
		if self.driver and self.driver != opening.driver:
			frappe.throw("The shift belongs to a different staff member.")
		self.driver = opening.driver
		self.company = self.company or opening.company
		self.van_profile = self.van_profile or opening.van_profile
		if not self.company:
			frappe.throw("Company is required.")

	def _profile(self):
		if not self.van_profile:
			return None
		return frappe.get_cached_doc("Van Profile", self.van_profile)

	def _validate_profile_rules(self, profile):
		if not profile:
			return
		if self.movement_type == "Expense" and not profile.allow_expense:
			frappe.throw("Expenses are not enabled on your profile.", frappe.PermissionError)
		if self.movement_type == "Deposit" and not profile.allow_cash_deposit:
			frappe.throw("Cash deposits are not enabled on your profile.", frappe.PermissionError)
		max_amount = flt(profile.cash_movement_max_amount)
		if max_amount and flt(self.amount) > max_amount:
			frappe.throw(
				f"Amount exceeds the maximum of {frappe.format_value(max_amount, {'fieldtype': 'Currency'})} "
				"per cash movement allowed on your profile."
			)
		if profile.require_cash_movement_remarks and not (self.remarks or "").strip():
			frappe.throw("Remarks are required for cash movements on your profile.")
		if self.movement_type == "Expense":
			allowed = [row.account for row in (profile.allowed_expense_accounts or []) if row.account]
			if allowed and self.expense_account and self.expense_account not in allowed:
				frappe.throw(f"Expense account {self.expense_account} is not allowed on your profile.")

	def _resolve_accounts(self, profile):
		"""Fill source / target from the profile, then check they make sense."""
		self.source_account = self.source_account or resolve_cash_account(profile, self.company)
		if not self.source_account:
			frappe.throw(
				"No cash drawer account found. Set a Cash Drawer Account or a Default Cash Mode "
				"with an account for this company on the Van Profile."
			)

		if self.movement_type == "Expense":
			self.expense_account = self.expense_account or (profile.expense_account if profile else None)
			if not self.expense_account:
				frappe.throw("Select an expense account.")
			self.target_account = self.expense_account
		else:
			self.expense_account = None
			self.target_account = self.target_account or resolve_back_office_account(profile, self.company)
			if not self.target_account:
				frappe.throw(
					"No back office cash account found. Set one on the Van Profile, or a default "
					"cash account on the company."
				)

		if self.source_account == self.target_account:
			frappe.throw("Source and target accounts must be different.")

		for fieldname, label in (("source_account", "Source account"), ("target_account", "Target account")):
			account = frappe.db.get_value(
				"Account", self.get(fieldname), ["company", "is_group", "root_type", "account_type"], as_dict=True
			)
			if not account:
				frappe.throw(f"{label} {self.get(fieldname)} was not found.")
			if account.company != self.company:
				frappe.throw(f"{label} {self.get(fieldname)} does not belong to {self.company}.")
			if account.is_group:
				frappe.throw(f"{label} {self.get(fieldname)} is a group account.")
		if self.movement_type == "Expense":
			root_type = frappe.db.get_value("Account", self.target_account, "root_type")
			if root_type != "Expense":
				frappe.throw(f"{self.target_account} is not an expense account.")

		self.cost_center = (
			self.cost_center
			or (profile.cost_center if profile else None)
			or frappe.get_cached_value("Company", self.company, "cost_center")
		)

	# ─── Accounting ────────────────────────────────────────────────────────

	def on_submit(self):
		self.db_set("journal_entry", self._make_journal_entry())

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Journal Entry",)
		if self.journal_entry and frappe.db.exists("Journal Entry", self.journal_entry):
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			if je.docstatus == 1:
				je.flags.ignore_permissions = True
				# The movement keeps its link for the audit trail; cancelling through
				# this controlled path is the only way the JE should ever go.
				je.flags.ignore_links = True
				frappe.flags.ignore_account_permission = True
				je.cancel()

	def _make_journal_entry(self) -> str:
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.company
		je.posting_date = self.posting_date
		who = frappe.utils.get_fullname(self.driver)
		detail = f" ({self.against_name})" if self.against_name else ""
		je.user_remark = f"Van cash {self.movement_type.lower()} {self.name} by {who}{detail}"
		if self.remarks:
			je.user_remark += f": {self.remarks}"
		je.append(
			"accounts",
			{
				"account": self.target_account,
				"debit_in_account_currency": flt(self.amount),
				"credit_in_account_currency": 0,
				"cost_center": self.cost_center,
			},
		)
		je.append(
			"accounts",
			{
				"account": self.source_account,
				"debit_in_account_currency": 0,
				"credit_in_account_currency": flt(self.amount),
				"cost_center": self.cost_center,
			},
		)
		# The driver role holds no Journal Entry / Account permissions; authorization
		# was done by the endpoint (cash_movement.create_cash_movement) and this doc's
		# own validate(). Same pattern as Payment Entry / Sales Invoice in sales.py.
		je.flags.ignore_permissions = True
		frappe.flags.ignore_account_permission = True
		je.insert()
		je.submit()
		return je.name


# ─── Account resolution (shared with the API / profile editor) ─────────────────

def resolve_cash_account(profile, company: str) -> str | None:
	"""The drawer account: an explicit Cash Drawer Account on the profile, else the
	account the profile's Default Cash Mode maps to for this company (how ERPNext
	itself routes a cash Payment Entry), else the company default cash account."""
	if profile and profile.cash_account:
		return profile.cash_account
	if profile and profile.default_cash_mode:
		account = frappe.db.get_value(
			"Mode of Payment Account",
			{"parent": profile.default_cash_mode, "company": company},
			"default_account",
		)
		if account:
			return account
	return frappe.get_cached_value("Company", company, "default_cash_account")


def resolve_back_office_account(profile, company: str) -> str | None:
	if profile and profile.back_office_cash_account:
		return profile.back_office_cash_account
	return frappe.get_cached_value("Company", company, "default_cash_account")
