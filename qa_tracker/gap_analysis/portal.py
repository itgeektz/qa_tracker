"""Portal API for gap analysis: fast workshop capture and follow-up (used by /qa#/gaps)."""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate, pretty_date

from qa_tracker.gap_analysis.api import ACTIONS
from qa_tracker.gap_analysis.api import record as _record

GAP_ROLES = {"GA Analyst", "GA Approver", "QA Lead", "System Manager", "Vendor Developer", "QA Tester", "UAT User", "QA Viewer"}
STAGES = [
	("Identified", ["Identified"]),
	("Analysed", ["Analysed"]),
	("Approval", ["Awaiting Approval"]),
	("Delivery", ["Approved", "In Progress"]),
	("Verify", ["Delivered", "Verified"]),
	("Closed", ["Closed"]),
]
DONE = ["Closed", "Rejected", "Deferred", "Merged"]
FIT = ("Gap", "Partial Fit", "Fit", "Not Applicable")
PRIORITY = ("Must Have", "Should Have", "Could Have", "Won't Have")
APPROACHES = ["Configuration", "Customization / Development", "Workaround", "Process Change", "Third-party / Integration",
	"Training", "Future Release", "Not Required"]
EDITABLE = {"title", "fit_status", "priority", "business_impact", "gap_type", "process_name", "department", "requirement",
	"current_process", "system_behaviour", "risk_if_not_addressed", "regulatory", "resolution_approach", "proposed_solution",
	"workaround", "responsible_party", "assigned_to", "business_owner", "effort_days", "estimated_cost", "target_release",
	"target_date", "source", "reference"}

# workflow action -> portal button
ACTION_UI = {
	"Analyse": {"kind": "analyse", "label": "Mark analysed", "style": "secondary"},
	"Close as Fit": {"kind": "close_fit", "label": "Close as fit", "style": "success"},
	"Submit for Approval": {"kind": "submit", "label": "Send for approval", "style": "primary"},
	"Approve": {"kind": "approve", "label": "Approve", "style": "success", "notes": "Notes (optional)"},
	"Reject": {"kind": "reject", "label": "Reject", "style": "danger", "notes": "Why?", "notes_required": 1},
	"Defer": {"kind": "defer", "label": "Defer", "style": "secondary", "notes": "Defer until / reason", "notes_required": 1},
	"Send Back": {"kind": "send_back", "label": "Send back", "style": "secondary", "notes": "What needs more analysis?", "notes_required": 1},
	"Start Work": {"kind": "start", "label": "Start work", "style": "secondary"},
	"Mark Delivered": {"kind": "deliver", "label": "Mark delivered", "style": "primary", "notes": "What was delivered?", "notes_required": 1, "build": 1, "shots": 1},
	"Verify": {"kind": "verify_pass", "label": "Works", "style": "success", "notes": "Notes (optional)", "shots": 1},
	"Verification Failed": {"kind": "verify_fail", "label": "Doesn't work", "style": "danger", "notes": "What is wrong?", "notes_required": 1, "shots": 1},
	"Close": {"kind": "close", "label": "Close", "style": "success"},
	"Reopen": {"kind": "reopen", "label": "Reopen", "style": "danger"},
}


def _require():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in"), frappe.PermissionError)
	if not (set(frappe.get_roles()) & GAP_ROLES) and frappe.session.user != "Administrator":
		frappe.throw(_("You don't have access to gap analysis."), frappe.PermissionError)


def _roles():
	r = set(frappe.get_roles())
	if frappe.session.user == "Administrator":
		r |= {"QA Lead"}
	return r


def can_capture(roles=None):
	roles = roles or _roles()
	return bool(roles & {"GA Analyst", "QA Lead", "System Manager", "QA Tester", "UAT User"})


def stage_index(status):
	for i, (_l, states) in enumerate(STAGES):
		if status in states:
			return i
	return -1


def _needs_groups(user, roles):
	g = [
		{"business_owner": user, "status": "Awaiting Approval"},
		{"assigned_to": user, "status": ["in", ["Approved", "In Progress"]]},
		{"raised_by": user, "status": "Delivered"},
	]
	if roles & {"GA Analyst", "QA Lead"}:
		g.append({"status": ["in", ["Identified", "Analysed"]]})
	if roles & {"QA Tester", "UAT User"}:
		g.append({"status": "Delivered"})
	if roles & {"GA Approver", "QA Lead"}:
		g.append({"status": "Verified"})
	return g


