"""API for the tester portal at /qa (simple, mobile-first UI for testers, developers and UAT users)."""

import base64
import re

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, pretty_date

from qa_tracker import access
from qa_tracker.utils import add_attachment, add_screenshot, append_update, attach_existing_file, file_kind, max_upload_bytes, parse_files, party_for_user, save_file, settings

STAGES = [
	("Logged", ["New", "Triaged"]),
	("Developer", ["Assigned", "In Progress", "Reopened"]),
	("Retest", ["Ready for Retest", "Answered"]),
	("Confirmed", ["Retest Passed", "Confirmed"]),
	("UAT", ["In UAT"]),
	("Done", ["UAT Accepted", "Closed"]),
]
DONE = ["UAT Accepted", "Closed", "Rejected", "Merged"]
QA_ROLES = {"QA Tester", "QA Lead", "Vendor Developer", "UAT User", "QA Viewer", "System Manager", "GA Analyst", "GA Approver"}

# workflow action -> how the portal shows it
ACTION_UI = {
	"Mark Fixed": {"kind": "fix", "label": "Mark fixed", "style": "primary", "notes": "What did you change?", "notes_required": 1, "build": 1},
	"Answer Query": {"kind": "answer", "label": "Answer", "style": "secondary", "notes": "Your answer", "notes_required": 1},
	"Start Work": {"kind": "wf", "label": "Start work", "style": "secondary"},
	"Retest Passed": {"kind": "retest_pass", "label": "Pass", "style": "success", "notes": "Notes (optional)", "build": 1, "shots": 1},
	"Retest Failed": {"kind": "retest_fail", "label": "Fail", "style": "danger", "notes": "What is still wrong?", "notes_required": 1, "build": 1, "shots": 1},
	"UAT Accept": {"kind": "uat_accept", "label": "Accept", "style": "success", "notes": "Notes (optional)", "shots": 1},
	"UAT Reject": {"kind": "uat_reject", "label": "Reject", "style": "danger", "notes": "Why is it rejected?", "notes_required": 1, "shots": 1},
	"Accept Answer": {"kind": "wf", "label": "Answer is fine", "style": "success"},
	"Not Resolved": {"kind": "wf", "label": "Not resolved", "style": "danger", "notes": "What is still unclear?"},
	"Triage": {"kind": "wf", "label": "Triage", "style": "secondary"},
	"Assign to Developer": {"kind": "assign", "label": "Assign", "style": "primary"},
	"Confirm": {"kind": "wf", "label": "Confirm", "style": "success"},
	"Send to UAT": {"kind": "wf", "label": "Send to UAT", "style": "primary"},
	"Close without UAT": {"kind": "wf", "label": "Close (no UAT)", "style": "secondary"},
	"Reject": {"kind": "wf", "label": "Reject", "style": "danger", "notes": "Why isn't this a valid issue? (duplicate, works as designed, user error…)", "notes_required": 1,
		"hint": "Not a real issue. It is closed."},
	"Defer": {"kind": "wf", "label": "Defer (later)", "style": "secondary", "notes": "Why park it, and until when? (e.g. after go-live, phase 2)", "notes_required": 1,
		"hint": "Valid, but parked for later. A QA lead can reactivate it."},
	"Reactivate": {"kind": "wf", "label": "Reactivate", "style": "secondary"},
	"Reopen": {"kind": "wf", "label": "Reopen", "style": "danger", "notes": "Reason"},
}
# result-type actions go through api.record_result (sets the result field first)
RESULT_KINDS = {"fix", "answer", "retest_pass", "retest_fail", "uat_accept", "uat_reject"}


def _require_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in"), frappe.PermissionError)
	if not (set(frappe.get_roles()) & QA_ROLES) and frappe.session.user != "Administrator":
		frappe.throw(_("You don't have access to QA Tracker. Ask your QA lead to give you a QA role."), frappe.PermissionError)


def _roles():
	r = set(frappe.get_roles())
	if frappe.session.user == "Administrator":
		r |= {"QA Lead"}
	return r


def stage_index(status):
	for i, (_label, states) in enumerate(STAGES):
		if status in states:
			return i
	return -1


