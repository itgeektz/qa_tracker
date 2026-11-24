"""Install / migrate setup: roles, masters, workflow, dashboard, workspace.

Everything here is idempotent so it can run on every `bench migrate`.
"""

import json

import frappe

ROLES = {
	"QA Lead": "Triages, assigns, confirms and closes issues; manages cycles and settings",
	"QA Tester": "Logs issues, runs test cases and retests fixes",
	"Vendor Developer": "Works on assigned issues, records fixes and answers",
	"UAT User": "Business user who accepts or rejects fixes in UAT",
	"QA Viewer": "Read-only access to issues and dashboards",
	"QA Management": "Management: read-only dashboards and reports across their projects",
	"L1 Support": "Hospital helpdesk / super users: first response, triage, how-to answers, escalate to L2",
	"L2 Support": "Application support: configuration and functional fixes, escalate to L3",
	"L3 Support": "Vendor engineering: code fixes for escalated tickets",
}

DEFAULT_SITES = [("Parklands", "PKL"), ("Utawala", "UTW")]

DEFAULT_MODULES = [
	("Registration", "REG", "registration,register,uhid,id proof,patient search,revisit,crid"),
	("Billing & Cash Counter", "BIL", "bill,billing,cash counter,cashier,receipt,payment,credit bill,invoice,collection,interim"),
	("Insurance & SHA", "INS", "insurance,sha,scheme,sponsor,preauth,pre-auth,claim,payor,payer,corporate"),
	("Doctor EMR", "EMR", "emr,doctor,consultation,problem list,progress note,discharge summary,clinical,prescription,medication"),
	("Nursing", "NUR", "nurse,nursing,triage,vitals,ward,mar"),
	("Laboratory", "LAB", "lab,laboratory,sample,specimen,result,analyser,pathologist,culture"),
	("Radiology", "RAD", "radiology,x-ray,xray,mri,ct,ultrasound,imaging,pacs"),
	("Pharmacy", "PHA", "pharmacy,dispense,drug,indent,hold bill,medicine"),
	("Inventory & Stores", "INV", "inventory,store,stock,batch,grn,purchase,recall"),
	("Inpatient", "IPD", "admission,ip,inpatient,bed,discharge,ward transfer"),
	("Printing & Reports", "PRN", "print,printout,logo,watermark,report,certificate"),
	("Integration & HIE", "HIE", "hie,integration,api,xhr,token,smtp,sms,email,interface,client registry"),
	("Administration & Setup", "ADM", "configuration,setup,master,role,user,location,access"),
	("General", "GEN", ""),
]

STATE_STYLE = {
	"New": "Primary",
	"Triaged": "Info",
	"Assigned": "Info",
	"In Progress": "Warning",
	"Ready for Retest": "Warning",
	"Reopened": "Danger",
	"Retest Passed": "Success",
	"Confirmed": "Success",
	"In UAT": "Primary",
	"UAT Accepted": "Success",
	"Answered": "Info",
	"Closed": "Success",
	"Deferred": "Inverse",
	"Rejected": "Inverse",
	"Merged": "Inverse",
}

# state -> roles allowed to edit the document while in that state
STATE_EDITORS = {
	"New": ["QA Tester", "L1 Support", "QA Lead"],
	"Triaged": ["L1 Support", "QA Lead"],
	"Assigned": ["Vendor Developer", "L1 Support", "L2 Support", "L3 Support", "QA Lead"],
	"In Progress": ["Vendor Developer", "L1 Support", "L2 Support", "L3 Support", "QA Lead"],
	"Reopened": ["Vendor Developer", "L2 Support", "L3 Support", "QA Lead"],
	"Ready for Retest": ["QA Tester", "QA Lead"],
	"Retest Passed": ["QA Lead"],
	"Confirmed": ["QA Lead"],
	"In UAT": ["UAT User", "QA Lead"],
	"UAT Accepted": ["QA Lead"],
	"Answered": ["QA Tester", "QA Lead"],
	"Closed": ["QA Lead"],
	"Deferred": ["QA Lead"],
	"Rejected": ["QA Lead"],
	"Merged": ["QA Lead"],
}