def _project(project=None):
	from qa_tracker import access

	if not project or project == "all":
		return None
	access.check_project(project)
	return project


def _needs(user, roles, project=None):
	names = set()
	for g in _needs_groups(user, roles):
		if project:
			g = dict(g, project=["in", _tree(project)])
		names.update(frappe.get_list("Gap Item", filters=g, pluck="name", limit=300))
	return names


def _tree(project):
	from qa_tracker import access

	return sorted(access.descendants("QA Project", project))


def _members_with(project, project_role, fallback_role):
	from qa_tracker import access

	if not project:
		return _users_with(fallback_role)
	seen, out = set(), []
	for m in access.members_for(project):
		if m.is_active and m.project_role in (project_role, "QA Lead") and m.user not in seen:
			seen.add(m.user)
			out.append({"value": m.user, "label": m.full_name or m.user})
	return out


def _users_with(role):
	return [{"value": d, "label": frappe.utils.get_fullname(d)} for d in frappe.get_all(
		"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent", distinct=True)
		if frappe.db.get_value("User", d, "enabled") and d not in ("Administrator", "Guest")]


def _assessment_row(a):
	return {
		"name": a.name, "site": a.site, "module": a.module, "status": a.status, "date": str(a.workshop_date or ""),
		"project": a.get("project"), "vendor": a.get("vendor"),
		"total": a.total_items or 0, "fit": a.fit_count or 0, "partial": a.partial_count or 0, "gap": a.gap_count or 0,
		"fit_pct": a.fit_percent or 0, "must": a.open_must_haves or 0, "approver": a.approver,
	}


@frappe.whitelist()
def boot(project=None):
	_require()
	from qa_tracker import access
	from qa_tracker.utils import max_upload_bytes

	user, roles = frappe.session.user, _roles()
	project = _project(project)
	ass = frappe.get_list("Gap Assessment", filters={"project": ["in", _tree(project)]} if project else {},
		fields=["name", "site", "module", "status", "workshop_date", "total_items", "fit_count",
		"partial_count", "gap_count", "fit_percent", "open_must_haves", "approver", "project", "vendor"], order_by="modified desc", limit=50)
	return {
		"can_capture": can_capture(roles),
		"is_analyst": bool(roles & {"GA Analyst", "QA Lead"}),
		"is_approver": bool(roles & {"GA Approver", "QA Lead"}),
		"needs_you": len(_needs(user, roles, project)),
		"assessments": [_assessment_row(a) for a in ass],
		"approvers": _members_with(project, "Gap Approver", "GA Approver"),
		"developers": [{"value": d.name, "label": d.full_name or d.name} for d in access.developers(project)] if project
			else _users_with("Vendor Developer"),
		"vendors": [v.vendor for v in access.project_vendors(project)] if project else [],
		"fit": FIT, "priority": PRIORITY, "approaches": APPROACHES, "max_upload": max_upload_bytes(),
		"gap_types": frappe.get_meta("Gap Item").get_field("gap_type").options.split("\n"),
	}


def _row(d, needs=None):
	return {
		"name": d.name, "code": d.gap_code, "title": d.title, "status": d.status, "stage": stage_index(d.status),
		"fit": d.fit_status, "priority": d.priority, "module": d.module, "approach": d.resolution_approach,
		"assessment": d.assessment, "regulatory": d.regulatory, "ago": pretty_date(d.modified),
		"needs_you": bool(needs and d.name in needs), "effort": d.effort_days, "vendor": d.get("vendor"),
	}


ROW_FIELDS = ["name", "gap_code", "title", "status", "fit_status", "priority", "module", "resolution_approach", "assessment",
	"regulatory", "modified", "effort_days", "vendor", "project"]


