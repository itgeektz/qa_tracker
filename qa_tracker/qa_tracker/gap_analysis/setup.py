"""Install / migrate setup for the Gap Analysis module (idempotent)."""

import json

import frappe

ROLES = {
	"GA Analyst": "Business analyst: records requirements, assesses fit, proposes solutions",
	"GA Approver": "Business owner / steering committee: approves, rejects or defers gaps and signs off assessments",
}

STATE_STYLE = {
	"Identified": "Primary",
	"Analysed": "Info",
	"Awaiting Approval": "Warning",
	"Approved": "Success",
	"In Progress": "Warning",
	"Delivered": "Info",
	"Verified": "Success",
	"Closed": "Success",
	"Deferred": "Inverse",
	"Rejected": "Inverse",
	"Merged": "Inverse",
}

STATE_EDITORS = {
	"Identified": ["GA Analyst", "QA Lead", "QA Tester", "UAT User"],
	"Analysed": ["GA Analyst", "QA Lead"],
	"Awaiting Approval": ["GA Approver", "GA Analyst", "QA Lead"],
	"Approved": ["GA Analyst", "QA Lead", "Vendor Developer"],
	"In Progress": ["Vendor Developer", "GA Analyst", "QA Lead"],
	"Delivered": ["QA Tester", "UAT User", "GA Analyst", "QA Lead"],
	"Verified": ["GA Approver", "GA Analyst", "QA Lead"],
	"Closed": ["GA Analyst", "QA Lead"],
	"Deferred": ["GA Analyst", "QA Lead"],
	"Rejected": ["GA Analyst", "QA Lead"],
	"Merged": ["GA Analyst", "QA Lead"],
}

FIT_COND = "doc.fit_status in ('Fit', 'Not Applicable')"
TRANSITIONS = [
	("Identified", "Analyse", "Analysed", ["GA Analyst", "QA Lead"], None),
	("Identified", "Close as Fit", "Closed", ["GA Analyst", "QA Lead"], FIT_COND),
	("Analysed", "Close as Fit", "Closed", ["GA Analyst", "QA Lead"], FIT_COND),
	("Analysed", "Submit for Approval", "Awaiting Approval", ["GA Analyst", "QA Lead"],
		"doc.resolution_approach and doc.business_owner and doc.fit_status in ('Gap', 'Partial Fit')"),
	("Awaiting Approval", "Approve", "Approved", ["GA Approver", "QA Lead"], None),
	("Awaiting Approval", "Reject", "Rejected", ["GA Approver", "QA Lead"], None),
	("Awaiting Approval", "Defer", "Deferred", ["GA Approver", "QA Lead"], None),
	("Awaiting Approval", "Send Back", "Analysed", ["GA Approver", "QA Lead"], None),
	("Approved", "Start Work", "In Progress", ["Vendor Developer", "GA Analyst", "QA Lead"], None),
	("Approved", "Mark Delivered", "Delivered", ["Vendor Developer", "GA Analyst", "QA Lead"], "doc.delivery_notes"),
	("In Progress", "Mark Delivered", "Delivered", ["Vendor Developer", "GA Analyst", "QA Lead"], "doc.delivery_notes"),
	("Delivered", "Verify", "Verified", ["QA Tester", "UAT User", "GA Analyst", "QA Lead"], "doc.verification_result == 'Pass'"),
	("Delivered", "Verification Failed", "In Progress", ["QA Tester", "UAT User", "GA Analyst", "QA Lead"], "doc.verification_result == 'Fail'"),
	("Verified", "Close", "Closed", ["GA Approver", "GA Analyst", "QA Lead"], None),
	("Deferred", "Reopen", "Analysed", ["GA Analyst", "QA Lead"], None),
	("Rejected", "Reopen", "Analysed", ["GA Analyst", "QA Lead"], None),
	("Closed", "Reopen", "Analysed", ["GA Analyst", "QA Lead"], None),
]

OPEN_STATES = ["Identified", "Analysed", "Awaiting Approval", "Approved", "In Progress", "Delivered", "Verified"]


def create_roles():
	for role, desc in ROLES.items():
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1, "description": desc}).insert(
				ignore_permissions=True
			)


def setup():
	create_roles()
	create_workflow()
	create_dashboard()
	create_workspace()
	create_kanban()


def create_workflow():
	for state, style in STATE_STYLE.items():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state, "style": style}).insert(
				ignore_permissions=True
			)
	for action in sorted({t[1] for t in TRANSITIONS}):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)
	name = "Gap Item Workflow"
	wf = frappe.get_doc("Workflow", name) if frappe.db.exists("Workflow", name) else frappe.new_doc("Workflow")
	wf.workflow_name = name
	wf.document_type = "Gap Item"
	wf.workflow_state_field = "status"
	wf.is_active = 1
	wf.send_email_alert = 0
	wf.override_status = 0
	wf.set("states", [])
	for state, roles in STATE_EDITORS.items():
		for role in roles:
			wf.append("states", {"state": state, "doc_status": "0", "allow_edit": role})
	wf.set("transitions", [])
	for frm, action, to, roles, cond in TRANSITIONS:
		for role in roles:
			wf.append("transitions", {"state": frm, "action": action, "next_state": to, "allowed": role,
				"allow_self_approval": 1, "condition": cond or ""})
	wf.flags.ignore_permissions = True
	wf.save()