def _needs_you_filters(user, roles):
	"""List of OR-groups describing tickets waiting on this user."""
	groups = [
		{"reported_by": user, "status": ["in", ["Ready for Retest", "Answered"]]},
	]
	if "Vendor Developer" in roles or "QA Lead" in roles:
		groups.append({"assigned_to": user, "status": ["in", ["Assigned", "In Progress", "Reopened"]]})
	if "UAT User" in roles:
		groups.append({"status": "In UAT"})
	if "QA Lead" in roles:
		groups.append({"status": ["in", ["New", "Retest Passed", "Confirmed"]]})
	return groups


def _project(project=None):
	"""Validate the project picked in the portal. None = all of the user's projects."""
	if not project or project == "all":
		return None
	access.check_project(project)
	return project


def _pf(filters, project):
	"""Filter on a project and its sub-projects."""
	if project:
		filters = dict(filters, project=["in", sorted(access.descendants("QA Project", project))])
	return filters


def _mine_filter(user, roles):
	if roles & {"QA Lead", "QA Viewer", "Vendor Developer", "System Manager"}:
		return None  # sees everything they have access to (vendor staff: their vendor's tickets)
	return [{"reported_by": user}, {"assigned_to": user}, {"owner": user}]


def _thumb(name):
	return frappe.db.get_value("QA Screenshot", {"parent": name, "parentfield": "screenshots"}, "image", order_by="idx asc")


FIELDS = ["name", "title", "status", "severity", "module", "site", "issue_code", "modified", "reported_by", "project", "vendor",
	"assigned_to", "source_channel", "issue_type"]


def _row(d, user, roles, needs=None):
	d = frappe._dict(d)
	return {
		"name": d.name,
		"title": d.title,
		"status": d.status,
		"stage": stage_index(d.status),
		"severity": d.severity,
		"module": d.module,
		"site": d.site,
		"project": d.get("project"),
		"vendor": d.get("vendor"),
		"code": d.issue_code,
		"type": d.issue_type,
		"ago": pretty_date(d.modified),
		"thumb": _thumb(d.name),
		"needs_you": bool(needs and d.name in needs),
		"mine": d.reported_by == user,
	}


def _needs_names(user, roles, limit=200, project=None):
	names = set()
	for g in _needs_you_filters(user, roles):
		names.update(frappe.get_list("QA Issue", filters=_pf(g, project), pluck="name", limit=limit))
	return names


def _scoreboard(project):
	"""Per-vendor open / blocker / overdue counts for client staff."""
	if not project or access.vendor_of(frappe.session.user, project):
		return []
	open_f = ["not in", DONE + ["Deferred"]]
	rows = frappe.db.sql(
		"""select ifnull(vendor, '') as vendor, count(*) as open,
			sum(severity='Blocker') as blockers,
			sum(target_date is not null and target_date < %(today)s) as overdue,
			sum(status='Ready for Retest') as retest,
			round(avg(greatest(0, datediff(%(today)s, date(ifnull(reported_on, creation)))))) as avg_age
		from `tabQA Issue` where project in %(projects)s and status not in %(closed)s group by ifnull(vendor, '') order by open desc""",
		{"projects": tuple(access.descendants("QA Project", project)), "closed": tuple(open_f[1]), "today": frappe.utils.today()},
		as_dict=True,
	)
	for v in access.project_vendors(project):
		if not any(r.vendor == v.vendor for r in rows):
			rows.append(frappe._dict(vendor=v.vendor, open=0, blockers=0, overdue=0, retest=0, avg_age=0))
	for r in rows:
		r.label = r.vendor or _("No vendor yet")
		r.product = frappe.db.get_value("QA Vendor", r.vendor, "product") if r.vendor else ""
		for k in ("open", "blockers", "overdue", "retest", "avg_age"):
			r[k] = cint(r[k])
	return rows