@frappe.whitelist()
def gaps(scope="needs_you", assessment=None, search=None, start=0, project=None):
	_require()
	user, roles = frappe.session.user, _roles()
	project = _project(project)
	needs = _needs(user, roles, project)
	filters = {"project": ["in", _tree(project)]} if project else {}
	if assessment:
		filters["assessment"] = assessment
	if scope == "needs_you":
		if not needs:
			return []
		filters["name"] = ["in", list(needs)]
	elif scope == "done":
		filters["status"] = ["in", DONE]
	elif scope == "open":
		filters["status"] = ["not in", DONE]
	if search:
		s = search.strip()
		if re.match(r"^(GAP-)?\d+$", s, re.I):
			filters["name"] = f"GAP-{int(s.upper().replace('GAP-', '')):05d}"
		else:
			filters["title"] = ["like", f"%{s}%"]
	rows = frappe.get_list("Gap Item", filters=filters, fields=ROW_FIELDS, order_by="modified desc", start=cint(start), limit=50)
	return [_row(r, needs) for r in rows]


def _actions(doc, roles):
	from frappe.model.workflow import get_transitions

	out, seen = [], set()
	extra = []
	if doc.status == "Delivered" and roles & {"QA Tester", "UAT User", "GA Analyst", "QA Lead"}:
		extra = ["Verify", "Verification Failed"]
	elif doc.status in ("Approved", "In Progress") and roles & {"Vendor Developer", "GA Analyst", "QA Lead"}:
		extra = ["Mark Delivered"]
	elif doc.status == "Analysed" and roles & {"GA Analyst", "QA Lead"} and doc.fit_status in ("Gap", "Partial Fit"):
		extra = ["Submit for Approval"]
	try:
		transitions = [t.action for t in get_transitions(doc)]
	except Exception:
		transitions = []
	for a in extra + transitions:
		if a in seen or a not in ACTION_UI:
			continue
		seen.add(a)
		out.append(dict(ACTION_UI[a], action=a))
	return out


@frappe.whitelist()
def gap(name):
	_require()
	doc = frappe.get_doc("Gap Item", name)
	doc.check_permission("read")
	roles = _roles()
	user = frappe.session.user
	can_edit = bool(doc.has_permission("write")) and doc.status not in ("Closed",) and bool(
		roles & {"GA Analyst", "QA Lead", "System Manager"} or (doc.raised_by == user and doc.status == "Identified"))
	return {
		"name": doc.name, "code": doc.gap_code, "title": doc.title, "status": doc.status, "stage": stage_index(doc.status),
		"assessment": doc.assessment, "site": doc.site, "module": doc.module,
		"values": {f: doc.get(f) for f in EDITABLE},
		"decision": doc.decision, "decision_notes": doc.decision_notes,
		"delivery_notes": doc.delivery_notes, "delivered_in_build": doc.delivered_in_build,
		"verification_notes": doc.verification_notes,
		"owner_name": frappe.utils.get_fullname(doc.business_owner) if doc.business_owner else None,
		"assignee_name": frappe.utils.get_fullname(doc.assigned_to) if doc.assigned_to else None,
		"raised": frappe.utils.get_fullname(doc.raised_by) if doc.raised_by else None,
		"evidence": [e.file for e in doc.evidence if e.file],
		"verification_evidence": [e.file for e in doc.verification_evidence if e.file],
		"issues": [{"name": r.issue, "title": r.issue_title, "status": r.issue_status} for r in doc.linked_issues],
		"tests": [{"name": r.test_case, "title": r.test_title} for r in doc.linked_test_cases],
		"timeline": [{"type": u.update_type, "text": u.message, "file": u.attachment, "ago": pretty_date(u.posted_on) if u.posted_on else "",
			"by": frappe.utils.get_fullname(u.posted_by) if u.posted_by else "", "mine": u.posted_by == user} for u in doc.updates],
		"actions": _actions(doc, roles),
		"can_edit": can_edit,
		"desk_url": f"/app/gap-item/{doc.name}",
		"merged_into": doc.get("merged_into"),
		"merged_from": frappe.get_all("Gap Item", filters={"merged_into": doc.name}, fields=["name", "title"]),
		"can_merge": _can_merge(doc),
		"similar": _similar_hint(doc),
	}


def _save_images(doc_name, images, table=None):
	from qa_tracker.portal import _decode_images

	urls = []
	for fname, content in _decode_images(images):
		f = frappe.get_doc({"doctype": "File", "file_name": fname, "content": content, "attached_to_doctype": "Gap Item",
			"attached_to_name": doc_name, "is_private": 1})
		f.flags.ignore_permissions = True
		f.insert()
		urls.append(f.file_url)
	return urls