def _upsert(doctype, name, values):
	if frappe.db.exists(doctype, name):
		doc = frappe.get_doc(doctype, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc(dict(doctype=doctype, **values)).insert(ignore_permissions=True)


def create_dashboard():
	open_f = ["Gap Item", "status", "in", OPEN_STATES, False]
	cards = [
		("Open Gaps", [open_f, ["Gap Item", "fit_status", "in", ["Gap", "Partial Fit"], False]], "#2490EF"),
		("Open Must-Have Gaps", [open_f, ["Gap Item", "priority", "=", "Must Have", False],
			["Gap Item", "fit_status", "in", ["Gap", "Partial Fit"], False]], "#E24C4C"),
		("Gaps Awaiting Approval", [["Gap Item", "status", "=", "Awaiting Approval", False]], "#ECAD4B"),
		("Gaps Awaiting Verification", [["Gap Item", "status", "=", "Delivered", False]], "#7575FF"),
		("Gaps Closed", [["Gap Item", "status", "=", "Closed", False]], "#29CD42"),
	]
	for label, filters, color in cards:
		_upsert("Number Card", label, {"name": label, "label": label, "type": "Document Type", "document_type": "Gap Item",
			"function": "Count", "filters_json": json.dumps(filters), "is_public": 1, "color": color, "module": "Gap Analysis"})

	open_json = json.dumps([open_f])
	charts = [
		("Gaps by Fit Status", "fit_status", "[]", "Donut", "Count", None),
		("Open Gaps by Module", "module", open_json, "Bar", "Count", None),
		("Gaps by Resolution Approach", "resolution_approach", "[]", "Bar", "Count", None),
		("Open Gaps by Priority", "priority", open_json, "Bar", "Count", None),
		("Gaps by Status", "status", "[]", "Bar", "Count", None),
		("Gap Effort by Module (days)", "module", "[]", "Bar", "Sum", "effort_days"),
	]
	for name, field, filters, ctype, agg, based_on in charts:
		values = {"chart_name": name, "chart_type": "Group By", "document_type": "Gap Item", "group_by_type": agg,
			"group_by_based_on": field, "number_of_groups": 0, "filters_json": filters, "type": ctype,
			"is_public": 1, "timeseries": 0, "module": "Gap Analysis"}
		if based_on:
			values["aggregate_function_based_on"] = based_on
		_upsert("Dashboard Chart", name, values)


def create_workspace():
	name = "Gap Analysis"
	cards = ["Open Gaps", "Open Must-Have Gaps", "Gaps Awaiting Approval", "Gaps Awaiting Verification", "Gaps Closed"]
	charts = ["Gaps by Fit Status", "Open Gaps by Module", "Open Gaps by Priority", "Gaps by Resolution Approach",
		"Gap Effort by Module (days)", "Gaps by Status"]
	shortcuts = [
		("New Gap", "URL", None, "/app/gap-item/new", "Blue"),
		("Gap Register", "DocType", "Gap Item", None, "Grey"),
		("Gap Board", "URL", None, "/app/gap-item/view/kanban/Gap Board", "Purple"),
		("Assessments", "DocType", "Gap Assessment", None, "Orange"),
		("Fit-Gap Summary", "Report", "Gap Register Summary", None, "Green"),
		("QA Tracker", "URL", None, "/app/qa-tracker", "Grey"),
	]
	content = []
	for i, c in enumerate(cards):
		content.append({"id": f"gnc{i}", "type": "number_card", "data": {"number_card_name": c, "col": 4 if i < 3 else 6}})
	for i, s in enumerate(shortcuts):
		content.append({"id": f"gsc{i}", "type": "shortcut", "data": {"shortcut_name": s[0], "col": 4}})
	for i, c in enumerate(charts):
		content.append({"id": f"gch{i}", "type": "chart", "data": {"chart_name": c, "col": 6}})
	content.append({"id": "gcd0", "type": "card", "data": {"card_name": "Gap Analysis", "col": 6}})

	for c in cards:
		if not frappe.db.exists("Number Card", c):
			frappe.throw(f"Number Card {c} missing")
	ws = frappe.get_doc("Workspace", name) if frappe.db.exists("Workspace", name) else frappe.new_doc("Workspace")
	ws.update({"name": name, "label": name, "title": name, "module": "Gap Analysis", "public": 1, "icon": "list",
		"sequence_id": 51, "content": json.dumps(content)})
	ws.set("number_cards", [{"number_card_name": c, "label": c} for c in cards])
	ws.set("charts", [{"chart_name": c, "label": c} for c in charts])
	ws.set("shortcuts", [])
	for label, typ, link_to, url, color in shortcuts:
		row = {"label": label, "type": typ, "color": color}
		if typ == "URL":
			row["url"] = url
		else:
			row["link_to"] = link_to
		ws.append("shortcuts", row)
	ws.set("links", [])
	links = [("Gap Items", "Gap Item"), ("Gap Assessments", "Gap Assessment"), ("Sites", "QA Site"), ("Modules", "QA Module")]
	ws.append("links", {"type": "Card Break", "label": "Gap Analysis", "link_count": len(links)})
	for label, dt in links:
		ws.append("links", {"type": "Link", "label": label, "link_type": "DocType", "link_to": dt})
	ws.flags.ignore_permissions = True
	ws.flags.ignore_links = True
	ws.save() if not ws.is_new() else ws.insert()


def create_kanban():
	name = "Gap Board"
	if frappe.db.exists("Kanban Board", name):
		return
	board = frappe.get_doc({"doctype": "Kanban Board", "kanban_board_name": name, "reference_doctype": "Gap Item",
		"field_name": "status", "private": 0, "show_labels": 0,
		"fields": json.dumps(["priority", "fit_status", "module"])})
	for state in STATE_STYLE:
		board.append("columns", {"column_name": state, "status": "Active", "indicator": "Gray"})
	board.insert(ignore_permissions=True)