# (from, action, to, roles, condition)
TRANSITIONS = [
	("New", "Triage", "Triaged", ["L1 Support", "QA Lead"], None),
	("New", "Reject", "Rejected", ["L1 Support", "QA Lead"], None),
	("Triaged", "Assign to Developer", "Assigned", ["L1 Support", "QA Lead"], "doc.assigned_to"),
	("Triaged", "Defer", "Deferred", ["L1 Support", "QA Lead"], None),
	("Triaged", "Reject", "Rejected", ["L1 Support", "QA Lead"], None),
	("Assigned", "Start Work", "In Progress", ["L2 Support", "L3 Support", "Vendor Developer", "QA Lead"], None),
	("Assigned", "Mark Fixed", "Ready for Retest", ["L2 Support", "L3 Support", "Vendor Developer", "QA Lead"], "doc.resolution"),
	("Assigned", "Answer Query", "Answered", ["L1 Support", "L2 Support", "L3 Support", "Vendor Developer", "QA Lead"], "doc.resolution"),
	("Assigned", "Defer", "Deferred", ["L1 Support", "QA Lead"], None),
	("In Progress", "Mark Fixed", "Ready for Retest", ["L2 Support", "L3 Support", "Vendor Developer", "QA Lead"], "doc.resolution"),
	("In Progress", "Answer Query", "Answered", ["L1 Support", "L2 Support", "L3 Support", "Vendor Developer", "QA Lead"], "doc.resolution"),
	("Reopened", "Start Work", "In Progress", ["L2 Support", "L3 Support", "Vendor Developer", "QA Lead"], None),
	("Reopened", "Mark Fixed", "Ready for Retest", ["L2 Support", "L3 Support", "Vendor Developer", "QA Lead"], "doc.resolution"),
	("Ready for Retest", "Retest Passed", "Retest Passed", ["QA Tester", "QA Lead"], "doc.retest_result == 'Pass'"),
	("Ready for Retest", "Retest Failed", "Reopened", ["QA Tester", "QA Lead"], "doc.retest_result == 'Fail'"),
	("Retest Passed", "Confirm", "Confirmed", ["QA Lead"], None),
	("Retest Passed", "Retest Failed", "Reopened", ["QA Lead"], None),
	("Confirmed", "Send to UAT", "In UAT", ["QA Lead"], None),
	("Confirmed", "Close without UAT", "Closed", ["QA Lead"], None),
	("In UAT", "UAT Accept", "UAT Accepted", ["UAT User", "QA Lead"], "doc.uat_result == 'Accepted'"),
	("In UAT", "UAT Reject", "Reopened", ["UAT User", "QA Lead"], "doc.uat_result == 'Rejected'"),
	("Answered", "Accept Answer", "Closed", ["QA Tester", "QA Lead"], None),
	("Answered", "Not Resolved", "Reopened", ["QA Tester", "QA Lead"], None),
	("Deferred", "Reactivate", "Triaged", ["QA Lead"], None),
	("Closed", "Reopen", "Reopened", ["QA Lead"], None),
	("UAT Accepted", "Reopen", "Reopened", ["QA Lead"], None),
	("Rejected", "Reopen", "Reopened", ["QA Lead"], None),
]

OPEN_STATES = ["New", "Triaged", "Assigned", "In Progress", "Reopened", "Ready for Retest", "Retest Passed", "Confirmed", "In UAT", "Answered"]


def before_install():
	create_roles()
	from qa_tracker.gap_analysis.setup import create_roles as gap_roles

	gap_roles()


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	create_roles()
	create_masters()
	create_workflow()
	create_dashboard()
	create_workspace()
	create_persona_workspaces()
	from qa_tracker.gap_analysis import setup as gap_setup

	gap_setup.setup()
	setup_projects()
	frappe.db.commit()


