# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import getseries
from frappe.utils import now_datetime, nowdate

from qa_tracker.compat import after_commit, assign

DECISIONS = {"Approved": "Approved", "Rejected": "Rejected", "Deferred": "Deferred"}


class GapItem(Document):
	def before_insert(self):
		if not self.raised_by and frappe.session.user not in ("Guest", "Administrator"):
			self.raised_by = frappe.session.user
		if not self.raised_on:
			self.raised_on = nowdate()
		if self.assessment:
			a = frappe.db.get_value("Gap Assessment", self.assessment, ["site", "module", "approver"], as_dict=True) or {}
			self.site = self.site or a.get("site")
			self.module = self.module or a.get("module")
			self.business_owner = self.business_owner or a.get("approver")

	def validate(self):
		self.title = (self.title or "").strip()[:240]
		if self.fit_status in ("Fit", "Not Applicable") and not self.resolution_approach:
			self.resolution_approach = "Not Required"
		self.set_gap_code()
		for table in ("evidence", "verification_evidence"):
			for row in self.get(table):
				if not row.added_by and frappe.session.user != "Guest":
					row.added_by = frappe.session.user
		self.handle_status_change()

	def on_update(self):
		before = self.get_doc_before_save()
		old = before.status if before else None
		if old != self.status:
			if self.status == "Awaiting Approval" and self.business_owner:
				assign(self.doctype, self.name, self.business_owner, description=_("Approve gap: {0}").format(self.title),
					priority="High" if self.priority == "Must Have" else "Medium")
			if self.status == "Approved" and self.assigned_to:
				assign(self.doctype, self.name, self.assigned_to, description=_("Deliver gap: {0}").format(self.title))
			if old:
				from qa_tracker.gap_analysis import notify

				name, new = self.name, self.status
				after_commit(lambda: notify.on_status_change(name, old, new))
		if self.assessment:
			from qa_tracker.gap_analysis.doctype.gap_assessment.gap_assessment import update_summary

			update_summary(self.assessment)
		if before and before.assessment and before.assessment != self.assessment:
			from qa_tracker.gap_analysis.doctype.gap_assessment.gap_assessment import update_summary

			update_summary(before.assessment)

	def on_trash(self):
		self.flags.assessment = self.assessment

	def after_delete(self):
		if self.flags.assessment:
			from qa_tracker.gap_analysis.doctype.gap_assessment.gap_assessment import update_summary

			update_summary(self.flags.assessment)

	# ------------------------------------------------------------------
	def set_gap_code(self):
		"""SITE-MODULE-G### ; follows site/module while the gap is still being identified."""
		if not (self.site and self.module):
			return
		site_code = frappe.db.get_value("QA Site", self.site, "site_code")
		module_code = frappe.db.get_value("QA Module", self.module, "module_code")
		if not (site_code and module_code):
			return
		prefix = f"{site_code}-{module_code}-G".upper()
		if self.gap_code and (self.gap_code.startswith(prefix) or self.status not in (None, "", "Identified")):
			return
		self.gap_code = prefix + getseries(prefix, 3)

	def handle_status_change(self):
		before = self.get_doc_before_save()
		old = before.status if before else None
		new = self.status
		if not old or old == new:
			return
		user, now = frappe.session.user, now_datetime()
		if old == "Awaiting Approval" and new in DECISIONS:
			self.decision = DECISIONS[new]
			self.approved_by, self.approved_on = user, now
			self.add_row("Decision", _("{0}{1}").format(_(new).upper(), f": {self.decision_notes}" if self.decision_notes else ""))
		if new == "Analysed" and old == "Awaiting Approval":
			self.decision = "Pending"
			self.add_row("Decision", _("Sent back for analysis{0}").format(f": {self.decision_notes}" if self.decision_notes else ""))
		if new == "Delivered":
			self.delivered_on = now
			self.verification_result = "Pending"
			self.add_row("Delivery", _("Delivered{0}: {1}").format(
				f" in {self.delivered_in_build}" if self.delivered_in_build else "", self.delivery_notes or ""))
		if old == "Delivered" and new in ("Verified", "In Progress"):
			self.verified_by, self.verified_on = user, now
			self.add_row("Verification", _("Verification {0}{1}").format(
				_("PASSED") if new == "Verified" else _("FAILED"), f": {self.verification_notes}" if self.verification_notes else ""))
		if new == "Closed":
			self.closed_on = now
		if old in ("Closed", "Rejected", "Deferred") and new == "Analysed":
			self.reopen_count = (self.reopen_count or 0) + 1
			self.closed_on = None
			self.decision = "Pending"
		self.add_row("Status Change", f"{old} → {new}")

	def add_row(self, update_type, message):
		self.append("updates", {
			"posted_on": now_datetime(),
			"posted_by": frappe.session.user if frappe.session.user != "Guest" else None,
			"update_type": update_type,
			"message": message,
		})