@frappe.whitelist()
def boot(project=None):
	_require_user()
	user, roles = frappe.session.user, _roles()
	s = settings()
	projects = access.my_projects(user)
	names = [p.name for p in projects]
	if project not in names and project != "all":
		project = s.default_project if s.default_project in names else (names[0] if names else None)
	cur = None if project == "all" else project
	needs = _needs_names(user, roles, project=cur)
	mine = _mine_filter(user, roles)
	open_f = {"status": ["not in", DONE + ["Deferred"]]}
	open_count = len(frappe.get_list("QA Issue", filters=_pf(open_f, cur), pluck="name", limit=5000)) if mine is None else len(
		{n for g in mine for n in frappe.get_list("QA Issue", filters=_pf(dict(g, **open_f), cur), pluck="name")})
	sites = access.sites_for_project(cur) if cur else access.sites_for_project(None)
	mod_f = {"is_active": 1}
	mod_or = [["project", "is", "not set"], ["project", "in", access.ancestors("QA Project", cur)]] if cur else None
	my_vendor = access.vendor_of(user, cur) if cur else None
	lim_sites, lim_mods = access.limits(user, cur) if cur else (None, None)
	if lim_sites is not None:
		sites = [x for x in sites if x.name in lim_sites]
	modules = frappe.get_all("QA Module", filters=mod_f, or_filters=mod_or, fields=["name", "module_code as code", "keywords", "vendor"],
		order_by="name asc")
	if lim_mods is not None:
		modules = [m for m in modules if m.name in lim_mods]
	runs = frappe.db.count("QA Test Execution", {"tester": user, "result": "Not Run"}) if frappe.db.exists(
		"DocType", "QA Test Execution") else 0
	channels = []
	if s.telegram_enabled and s.telegram_bot_username:
		channels.append({"name": "Telegram", "hint": "@" + s.telegram_bot_username, "url": f"https://t.me/{s.telegram_bot_username}"})
	if s.whatsapp_enabled:
		channels.append({"name": "WhatsApp", "hint": "Message the QA WhatsApp number"})
	if s.raven_enabled:
		chan = frappe.db.get_value("Raven Channel", s.raven_channel, "channel_name") if s.raven_channel and frappe.db.exists(
			"DocType", "Raven Channel") else None
		channels.append({"name": "Raven", "hint": f"Post in #{chan}" if chan else "Post in the QA channel", "url": "/raven"})
	inbox = frappe.db.get_value("Email Account", {"append_to": "QA Issue", "enable_incoming": 1}, "email_id")
	if inbox:
		channels.append({"name": "Email", "hint": inbox, "url": f"mailto:{inbox}"})
	if s.teams_enabled:
		channels.append({"name": "Teams", "hint": "@QA Tracker in the QA channel"})
	return {
		"user": user,
		"full_name": frappe.utils.get_fullname(user),
		"roles": sorted(roles & QA_ROLES),
		"party": party_for_user(user),
		"is_lead": "QA Lead" in roles,
		"is_dev": "Vendor Developer" in roles,
		"title": s.portal_title or "QA Tracker",
		"logo": s.portal_logo,
		"accent": s.portal_accent or "#0F766E",
		"help": s.portal_help,
		"default_site": s.default_site if any(x.name == s.default_site for x in sites) else None,
		"sites": [{"name": x.name, "code": x.site_code, "path": x.path, "group": x.is_group} for x in sites],
		"modules": modules,
		"projects": [{"name": p.name, "code": p.project_code, "client": p.client, "status": p.status, "depth": p.depth,
			"path": p.path, "parent": p.parent_qa_project} for p in projects],
		"is_project_lead": bool(cur and access.is_project_lead(user, cur)),
		"limits": {"sites": sorted(lim_sites) if lim_sites is not None else None,
			"modules": sorted(lim_mods) if lim_mods is not None else None},
		"subprojects": [p.name for p in projects if p.parent_qa_project == cur] if cur else [],
		"project": project,
		"vendors": [{"name": v.vendor, "scope": v.scope, "product": frappe.db.get_value("QA Vendor", v.vendor, "product")}
			for v in access.project_vendors(cur)] if cur else [],
		"my_vendor": my_vendor,
		"scoreboard": _scoreboard(cur),
		"counts": {"needs_you": len(needs), "open": open_count, "runs": runs},
		"channels": channels,
		"desk": bool(roles & {"QA Lead", "System Manager", "GA Analyst"}),
		"max_upload": max_upload_bytes(),
		"gaps": bool(roles & {"GA Analyst", "GA Approver", "QA Lead", "System Manager"}) or bool(
			frappe.db.exists("Gap Item", {"assigned_to": user})) or bool(frappe.db.exists("Gap Item", {"raised_by": user})),
		"gap_needs": _gap_needs_count(user, roles),
	}