def _rebuild_tree(doctype, parent_field):
	from frappe.utils import nestedset

	try:
		nestedset.rebuild_tree(doctype, parent_field)
	except TypeError:  # Frappe 16: rebuild_tree(doctype)
		nestedset.rebuild_tree(doctype)


def _rebuild_site_tree():
	_rebuild_tree("QA Site", "parent_qa_site")


def setup_projects():
	"""Multi-project upgrade (v2): build the site tree and move existing data into a default project."""
	frappe.db.sql("update `tabQA Issue` set support_level='L1' where ifnull(support_level, '')=''")
	if frappe.db.sql("select count(*) from `tabQA Site` where ifnull(rgt, 0) = 0")[0][0]:
		_rebuild_site_tree()
	if frappe.db.sql("select count(*) from `tabQA Project` where ifnull(rgt, 0) = 0")[0][0]:
		_rebuild_tree("QA Project", "parent_qa_project")
	has_data = any(frappe.db.count(dt) for dt in ("QA Issue", "QA Test Cycle", "Gap Item", "Gap Assessment"))
	if not frappe.db.count("QA Project"):
		title = (frappe.db.get_single_value("QA Settings", "portal_title") or "").strip()
		name = "Main Project" if not title or title == "QA Tracker" else title
		p = frappe.get_doc({"doctype": "QA Project", "project_name": name, "project_code": "MAIN", "status": "Active",
			"description": "Created automatically when upgrading to multi-project. Rename it, add vendors and the team."})
		# everyone who already has a QA role keeps seeing everything (as client staff, no vendor)
		reverse = {v: k for k, v in __import__("qa_tracker.access", fromlist=["ROLE_MAP"]).ROLE_MAP.items()}
		order = ["QA Lead", "QA Tester", "Vendor Developer", "UAT User", "GA Analyst", "GA Approver", "QA Viewer"]
		rows = frappe.get_all("Has Role", filters={"role": ["in", order], "parenttype": "User"}, fields=["parent", "role"])
		best = {}
		for r in rows:
			if r.parent in ("Administrator", "Guest"):
				continue
			if r.parent not in best or order.index(r.role) < order.index(best[r.parent]):
				best[r.parent] = r.role
		for user, role in sorted(best.items()):
			if frappe.db.get_value("User", user, "enabled"):
				p.append("members", {"user": user, "project_role": reverse[role], "is_active": 1})
		p.flags.ignore_permissions = True
		p.flags.ignore_mandatory = True
		p.insert()
		if not frappe.db.get_single_value("QA Settings", "default_project"):
			frappe.db.set_single_value("QA Settings", "default_project", p.name)
	if has_data:
		default = frappe.db.get_single_value("QA Settings", "default_project") or frappe.get_all("QA Project", pluck="name", limit=1)[0]
		for dt in ("QA Issue", "QA Test Cycle", "Gap Assessment", "QA Import Batch"):
			frappe.db.sql(f"update `tab{dt}` set project=%s where ifnull(project, '')=''", default)
		frappe.db.sql("""update `tabQA Test Execution` e join `tabQA Test Cycle` c on c.name=e.test_cycle
			set e.project=c.project where ifnull(e.project, '')=''""")
		frappe.db.sql("""update `tabGap Item` g left join `tabGap Assessment` a on a.name=g.assessment
			set g.project=ifnull(a.project, %s), g.vendor=ifnull(g.vendor, a.vendor) where ifnull(g.project, '')=''""", default)


def create_roles():
	for role, desc in ROLES.items():
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1, "description": desc}).insert(
				ignore_permissions=True
			)


