"""Whitelisted methods for the Gap Analysis tracker."""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

# kind -> (workflow action, {field: arg}, (result_field, value) or None)
ACTIONS = {
	"analyse": ("Analyse", {}, None),
	"submit": ("Submit for Approval", {}, None),
	"close_fit": ("Close as Fit", {}, None),
	"approve": ("Approve", {"decision_notes": "notes"}, None),
	"reject": ("Reject", {"decision_notes": "notes"}, None),
	"defer": ("Defer", {"decision_notes": "notes"}, None),
	"send_back": ("Send Back", {"decision_notes": "notes"}, None),
	"start": ("Start Work", {}, None),
	"deliver": ("Mark Delivered", {"delivery_notes": "notes", "delivered_in_build": "build"}, None),
	"verify_pass": ("Verify", {"verification_notes": "notes"}, ("verification_result", "Pass")),
	"verify_fail": ("Verification Failed", {"verification_notes": "notes"}, ("verification_result", "Fail")),
	"close": ("Close", {}, None),
	"reopen": ("Reopen", {}, None),
}


def _list(value):
	if not value:
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			value = [value]
	return [v for v in value if v]


@frappe.whitelist()
def record(gap, kind, notes=None, build=None, evidence=None):
	"""Set the details for a stage, then apply the workflow action."""
	from frappe.model.workflow import apply_workflow

	if kind not in ACTIONS:
		frappe.throw(_("Unknown action"))
	action, mapping, result = ACTIONS[kind]
	doc = frappe.get_doc("Gap Item", gap)
	doc.check_permission("write")
	values = {"notes": notes, "build": build}
	for field, key in mapping.items():
		if values.get(key):
			doc.set(field, values[key])
	if result:
		doc.set(result[0], result[1])
	for url in _list(evidence):
		doc.append("verification_evidence" if kind.startswith("verify") else "evidence",
			{"file": url, "added_by": frappe.session.user})
	doc.save()  # apply_workflow reloads from the database, so persist first
	doc = apply_workflow(doc, action)
	return doc.status


@frappe.whitelist()
def add_update(gap, message, attachment=None):
	frappe.has_permission("Gap Item", "read", doc=gap, throw=True)
	message = (message or "").strip()
	if not message and not attachment:
		frappe.throw(_("Write a message or attach a file"))
	idx = frappe.db.sql("select ifnull(max(idx),0) from `tabGap Update` where parent=%s", gap)[0][0]
	row = frappe.get_doc({
		"doctype": "Gap Update", "parent": gap, "parenttype": "Gap Item", "parentfield": "updates", "idx": idx + 1,
		"posted_on": now_datetime(), "posted_by": frappe.session.user, "update_type": "Comment",
		"message": message or _("File attached"), "attachment": attachment,
	})
	row.db_insert()
	frappe.db.set_value("Gap Item", gap, "modified_by", frappe.session.user)
	from qa_tracker.gap_analysis import notify

	notify.on_update_posted(gap, row)
	return row.name


@frappe.whitelist()
def create_from_issue(issue, fit_status="Gap", priority=None):
	"""Turn a QA ticket (typically a Change Request or Query found in testing) into a gap item."""
	src = frappe.get_doc("QA Issue", issue)
	src.check_permission("read")
	existing = frappe.db.get_value("Gap Item", {"created_from_issue": issue})
	if existing:
		return existing
	gap = frappe.get_doc({
		"doctype": "Gap Item",
		"title": src.title,
		"fit_status": fit_status,
		"priority": priority or ("Must Have" if src.severity == "Blocker" else "Should Have"),
		"business_impact": "High" if src.severity in ("Blocker", "High") else "Medium",
		"gap_type": "Integration" if src.issue_type == "Integration" else ("Data / Migration" if src.issue_type == "Data Migration" else "Functional"),
		"site": src.site,
		"module": src.module,
		"project": src.get("project"),
		"vendor": src.get("vendor"),
		"process_name": src.screen,
		"requirement": src.description,
		"system_behaviour": src.actual_result,
		"source": "Go-Live Issue" if src.found_in_phase == "Test" and src.test_cycle and "go-live" in (src.test_cycle or "").lower() else "Testing / UAT",
		"reference": src.name,
		"raised_by": src.reported_by or frappe.session.user,
		"created_from_issue": src.name,
		"linked_issues": [{"issue": src.name}],
		"evidence": [{"file": s.image, "caption": s.caption, "added_by": s.added_by} for s in src.screenshots if s.image],
	})
	gap.insert()
	from qa_tracker.utils import append_update

	append_update(src.name, _("Logged as gap {0} for analysis").format(gap.name), update_type="Comment", notify=False)
	return gap.name


@frappe.whitelist()
def create_test_case(gap):
	"""Create a QA Test Case that verifies the delivered gap, and link it."""
	doc = frappe.get_doc("Gap Item", gap)
	doc.check_permission("write")
	if not doc.module:
		frappe.throw(_("Set the module first"))
	tc = frappe.get_doc({
		"doctype": "QA Test Case",
		"title": f"Verify {doc.gap_code or doc.name}: {doc.title}"[:140],
		"module": doc.module,
		"screen": doc.process_name,
		"priority": {"Must Have": "Critical", "Should Have": "High", "Could Have": "Medium"}.get(doc.priority, "Medium"),
		"reference": doc.name,
		"steps": doc.proposed_solution or doc.requirement or doc.title,
		"expected_result": frappe.utils.strip_html(doc.requirement or "") or doc.title,
	}).insert()
	doc.append("linked_test_cases", {"test_case": tc.name})
	doc.save()
	return tc.name


@frappe.whitelist()
def link_issue(gap, issue):
	doc = frappe.get_doc("Gap Item", gap)
	doc.check_permission("write")
	if not any(r.issue == issue for r in doc.linked_issues):
		doc.append("linked_issues", {"issue": issue})
		doc.save()
	return gap