def _clean_values(values):
	values = frappe.parse_json(values) if values else {}
	out = {}
	for k, v in (values or {}).items():
		if k not in EDITABLE:
			continue
		if k == "fit_status" and v not in FIT:
			continue
		if k == "priority" and v not in PRIORITY:
			continue
		if k in ("effort_days", "estimated_cost"):
			v = flt(v) if v not in (None, "") else None
		if k == "regulatory":
			v = cint(v)
		out[k] = v
	return out


TAG_FIT = {"fit": "Fit", "partial": "Partial Fit", "gap": "Gap", "na": "Not Applicable", "n/a": "Not Applicable"}
TAG_PRIO = {"must": "Must Have", "should": "Should Have", "could": "Could Have", "wont": "Won't Have", "won't": "Won't Have"}


def parse_line(line):
	"""'Controlled drugs register [Gap] #must #reg' -> (title, values)."""
	vals = {}

	def repl(m):
		tag = (m.group(1) or m.group(2) or "").strip().lower()
		if tag in TAG_FIT:
			vals["fit_status"] = TAG_FIT[tag]
		elif tag in TAG_PRIO:
			vals["priority"] = TAG_PRIO[tag]
		elif tag in ("reg", "regulatory", "sha", "moh", "ppb", "kra"):
			vals["regulatory"] = 1
			if tag != "reg" and tag != "regulatory":
				vals.setdefault("reference", tag.upper())
		else:
			return m.group(0)
		return " "

	line = re.sub(r"^\s*(?:[-*•]|\d{1,3}[.)])\s*", "", line)
	title = re.sub(r"\[([^\]]{1,12})\]|(?<![\w/])#([\w'/]{2,12})", repl, line)
	title = re.sub(r"\s{2,}", " ", title).strip(" -–:")
	return title, vals


@frappe.whitelist()
def quick_add(assessment, title, values=None, images=None, videos=None, files=None, project=None):
	"""One requirement from the rapid capture screen."""
	_require()
	if not can_capture():
		frappe.throw(_("You can't add gaps"), frappe.PermissionError)
	title = (title or "").strip()
	parsed_title, tag_vals = parse_line(title)
	vals = dict(tag_vals)
	vals.update(_clean_values(values))
	if not parsed_title:
		frappe.throw(_("Type the requirement first"))
	project = _project(project)
	if assessment:
		frappe.get_doc("Gap Assessment", assessment).check_permission("read")
	doc = frappe.get_doc(dict(doctype="Gap Item", title=parsed_title[:240], assessment=assessment or None, source="Workshop", **vals))
	if not assessment and project:
		doc.project = project
	doc.insert()
	from qa_tracker.utils import attach_existing_file, parse_files

	urls = _save_images(doc.name, images)
	for v in parse_files(files, videos):
		urls.append(attach_existing_file(v["url"], "Gap Item", doc.name))
	for i, url in enumerate(urls, 1):
		frappe.get_doc({"doctype": "Gap Evidence", "parent": doc.name, "parenttype": "Gap Item", "parentfield": "evidence",
			"idx": i, "file": url, "added_by": frappe.session.user}).db_insert()
	return _row(frappe.get_doc("Gap Item", doc.name))


@frappe.whitelist()
def bulk_add(assessment, text, fit_status="Gap", priority="Should Have"):
	"""Paste many requirements - one per line."""
	_require()
	if not can_capture():
		frappe.throw(_("You can't add gaps"), frappe.PermissionError)
	rows = []
	for line in (text or "").splitlines():
		if not line.strip():
			continue
		title, vals = parse_line(line)
		if not title:
			continue
		vals.setdefault("fit_status", fit_status if fit_status in FIT else "Gap")
		vals.setdefault("priority", priority if priority in PRIORITY else "Should Have")
		doc = frappe.get_doc(dict(doctype="Gap Item", title=title[:240], assessment=assessment or None, source="Workshop", **vals))
		doc.insert()
		rows.append(_row(doc))
		if len(rows) >= 300:
			break
	return rows