def create_masters():
	if not frappe.db.count("QA Site"):
		for name, code in DEFAULT_SITES:
			frappe.get_doc({"doctype": "QA Site", "site_name": name, "site_code": code}).insert(ignore_permissions=True)
	if not frappe.db.count("QA Module"):
		for name, code, kw in DEFAULT_MODULES:
			frappe.get_doc(
				{"doctype": "QA Module", "module_name": name, "module_code": code, "keywords": kw}
			).insert(ignore_permissions=True)
	# fill defaults for settings fields added in newer versions (Frappe doesn't back-fill singles)
	present = set(frappe.db.sql_list("select field from `tabSingles` where doctype='QA Settings'"))
	for df in frappe.get_meta("QA Settings").fields:
		if df.default and df.fieldname not in present and df.fieldtype not in ("Password", "Section Break", "Column Break"):
			frappe.db.set_single_value("QA Settings", df.fieldname, df.default)
	frappe.clear_document_cache("QA Settings", "QA Settings") if hasattr(frappe, "clear_document_cache") else None
	settings = frappe.get_single("QA Settings")
	changed = False
	if not settings.default_module and frappe.db.exists("QA Module", "General"):
		settings.default_module = "General"
		changed = True
	if not settings.group_window_minutes:
		settings.group_window_minutes = 10
		changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.save()


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

	name = "QA Issue Workflow"
	wf = frappe.get_doc("Workflow", name) if frappe.db.exists("Workflow", name) else frappe.new_doc("Workflow")
	wf.workflow_name = name
	wf.document_type = "QA Issue"
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
			wf.append(
				"transitions",
				{
					"state": frm,
					"action": action,
					"next_state": to,
					"allowed": role,
					"allow_self_approval": 1,
					"condition": cond or "",
				},
			)
	wf.flags.ignore_permissions = True
	wf.save()