def _gap_needs_count(user, roles):
	try:
		from qa_tracker.gap_analysis.portal import _needs

		return len(_needs(user, roles))
	except Exception:
		return 0


@frappe.whitelist()
def tickets(scope="needs_you", search=None, start=0, project=None, vendor=None):
	_require_user()
	user, roles = frappe.session.user, _roles()
	start = cint(start)
	project = _project(project)
	needs = _needs_names(user, roles, project=project)
	filters = _pf({}, project)
	if vendor:
		filters["vendor"] = ["is", "not set"] if vendor == "-" else vendor
	or_filters = None
	if scope == "needs_you":
		if not needs:
			return []
		filters["name"] = ["in", list(needs)]
	else:
		filters["status"] = ["in", DONE] if scope == "done" else ["not in", DONE]
		mine = _mine_filter(user, roles)
		if mine is not None:
			or_filters = [["reported_by", "=", user], ["assigned_to", "=", user], ["owner", "=", user]]
	if search:
		search = search.strip()
		if re.match(r"^(ISS-)?\d+$", search, re.I):
			n = search.upper()
			filters["name"] = f"ISS-{int(n.replace('ISS-', '')):05d}"
		else:
			filters["title"] = ["like", f"%{search}%"]
	rows = frappe.get_list("QA Issue", filters=filters, or_filters=or_filters, fields=FIELDS,
		order_by="modified desc", start=start, limit=30)
	return [_row(r, user, roles, needs) for r in rows]


def _actions(doc, user, roles):
	from frappe.model.workflow import get_transitions

	seen, out = set(), []
	try:
		transitions = get_transitions(doc)
	except Exception:
		transitions = []
	# result actions are offered regardless of the condition (the portal sets the result first)
	extra = []
	if doc.status == "Ready for Retest" and roles & {"QA Tester", "QA Lead"}:
		extra = ["Retest Passed", "Retest Failed"]
	elif doc.status == "In UAT" and roles & {"UAT User", "QA Lead"}:
		extra = ["UAT Accept", "UAT Reject"]
	elif doc.status in ("Assigned", "In Progress", "Reopened") and roles & {"Vendor Developer", "QA Lead"}:
		extra = ["Mark Fixed"] + (["Answer Query"] if doc.issue_type == "Query" else [])
	elif doc.status == "Triaged" and "QA Lead" in roles:
		extra = ["Assign to Developer"]  # shown even before a developer is set - the sheet asks for one
	for action in extra + [t.action for t in transitions]:
		if action in seen or action not in ACTION_UI:
			continue
		seen.add(action)
		out.append(dict(ACTION_UI[action], action=action))
	return out


