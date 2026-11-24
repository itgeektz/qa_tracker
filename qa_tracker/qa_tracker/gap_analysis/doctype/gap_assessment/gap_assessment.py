# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

OPEN = ("Identified", "Analysed", "Awaiting Approval", "Approved", "In Progress", "Delivered", "Verified")


class GapAssessment(Document):
	def validate(self):
		if self.status == "Signed Off" and not self.signed_off_by:
			frappe.throw(_("Use the Sign Off button so the approver and date are recorded"))

	@frappe.whitelist()
	def sign_off(self, comments=None):
		roles = set(frappe.get_roles())
		if frappe.session.user != self.approver and not roles & {"QA Lead", "GA Approver", "System Manager"}:
			frappe.throw(_("Only the business approver can sign off this assessment"), frappe.PermissionError)
		pending = frappe.db.count("Gap Item", {"assessment": self.name, "status": ["in", ["Identified", "Analysed"]]})
		if pending:
			frappe.throw(_("{0} items are still being analysed. Finish the analysis before sign-off.").format(pending))
		self.signed_off_by = frappe.session.user
		self.signed_off_on = now_datetime()
		self.signoff_comments = comments or self.signoff_comments
		self.status = "Signed Off"
		self.save()
		return self.status


def update_summary(assessment):
	if not frappe.db.exists("Gap Assessment", assessment):
		return
	rows = frappe.get_all("Gap Item", filters={"assessment": assessment},
		fields=["fit_status", "status", "priority", "effort_days", "estimated_cost"])
	counted = [r for r in rows if r.fit_status != "Not Applicable"]
	fit = sum(1 for r in counted if r.fit_status == "Fit")
	partial = sum(1 for r in counted if r.fit_status == "Partial Fit")
	gap = sum(1 for r in counted if r.fit_status == "Gap")
	active = [r for r in rows if r.fit_status in ("Gap", "Partial Fit") and r.status not in ("Rejected", "Deferred")]
	frappe.db.set_value("Gap Assessment", assessment, {
		"total_items": len(rows),
		"fit_count": fit,
		"partial_count": partial,
		"gap_count": gap,
		"fit_percent": round(100.0 * (fit + 0.5 * partial) / len(counted), 1) if counted else 0,
		"open_must_haves": sum(1 for r in active if r.priority == "Must Have" and r.status in OPEN),
		"total_effort_days": sum(flt(r.effort_days) for r in active),
		"total_cost": sum(flt(r.estimated_cost) for r in active),
		"closed_count": sum(1 for r in rows if r.status == "Closed"),
	}, update_modified=False)