def _upsert(doctype, name, values):
	if frappe.db.exists(doctype, name):
		doc = frappe.get_doc(doctype, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(dict(doctype=doctype, **values))
		doc.insert(ignore_permissions=True)
	return doc


def create_dashboard():
	open_filter = json.dumps([["QA Issue", "status", "in", OPEN_STATES, False]])
	# Number Cards are named after their label, so the label is the key
	cards = [
		("Open Issues", "Open Issues", open_filter, "#2490EF"),
		(
			"Open Blockers",
			"Open Blockers",
			json.dumps([["QA Issue", "status", "in", OPEN_STATES, False], ["QA Issue", "severity", "=", "Blocker", False]]),
			"#E24C4C",
		),
		("Ready for Retest", "Ready for Retest", json.dumps([["QA Issue", "status", "=", "Ready for Retest", False]]), "#ECAD4B"),
		("In UAT", "In UAT", json.dumps([["QA Issue", "status", "=", "In UAT", False]]), "#7575FF"),
		(
			"UAT Accepted / Closed",
			"UAT Accepted / Closed",
			json.dumps([["QA Issue", "status", "in", ["UAT Accepted", "Closed"], False]]),
			"#29CD42",
		),
	]
	# remove duplicates created by earlier versions
	for dup in frappe.get_all("Number Card", filters={"module": "QA Tracker", "name": ["like", "%-_"]}, pluck="name"):
		frappe.delete_doc("Number Card", dup, ignore_permissions=True, force=True)
	for name, label, filters, color in cards:
		_upsert(
			"Number Card",
			name,
			{
				"name": name,
				"label": label,
				"type": "Document Type",
				"document_type": "QA Issue",
				"function": "Count",
				"filters_json": filters,
				"is_public": 1,
				"show_percentage_stats": 0,
				"color": color,
				"module": "QA Tracker",
			},
		)

	charts = [
		("QA Issues by Status", "status", "[]", "Bar"),
		("QA Open Issues by Module", "module", open_filter, "Bar"),
		("QA Open Issues by Site", "site", open_filter, "Donut"),
		("QA Open Issues by Developer", "assigned_to", open_filter, "Bar"),
		("QA Issues by Reporter", "reported_by", "[]", "Bar"),
		("QA Open Issues by Vendor", "vendor", open_filter, "Bar"),
		("QA Open Issues by Project", "project", open_filter, "Donut"),
	]
	for name, field, filters, ctype in charts:
		_upsert(
			"Dashboard Chart",
			name,
			{
				"chart_name": name,
				"chart_type": "Group By",
				"document_type": "QA Issue",
				"group_by_type": "Count",
				"group_by_based_on": field,
				"number_of_groups": 0,
				"filters_json": filters,
				"type": ctype,
				"is_public": 1,
				"timeseries": 0,
				"module": "QA Tracker",
			},
		)
	_upsert(
		"Dashboard Chart",
		"QA Issues Reported per Week",
		{
			"chart_name": "QA Issues Reported per Week",
			"chart_type": "Count",
			"document_type": "QA Issue",
			"based_on": "creation",
			"timeseries": 1,
			"timespan": "Last Quarter",
			"time_interval": "Weekly",
			"filters_json": "[]",
			"type": "Line",
			"is_public": 1,
			"module": "QA Tracker",
		},
	)


def create_workspace():
	name = "QA Tracker"
	cards = ["Open Issues", "Open Blockers", "Ready for Retest", "In UAT", "UAT Accepted / Closed"]
	charts = [
		"QA Issues by Status",
		"QA Open Issues by Vendor",
		"QA Open Issues by Project",
		"QA Open Issues by Module",
		"QA Open Issues by Developer",
		"QA Open Issues by Site",
		"QA Issues Reported per Week",
		"QA Issues by Reporter",
	]
	shortcuts = [
		("Tester Portal", "URL", None, "/qa", "Green"),
		("New Issue", "DocType", "QA Issue", "/app/qa-issue/new", "Blue"),
		("All Issues", "DocType", "QA Issue", None, "Grey"),
		("Issue Board", "URL", None, "/app/qa-issue/view/kanban/QA Issues", "Purple"),
		("Test Runs", "DocType", "QA Test Execution", None, "Orange"),
		("Test Cases", "DocType", "QA Test Case", None, "Grey"),
		("Issue Summary", "Report", "QA Issue Summary", None, "Green"),
		("Projects", "URL", None, "/app/qa-project/view/tree", "Blue"),
		("Vendors", "DocType", "QA Vendor", None, "Orange"),
		("Site Tree", "URL", None, "/app/qa-site/view/tree", "Grey"),
	]
	content = [{"id": "hdr1", "type": "header", "data": {"text": "<span class=\"h4\"><b>QA Tracker</b></span>", "col": 12}}]
	for i, c in enumerate(cards):
		content.append({"id": f"nc{i}", "type": "number_card", "data": {"number_card_name": c, "col": 4 if i < 3 else 6}})
	for i, s in enumerate(shortcuts):
		content.append({"id": f"sc{i}", "type": "shortcut", "data": {"shortcut_name": s[0], "col": 4}})
	for i, c in enumerate(charts):
		content.append({"id": f"ch{i}", "type": "chart", "data": {"chart_name": c, "col": 6}})
	content.append({"id": "hdr2", "type": "header", "data": {"text": "<span class=\"h4\"><b>Setup</b></span>", "col": 12}})
	for i, card in enumerate(["Masters", "Integrations"]):
		content.append({"id": f"cd{i}", "type": "card", "data": {"card_name": card, "col": 6}})

	ws = frappe.get_doc("Workspace", name) if frappe.db.exists("Workspace", name) else frappe.new_doc("Workspace")
	ws.update(
		{
			"name": name,
			"label": name,
			"title": name,
			"module": "QA Tracker",
			"public": 1,
			"icon": "tool",
			"sequence_id": 50,
			"content": json.dumps(content),
		}
	)
	ws.set("number_cards", [{"number_card_name": c, "label": c} for c in cards])
	for row in ws.number_cards:
		if not frappe.db.exists("Number Card", row.number_card_name):
			frappe.throw(f"Number Card {row.number_card_name} missing")
	ws.set("charts", [{"chart_name": c, "label": c} for c in charts])
	ws.set("shortcuts", [])
	for label, typ, link_to, url, color in shortcuts:
		row = {"label": label, "type": typ, "color": color}
		if typ == "URL":
			row["url"] = url
		else:
			row["link_to"] = link_to
		if label == "New Issue":
			row["type"] = "URL"
			row["url"] = url
			row.pop("link_to", None)
		ws.append("shortcuts", row)
	ws.set("links", [])
	groups = {
		"Masters": [
			("Sites", "QA Site"),
			("Modules", "QA Module"),
			("Test Cycles", "QA Test Cycle"),
			("Test Cases", "QA Test Case"),
		],
		"Integrations": [
			("QA Settings", "QA Settings"),
			("Email Accounts", "Email Account"),
			("Incoming Message Log", "QA Channel Message"),
			("Import Word / Excel", "QA Import Batch"),
		],
	}
	for card, links in groups.items():
		ws.append("links", {"type": "Card Break", "label": card, "link_count": len(links)})
		for label, dt in links:
			ws.append("links", {"type": "Link", "label": label, "link_type": "DocType", "link_to": dt})
	ws.flags.ignore_permissions = True
	ws.flags.ignore_links = True
	ws.save() if not ws.is_new() else ws.insert()

	create_kanban()


def create_kanban():
	name = "QA Issues"
	if frappe.db.exists("Kanban Board", name):
		return
	board = frappe.get_doc(
		{
			"doctype": "Kanban Board",
			"kanban_board_name": name,
			"reference_doctype": "QA Issue",
			"field_name": "status",
			"private": 0,
			"show_labels": 0,
			"fields": json.dumps(["severity", "module", "assigned_to"]),
		}
	)
	for state in STATE_STYLE:
		board.append("columns", {"column_name": state, "status": "Active", "indicator": "Gray"})
	board.insert(ignore_permissions=True)


# ---------------------------------------------------------------- persona workspaces (v2.3)
DEV_STATES = ["Assigned", "In Progress", "Reopened"]
ME = "frappe.session.user"
TODAY = "frappe.datetime.get_today()"


def _card(name, filters, color, dynamic=None):
	_upsert("Number Card", name, {
		"name": name, "label": name, "type": "Document Type", "document_type": "QA Issue", "function": "Count",
		"filters_json": json.dumps(filters), "dynamic_filters_json": json.dumps(dynamic) if dynamic else None,
		"is_public": 1, "show_percentage_stats": 0, "color": color, "module": "QA Tracker",
	})


def _persona_cards():
	op = ["QA Issue", "status", "in", OPEN_STATES, False]
	# a "<" date filter also matches empty dates, so require a target date (kept in the dynamic list: a static filter
	# on the same field would be dropped by Frappe when a dynamic one exists)
	late = [["QA Issue", "target_date", "is", "'set'"], ["QA Issue", "target_date", "<", TODAY]]
	_card("Overdue Issues", [op], "#ECAD4B", late)
	_card("Escalated to L2", [op, ["QA Issue", "support_level", "=", "L2", False]], "#7575FF")
	_card("Escalated to L3", [op, ["QA Issue", "support_level", "=", "L3", False]], "#E24C4C")
	_card("L1 Triage Queue", [["QA Issue", "status", "in", ["New", "Triaged"], False], ["QA Issue", "support_level", "=", "L1", False]], "#2490EF")
	_card("Closed This Week", [["QA Issue", "closed_on", "Timespan", "this week", False]], "#29CD42")
	_card("My Open Tickets", [op], "#2490EF", [["QA Issue", "reported_by", "=", ME]])
	_card("Waiting for My Retest", [["QA Issue", "status", "=", "Ready for Retest", False]], "#ECAD4B", [["QA Issue", "reported_by", "=", ME]])
	_card("Assigned to Me", [["QA Issue", "status", "in", DEV_STATES, False]], "#2490EF", [["QA Issue", "assigned_to", "=", ME]])
	_card("My Reopened Tickets", [["QA Issue", "status", "=", "Reopened", False]], "#E24C4C", [["QA Issue", "assigned_to", "=", ME]])
	_card("My Overdue Tickets", [["QA Issue", "status", "in", DEV_STATES, False]], "#ECAD4B",
		[["QA Issue", "assigned_to", "=", ME]] + late)
	open_filter = json.dumps([op])
	for name, field, ctype in (("QA Open Issues by Support Level", "support_level", "Bar"), ("QA Open Issues by Severity", "severity", "Donut")):
		_upsert("Dashboard Chart", name, {"chart_name": name, "chart_type": "Group By", "document_type": "QA Issue", "group_by_type": "Count",
			"group_by_based_on": field, "number_of_groups": 0, "filters_json": open_filter, "type": ctype, "is_public": 1, "timeseries": 0,
			"module": "QA Tracker"})
	_upsert("Dashboard Chart", "QA Issues Closed per Week", {"chart_name": "QA Issues Closed per Week", "chart_type": "Count",
		"document_type": "QA Issue", "based_on": "closed_on", "timeseries": 1, "timespan": "Last Quarter", "time_interval": "Weekly",
		"filters_json": json.dumps([["QA Issue", "closed_on", "is", "set", False]]), "type": "Line", "is_public": 1, "module": "QA Tracker"})


PERSONA_WORKSPACES = [
	{
		"name": "QA Management", "icon": "dashboard", "seq": 45, "roles": ["QA Management", "QA Lead", "System Manager"],
		"intro": "Project control: open the Management Dashboard for drill-down by project, sub-project, vendor, site and support level.",
		"cards": ["Open Issues", "Open Blockers", "Overdue Issues", "Escalated to L2", "Escalated to L3", "Closed This Week"],
		"shortcuts": [("Management Dashboard", "URL", None, "/qa#/dash", "Green"), ("Project Tree", "URL", None, "/app/qa-project/view/tree", "Blue"),
			("Vendors", "DocType", "QA Vendor", None, "Orange"), ("Issue Summary", "Report", "QA Issue Summary", None, "Grey"),
			("Gap Tracker", "URL", None, "/qa#/gaps", "Purple"), ("All Issues", "DocType", "QA Issue", None, "Grey")],
		"charts": ["QA Open Issues by Project", "QA Open Issues by Vendor", "QA Open Issues by Support Level", "QA Open Issues by Severity",
			"QA Issues Reported per Week", "QA Issues Closed per Week", "QA Open Issues by Site", "QA Open Issues by Module"],
	},
	{
		"name": "QA Reporting", "icon": "edit", "seq": 46, "roles": ["QA Tester", "UAT User"],
		"intro": "Report problems and follow your tickets. The portal works on a phone too.",
		"cards": ["My Open Tickets", "Waiting for My Retest", "In UAT"],
		"shortcuts": [("Report an Issue", "URL", None, "/qa#/new", "Green"), ("My Tickets", "URL", None, "/qa#/tickets", "Blue"),
			("My Test Runs", "URL", None, "/qa#/runs", "Orange"), ("Gap Tracker", "URL", None, "/qa#/gaps", "Purple")],
		"charts": [],
	},
	{
		"name": "QA L1 Support", "icon": "support", "seq": 47, "roles": ["L1 Support", "QA Lead"],
		"intro": "First response: triage new tickets, answer how-to questions, escalate real defects to L2.",
		"cards": ["L1 Triage Queue", "Open Blockers", "Escalated to L2", "Overdue Issues"],
		"shortcuts": [("Triage Queue", "URL", None, "/app/qa-issue?support_level=L1&status=New", "Blue"),
			("Portal: Needs You", "URL", None, "/qa#/tickets", "Green"), ("Issue Board", "URL", None, "/app/qa-issue/view/kanban/QA Issues", "Purple"),
			("Dashboard", "URL", None, "/qa#/dash", "Orange"), ("New Issue", "URL", None, "/app/qa-issue/new", "Grey")],
		"charts": ["QA Open Issues by Module", "QA Open Issues by Site", "QA Issues Reported per Week", "QA Open Issues by Severity"],
	},
	{
		"name": "QA Developer", "icon": "tool", "seq": 48, "roles": ["Vendor Developer"],
		"intro": "Your assigned tickets. Mark them fixed with a note so testers can retest.",
		"cards": ["Assigned to Me", "My Reopened Tickets", "My Overdue Tickets"],
		"shortcuts": [("My Work (Portal)", "URL", None, "/qa#/tickets", "Green"), ("Issue Board", "URL", None, "/app/qa-issue/view/kanban/QA Issues", "Purple"),
			("Open Issues", "URL", None, "/app/qa-issue?status=Assigned", "Blue")],
		"charts": ["QA Open Issues by Severity", "QA Open Issues by Module"],
	},
	{
		"name": "QA L2 L3 Support", "icon": "setting-gear", "seq": 49, "roles": ["L2 Support", "L3 Support"],
		"intro": "Escalated tickets: L2 application support fixes configuration, L3 vendor engineering fixes code.",
		"cards": ["Escalated to L2", "Escalated to L3", "Assigned to Me", "Overdue Issues"],
		"shortcuts": [("L2 Queue", "URL", None, "/app/qa-issue?support_level=L2", "Purple"), ("L3 Queue", "URL", None, "/app/qa-issue?support_level=L3", "Red"),
			("Portal: Needs You", "URL", None, "/qa#/tickets", "Green"), ("Dashboard", "URL", None, "/qa#/dash", "Orange")],
		"charts": ["QA Open Issues by Support Level", "QA Open Issues by Vendor", "QA Open Issues by Module"],
	},
]


def create_persona_workspaces():
	_persona_cards()
	for w in PERSONA_WORKSPACES:
		content = [{"id": "hdr", "type": "header", "data": {"text": f"<span class=\"h4\"><b>{w['name']}</b></span>", "col": 12}},
			{"id": "intro", "type": "paragraph", "data": {"text": w["intro"], "col": 12}}]
		for i, c in enumerate(w["cards"]):
			content.append({"id": f"nc{i}", "type": "number_card", "data": {"number_card_name": c, "col": 3 if len(w["cards"]) == 4 else 4}})
		content.append({"id": "hdr2", "type": "header", "data": {"text": "<span class=\"h5\"><b>Go to</b></span>", "col": 12}})
		for i, sc in enumerate(w["shortcuts"]):
			content.append({"id": f"sc{i}", "type": "shortcut", "data": {"shortcut_name": sc[0], "col": 4}})
		for i, c in enumerate(w["charts"]):
			content.append({"id": f"ch{i}", "type": "chart", "data": {"chart_name": c, "col": 6}})
		ws = frappe.get_doc("Workspace", w["name"]) if frappe.db.exists("Workspace", w["name"]) else frappe.new_doc("Workspace")
		ws.update({"name": w["name"], "label": w["name"], "title": w["name"], "module": "QA Tracker", "public": 1, "icon": w["icon"],
			"sequence_id": w["seq"], "content": json.dumps(content)})
		ws.set("number_cards", [{"number_card_name": c, "label": c} for c in w["cards"]])
		ws.set("charts", [{"chart_name": c, "label": c} for c in w["charts"]])
		ws.set("shortcuts", [])
		for label, typ, link_to, url, color in w["shortcuts"]:
			row = {"label": label, "type": typ, "color": color}
			if typ == "URL":
				row["url"] = url
			else:
				row["link_to"] = link_to
			ws.append("shortcuts", row)
		ws.set("roles", [{"role": r} for r in w["roles"] if frappe.db.exists("Role", r)])
		ws.flags.ignore_permissions = True
		ws.flags.ignore_links = True
		ws.save() if not ws.is_new() else ws.insert()
	# the original all-in-one workspace stays for leads and admins
	if frappe.db.exists("Workspace", "QA Tracker"):
		ws = frappe.get_doc("Workspace", "QA Tracker")
		ws.set("roles", [{"role": r} for r in ("QA Lead", "System Manager", "QA Viewer")])
		ws.flags.ignore_permissions = True
		ws.flags.ignore_links = True
		ws.save()