@frappe.whitelist()
def ticket(name):
	_require_user()
	doc = frappe.get_doc("QA Issue", name)
	doc.check_permission("read")
	user, roles = frappe.session.user, _roles()
	timeline = []
	for u in doc.updates:
		timeline.append({
			"by": u.sender_name or (frappe.utils.get_fullname(u.posted_by) if u.posted_by else u.party),
			"party": u.party,
			"channel": u.channel,
			"type": u.update_type,
			"text": u.message,
			"image": u.screenshot,
			"video": u.attachment if u.attachment and file_kind(u.attachment) == "Recording" else None,
			"file": {"url": u.attachment, "name": u.attachment_name or u.attachment.rsplit("/", 1)[-1], "kind": file_kind(u.attachment)}
				if u.attachment and file_kind(u.attachment) not in (None, "Recording") else None,
			"ago": pretty_date(u.posted_on) if u.posted_on else "",
			"mine": u.posted_by == user,
		})
	devs = []
	if "QA Lead" in roles:
		devs = [{"value": d.name, "label": d.full_name or d.name} for d in access.developers(doc.project, doc.vendor)]
	return {
		"name": doc.name,
		"title": doc.title,
		"code": doc.issue_code,
		"status": doc.status,
		"stage": stage_index(doc.status),
		"severity": doc.severity,
		"type": doc.issue_type,
		"site": doc.site,
		"module": doc.module,
		"project": doc.get("project"),
		"vendor": doc.get("vendor"),
		"target_date": str(doc.target_date) if doc.get("target_date") else None,
		"overdue": bool(doc.get("target_date") and str(doc.target_date) < frappe.utils.today() and doc.status not in DONE + ["Deferred", "Ready for Retest", "Retest Passed", "Confirmed", "In UAT"]),
		"description": doc.description,
		"reporter": doc.reporter_name or (frappe.utils.get_fullname(doc.reported_by) if doc.reported_by else None),
		"developer": frappe.utils.get_fullname(doc.assigned_to) if doc.assigned_to else None,
		"assigned_to": doc.assigned_to,
		"channel": doc.source_channel,
		"reported_ago": pretty_date(doc.reported_on or doc.creation),
		"resolution": doc.resolution,
		"fixed_in_build": doc.fixed_in_build,
		"retest_count": doc.retest_count,
		"reopen_count": doc.reopen_count,
		"shots": {
			"reported": [s.image for s in doc.screenshots if s.image],
			"retest": [s.image for s in doc.retest_screenshots if s.image],
			"uat": [s.image for s in doc.uat_screenshots if s.image],
		},
		"recordings": [{"url": r.file, "caption": r.caption, "duration": r.duration} for r in doc.get("media_files") or [] if r.file and r.file_type == "Recording"],
		"files": [{"url": r.file, "caption": r.caption, "kind": r.file_type, "name": r.file.rsplit("/", 1)[-1]} for r in doc.get("media_files") or [] if r.file and r.file_type != "Recording"],
		"timeline": timeline,
		"actions": _actions(doc, user, roles),
		"developers": devs,
		"desk_url": f"/app/qa-issue/{doc.name}",
		"merged_into": doc.get("merged_into"),
		"merged_from": frappe.get_all("QA Issue", filters={"merged_into": doc.name}, fields=["name", "title"], order_by="modified desc"),
		"can_merge": _can_merge(doc),
		"similar": _similar_hint(doc),
		"can_update": bool(roles & {"QA Tester", "QA Lead", "Vendor Developer", "UAT User", "System Manager"}),
	}


def _can_merge(doc):
	from qa_tracker.merge import can_merge

	return doc.status != "Merged" and can_merge("QA Issue", doc)


def _similar_hint(doc):
	"""Likely duplicates, shown to people who can merge."""
	if doc.status in DONE or not _can_merge(doc):
		return []
	from qa_tracker.merge import similar

	try:
		return [{"name": r.name, "title": r.title, "status": r.status, "score": r.score} for r in similar("QA Issue", doc.name, 3, 0.34)]
	except Exception:
		return []


@frappe.whitelist()
def merge_candidates(name, txt=None):
	from qa_tracker.merge import search, similar

	rows = search("QA Issue", txt, exclude=name) if txt else similar("QA Issue", name, 10)
	return [{"name": r.name, "title": r.title, "status": r.status, "module": r.module, "site": r.site,
		"score": r.get("score"), "project": r.project} for r in rows]


@frappe.whitelist()
def merge(target, sources):
	from qa_tracker.merge import merge_issues

	return merge_issues(target, sources)


def _decode_images(images):
	out = []
	for i, data in enumerate(frappe.parse_json(images) if images else []):
		if not data:
			continue
		if isinstance(data, dict):
			fname, data = data.get("name") or f"shot_{i}.png", data.get("data")
		else:
			fname = f"shot_{i}.png"
		m = re.match(r"^data:image/(png|jpe?g|webp|gif);base64,(.*)$", data or "", re.S)
		if not m:
			continue
		ext = "jpg" if m.group(1).startswith("jp") else m.group(1)
		content = base64.b64decode(m.group(2))
		if len(content) > 10 * 1024 * 1024:
			frappe.throw(_("Screenshot is too large (max 10 MB)"))
		base = re.sub(r"[^\w.-]", "_", fname.rsplit(".", 1)[0])[:40] or f"shot_{i}"
		out.append((f"{base}.{ext}", content))
	return out