@frappe.whitelist()
def set_fields(name, values):
	_require()
	doc = frappe.get_doc("Gap Item", name)
	doc.check_permission("write")
	vals = _clean_values(values)
	if not vals:
		return gap(name)
	doc.update(vals)
	doc.save()
	return gap(name)


@frappe.whitelist()
def remove(name):
	_require()
	doc = frappe.get_doc("Gap Item", name)
	if doc.status != "Identified":
		frappe.throw(_("Only newly captured items can be removed"))
	frappe.delete_doc("Gap Item", name)
	return "ok"


@frappe.whitelist()
def act(name, action, notes=None, build=None, images=None, videos=None, files=None):
	_require()
	from qa_tracker.utils import attach_existing_file, parse_files

	ui = ACTION_UI.get(action)
	if not ui or ui["kind"] not in ACTIONS:
		frappe.throw(_("Unknown action"))
	if ui.get("notes_required") and not (notes or "").strip():
		frappe.throw(_("Please add a note"))
	urls = _save_images(name, images) + [attach_existing_file(v["url"], "Gap Item", name) for v in parse_files(files, videos)]
	_record(name, ui["kind"], notes=notes, build=build, evidence=urls)
	return gap(name)


@frappe.whitelist()
def update(name, text=None, images=None, videos=None, files=None):
	_require()
	from qa_tracker.gap_analysis.api import add_update
	from qa_tracker.utils import attach_existing_file, parse_files

	frappe.has_permission("Gap Item", "read", doc=name, throw=True)
	urls = _save_images(name, images) + [attach_existing_file(v["url"], "Gap Item", name) for v in parse_files(files, videos)]
	text = (text or "").strip()
	if not text and not urls:
		frappe.throw(_("Write something or add a screenshot"))
	add_update(name, text or _("Screenshot added"), attachment=urls[0] if urls else None)
	for u in urls[1:]:
		add_update(name, _("Screenshot added"), attachment=u)
	return gap(name)


@frappe.whitelist()
def new_assessment(name, site=None, module=None, approver=None, workshop_date=None, scope=None, project=None, vendor=None):
	_require()
	from qa_tracker import access

	project = _project(project) or access.default_project_for(frappe.session.user)
	access.check_project(project)
	if vendor and vendor not in [v.vendor for v in access.project_vendors(project)]:
		vendor = None
	if not can_capture():
		frappe.throw(_("You can't create assessments"), frappe.PermissionError)
	name = (name or "").strip()
	if not name:
		frappe.throw(_("Give the assessment a name"))
	if frappe.db.exists("Gap Assessment", name):
		frappe.throw(_("An assessment with this name already exists"))
	doc = frappe.get_doc({"doctype": "Gap Assessment", "assessment_name": name, "site": site, "module": module,
		"approver": approver, "workshop_date": workshop_date or nowdate(), "status": "In Progress", "scope": scope,
		"project": project, "vendor": vendor,
		"facilitator": frappe.session.user if frappe.session.user != "Administrator" else None})
	doc.insert(ignore_permissions=bool(_roles() & {"QA Tester", "UAT User"}))
	return _assessment_row(frappe.get_doc("Gap Assessment", doc.name))


@frappe.whitelist()
def assessment(name):
	_require()
	a = frappe.get_doc("Gap Assessment", name)
	a.check_permission("read")
	return _assessment_row(a)


def _can_merge(doc):
	from qa_tracker.merge import can_merge

	return doc.status != "Merged" and can_merge("Gap Item", doc)


def _similar_hint(doc):
	if doc.status in DONE or not _can_merge(doc):
		return []
	from qa_tracker.merge import similar

	try:
		return [{"name": r.name, "title": r.title, "status": r.status, "score": r.score} for r in similar("Gap Item", doc.name, 3, 0.34)]
	except Exception:
		return []


@frappe.whitelist()
def merge_candidates(name, txt=None):
	from qa_tracker.merge import search, similar

	rows = search("Gap Item", txt, exclude=name) if txt else similar("Gap Item", name, 10)
	return [{"name": r.name, "title": r.title, "status": r.status, "module": r.module, "site": r.site,
		"score": r.get("score"), "project": r.project} for r in rows]


@frappe.whitelist()
def merge(target, sources):
	from qa_tracker.merge import merge_gaps

	return merge_gaps(target, sources)
