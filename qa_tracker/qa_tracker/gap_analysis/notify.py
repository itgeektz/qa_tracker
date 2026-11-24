"""Notifications for gap items: in-app, email (if configured) and Raven DM (if enabled)."""

import frappe
from frappe import _
from frappe.utils import escape_html

from qa_tracker.utils import settings, site_base_url

# new status -> who to tell
WHO = {
	"Awaiting Approval": ["business_owner"],
	"Approved": ["assigned_to", "raised_by"],
	"Rejected": ["raised_by"],
	"Deferred": ["raised_by"],
	"Delivered": ["raised_by", "business_owner"],
	"In Progress": ["assigned_to"],
	"Verified": ["business_owner"],
	"Closed": ["raised_by"],
}


def gap_url(name):
	return f"{site_base_url()}/app/gap-item/{name}"


def _safe(fn, *a, **kw):
	try:
		return fn(*a, **kw)
	except Exception:
		frappe.log_error(title="Gap Analysis notification failed", message=frappe.get_traceback())


def send(user, doc, subject, text):
	if not user or user in ("Administrator", "Guest"):
		return
	_safe(lambda: frappe.get_doc({"doctype": "Notification Log", "subject": subject, "email_content": escape_html(text),
		"for_user": user, "type": "Alert", "document_type": "Gap Item", "document_name": doc.name}).insert(ignore_permissions=True))
	s = settings()
	email = frappe.db.get_value("User", user, "email")
	if s.notify_email and email and frappe.db.exists("Email Account", {"enable_outgoing": 1}):
		_safe(frappe.sendmail, recipients=[email], subject=f"[{doc.gap_code or doc.name}] {subject}",
			message=f"<p>{escape_html(text).replace(chr(10), '<br>')}</p><p><a href='{gap_url(doc.name)}'>{_('Open gap')}</a></p>",
			reference_doctype="Gap Item", reference_name=doc.name)
	if s.raven_enabled:
		from qa_tracker.channels import raven

		_safe(raven.send_dm, user, f"{subject}\n{text}\n{gap_url(doc.name)}", issue=doc.name, doctype="Gap Item")


def on_status_change(name, old, new):
	doc = frappe.get_doc("Gap Item", name)
	who = frappe.utils.get_fullname(frappe.session.user)
	subject = f"{doc.gap_code or doc.name}: {doc.title} - {new}"
	text = _("{0} → {1} (by {2})").format(old, new, who)
	if new == "Awaiting Approval":
		text += "\n" + _("Priority: {0} · Approach: {1} · Effort: {2} days").format(doc.priority, doc.resolution_approach or "-", doc.effort_days or 0)
		if doc.proposed_solution:
			text += "\n" + _("Proposed: {0}").format(doc.proposed_solution)
	elif new in ("Rejected", "Deferred", "Approved") and doc.decision_notes:
		text += "\n" + _("Notes: {0}").format(doc.decision_notes)
	elif new == "Delivered":
		text += "\n" + _("Delivered: {0}. Please verify.").format(doc.delivery_notes or "-")
	elif new == "In Progress" and old == "Delivered" and doc.verification_notes:
		text += "\n" + _("Verification failed: {0}").format(doc.verification_notes)
	sent = set()
	for field in WHO.get(new, []):
		user = doc.get(field)
		if user and user not in sent and user != frappe.session.user:
			send(user, doc, subject, text)
			sent.add(user)


def on_update_posted(gap, row):
	doc = frappe.get_doc("Gap Item", gap)
	author = frappe.utils.get_fullname(row.posted_by) if row.posted_by else "-"
	for field in ("business_owner", "assigned_to", "raised_by"):
		user = doc.get(field)
		if user and user != row.posted_by:
			send(user, doc, _("Update on {0}").format(doc.gap_code or doc.name), f"{author}: {row.message}")