@frappe.whitelist()
def create(text, site=None, module=None, severity="Medium", issue_type=None, images=None, videos=None, files=None,
	project=None, vendor=None):
	_require_user()
	from qa_tracker import intake

	project = _project(project) or access.default_project_for(frappe.session.user)
	if vendor and vendor not in [v.vendor for v in access.project_vendors(project)]:
		vendor = None
	my_vendor = access.vendor_of(frappe.session.user, project)
	if my_vendor:
		vendor = my_vendor  # vendor staff can only raise tickets for their own vendor
	text = (text or "").strip()
	shots = _decode_images(images)
	vids = parse_files(files, videos)
	if not text and not shots and not vids:
		frappe.throw(_("Add a screenshot or describe the problem"))
	clean, tags = intake.parse_tags(text)
	doc = frappe.get_doc(
		{
			"doctype": "QA Issue",
			"title": intake.make_title(clean, _("Screenshot from {0}").format(frappe.utils.get_fullname())),
			"description": intake.text_to_html(clean),
			"site": site or tags.get("site"),
			"module": module or tags.get("module") or intake.guess_module(clean),
			"severity": severity if severity in ("Blocker", "High", "Medium", "Low") else "Medium",
			"issue_type": issue_type or tags.get("issue_type") or intake.guess_type(clean),
			"source_channel": "Portal",
			"reported_by": frappe.session.user,
			"project": project or tags.get("project"),
			"vendor": vendor,
		}
	)
	doc.insert()
	for fname, content in shots:
		url = save_file(doc.name, fname, content)
		add_screenshot(doc.name, url)
	for v in vids:
		attach_existing_file(v["url"], "QA Issue", doc.name)
		add_attachment(doc.name, "QA Issue", v, caption=_("Reported"))
	return doc.name


@frappe.whitelist()
def update(name, text=None, images=None, videos=None, files=None):
	_require_user()
	frappe.has_permission("QA Issue", "read", doc=name, throw=True)
	shots = _decode_images(images)
	vids = parse_files(files, videos)
	text = (text or "").strip()
	if not text and not shots and not vids:
		frappe.throw(_("Write something or add a screenshot"))
	urls = [save_file(name, f, c) for f, c in shots]
	for v in vids:
		attach_existing_file(v["url"], "QA Issue", name)
		add_attachment(name, "QA Issue", v, caption=_("Update"))
	first = vids[0] if vids else None
	label = lambda v: _("Recording added") if v["kind"] == "Recording" else _("{0} attached").format(v["name"])
	append_update(name, text or (label(first) if first and not urls else _("Screenshot added")), channel="Portal",
		screenshot=urls[0] if urls else None, attachment=first["url"] if first else None, attachment_name=first["name"] if first else None)
	for u in urls[1:]:
		append_update(name, _("Screenshot added"), channel="Portal", screenshot=u, notify=False)
	for v in vids[1:]:
		append_update(name, label(v), channel="Portal", attachment=v["url"], attachment_name=v["name"], notify=False)
	return ticket(name)


@frappe.whitelist()
def act(name, action, notes=None, build=None, assigned_to=None, images=None, videos=None, files=None):
	_require_user()
	from frappe.model.workflow import apply_workflow

	from qa_tracker import api

	ui = ACTION_UI.get(action)
	if not ui:
		frappe.throw(_("Unknown action"))
	if ui.get("notes_required") and not (notes or "").strip():
		frappe.throw(_("Please add a note"))
	urls = [save_file(name, f, c) for f, c in _decode_images(images)]
	stage = {"retest_pass": _("Retest"), "retest_fail": _("Retest"), "uat_accept": _("UAT"), "uat_reject": _("UAT"), "fix": _("Fix")}.get(ui["kind"], action)
	for v in parse_files(files, videos):
		attach_existing_file(v["url"], "QA Issue", name)
		add_attachment(name, "QA Issue", v, caption=stage)
		append_update(name, (_("Recording added ({0})") if v["kind"] == "Recording" else _("File attached ({0})")).format(stage),
			channel="Portal", attachment=v["url"], attachment_name=v["name"], notify=False)
	frappe.flags.qa_channel = "Portal"
	try:
		if ui["kind"] in RESULT_KINDS:
			api.record_result(name, ui["kind"], notes=notes, build=build, screenshots=urls)
		else:
			doc = frappe.get_doc("QA Issue", name)
			doc.check_permission("write")
			if ui["kind"] == "assign":
				if not assigned_to:
					frappe.throw(_("Choose a developer"))
				doc.assigned_to = assigned_to
				doc.save()
			elif doc.status in ("New",) and not doc.module:
				frappe.throw(_("Set a module first (open in Desk)"))
			apply_workflow(doc, action)
			if notes:
				append_update(name, notes, channel="Portal", notify=False)
			for u in urls:
				append_update(name, _("Screenshot added"), channel="Portal", screenshot=u, notify=False)
	finally:
		frappe.flags.qa_channel = None
	return ticket(name)


@frappe.whitelist()
def runs():
	_require_user()
	rows = frappe.get_all(
		"QA Test Execution",
		filters={"tester": frappe.session.user},
		fields=["name", "test_case", "case_title", "module", "result", "test_cycle", "issue", "modified"],
		order_by="modified desc",
		limit=200,
	)
	for r in rows:
		r["ago"] = pretty_date(r.modified)
	rows.sort(key=lambda r: 0 if r.result == "Not Run" else 1)  # to-do first
	return rows


@frappe.whitelist()
def run(name):
	_require_user()
	doc = frappe.get_doc("QA Test Execution", name)
	doc.check_permission("read")
	return {
		"name": doc.name,
		"case": doc.test_case,
		"title": doc.case_title,
		"cycle": doc.test_cycle,
		"module": doc.module,
		"steps": doc.steps,
		"expected": doc.expected_result,
		"result": doc.result,
		"actual": doc.actual_result,
		"issue": doc.issue,
	}


@frappe.whitelist()
def run_result(name, result, actual=None, images=None, videos=None, files=None):
	_require_user()
	from qa_tracker import api

	if result not in ("Pass", "Fail", "Blocked", "Skipped"):
		frappe.throw(_("Invalid result"))
	doc = frappe.get_doc("QA Test Execution", name)
	doc.check_permission("write")
	doc.result = result
	doc.actual_result = actual or doc.actual_result
	for fname, content in _decode_images(images):
		f = frappe.get_doc({"doctype": "File", "file_name": fname, "content": content, "attached_to_doctype": "QA Test Execution",
			"attached_to_name": doc.name, "is_private": 1}).insert(ignore_permissions=True)
		doc.append("screenshots", {"image": f.file_url})
	vids = parse_files(files, videos)
	for v in vids:
		attach_existing_file(v["url"], "QA Test Execution", doc.name)
		doc.append("media_files", {"file": v["url"], "file_type": v["kind"], "caption": _("Test run"), "duration": v["duration"], "added_by": frappe.session.user})
	doc.save()
	issue = None
	if result in ("Fail", "Blocked"):
		issue = api.raise_issue_from_execution(doc.name)
		for v in vids:
			attach_existing_file(v["url"], "QA Issue", issue)
			add_attachment(issue, "QA Issue", v, caption=_("Test run"))
	return {"issue": issue}


# ---------------------------------------------------------------- team & coverage (project leads)
TESTING_ROLES = ("Tester", "UAT User", "QA Lead")


def _require_lead(project):
	_require_user()
	if not project or project == "all":
		frappe.throw(_("Pick a project first"))
	if not access.is_project_lead(frappe.session.user, project):
		frappe.throw(_("Only the project's QA Leads can manage the team"), frappe.PermissionError)


def _covers(allocs, site, module, site_desc):
	"""Does a person (with these allocation rows; empty = everything) cover this leaf site + area?"""
	if not allocs:
		return True
	for a in allocs:
		if a.site and site not in site_desc(a.site):
			continue
		if a.module and a.module != module:
			continue
		return True
	return False


@frappe.whitelist()
def team(project):
	_require_lead(project)
	members = access.members_for(project)
	chain = access.ancestors("QA Project", project)
	allocs = frappe.get_all("QA Project Allocation", filters={"parenttype": "QA Project", "parent": ["in", chain]},
		fields=["name", "parent", "user", "site", "module", "note"], order_by="idx")
	by_user = {}
	for a in allocs:
		by_user.setdefault((a.parent, a.user), []).append(a)
	people = []
	for m in members:
		people.append({
			"row": m.name, "user": m.user, "name": m.full_name or m.user, "role": m.project_role, "vendor": m.vendor,
			"active": bool(m.is_active), "project": m.parent, "inherited": m.parent != project,
			"limits": [{"row": a.name, "site": a.site, "module": a.module, "note": a.note} for a in by_user.get((m.parent, m.user), [])],
		})
	sites = [x for x in access.sites_for_project(project) if not x.is_group] or access.sites_for_project(project)
	mod_or = [["project", "is", "not set"], ["project", "in", chain]]
	modules = frappe.get_all("QA Module", filters={"is_active": 1}, or_filters=mod_or, fields=["name", "module_code"], order_by="name")
	cache = {}

	def site_desc(s):
		if s not in cache:
			cache[s] = access.descendants("QA Site", s)
		return cache[s]

	testers = [p for p in people if p["active"] and p["role"] in TESTING_ROLES and not p["vendor"]]
	grid = []
	for st in sites:
		row = {"site": st.name, "path": st.path, "cells": []}
		for md in modules:
			who = [p["name"] for p in testers if _covers([frappe._dict(x) for x in p["limits"]], st.name, md.name, site_desc)]
			row["cells"].append({"module": md.name, "count": len(who), "who": who[:6]})
		grid.append(row)
	subs = frappe.get_all("QA Project", filters={"parent_qa_project": project}, fields=["name", "project_code", "status", "client"], order_by="lft")
	for sp in subs:
		sp.members = frappe.db.count("QA Project Member", {"parenttype": "QA Project", "parent": sp.name, "is_active": 1})
		sp.open = frappe.db.count("QA Issue", {"project": ["in", sorted(access.descendants("QA Project", sp.name))],
			"status": ["not in", DONE + ["Deferred"]]})
	gaps = sum(1 for r in grid for c in r["cells"] if not c["count"])
	return {
		"project": project, "people": people, "sites": [{"name": x.name, "path": x.path, "group": x.is_group} for x in access.sites_for_project(project)],
		"modules": [m.name for m in modules], "grid": grid, "subprojects": subs, "uncovered": gaps,
		"vendors": [v.vendor for v in access.project_vendors(project)],
		"roles": ["QA Lead", "Tester", "Developer", "UAT User", "Viewer", "Gap Analyst", "Gap Approver"],
	}


def _project_doc(project):
	doc = frappe.get_doc("QA Project", project)
	doc.flags.ignore_permissions = True  # checked by _require_lead
	return doc


@frappe.whitelist()
def allocate(project, user, site=None, module=None, note=None):
	_require_lead(project)
	doc = _project_doc(project)
	if not any(m.user == user for m in doc.members):
		frappe.throw(_("{0} isn't in this project's own team (they may come from a parent project). Add them here first.").format(user))
	if site and site not in {x.name for x in access.sites_for_project(project)}:
		frappe.throw(_("{0} isn't one of this project's sites").format(site))
	doc.append("allocations", {"user": user, "site": site or None, "module": module or None, "note": note})
	doc.save()
	return team(project)


@frappe.whitelist()
def unallocate(project, row):
	_require_lead(project)
	doc = _project_doc(project)
	doc.allocations = [a for a in doc.allocations if a.name != row]
	doc.save()
	return team(project)


@frappe.whitelist()
def add_member(project, user, role="Tester", vendor=None):
	_require_lead(project)
	user = (user or "").strip().lower()
	if not frappe.db.exists("User", user):
		frappe.throw(_("No user {0}. Create the user in Desk first (User > New).").format(user))
	doc = _project_doc(project)
	if any(m.user == user and m.project_role == role for m in doc.members):
		frappe.throw(_("{0} is already in the team as {1}").format(user, role))
	doc.append("members", {"user": user, "project_role": role, "vendor": vendor or None, "is_active": 1})
	doc.save()
	return team(project)


@frappe.whitelist()
def set_member_active(project, row, active=1):
	_require_lead(project)
	doc = _project_doc(project)
	for m in doc.members:
		if m.name == row:
			m.is_active = cint(active)
	doc.save()
	return team(project)


@frappe.whitelist()
def new_subproject(project, name, code, root_site=None):
	_require_lead(project)
	name, code = (name or "").strip(), (code or "").strip()
	if not name or not code:
		frappe.throw(_("Give the sub-project a name and a short code"))
	sp = frappe.get_doc({"doctype": "QA Project", "project_name": name, "project_code": code, "parent_qa_project": project,
		"status": "Active", "root_site": root_site or None,
		"client": frappe.db.get_value("QA Project", project, "client")})
	sp.flags.ignore_permissions = True
	sp.insert()
	return team(project)
