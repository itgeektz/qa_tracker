"""Whitelisted methods used by the desk UI and by external integrations."""

import base64
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from qa_tracker.utils import add_screenshot, append_update, html2text, party_for_user, settings


# ---------------------------------------------------------------------------
# updates from tester / developer (works in any status)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def add_update(issue, message, screenshots=None):
	frappe.has_permission("QA Issue", "read", doc=issue, throw=True)
	if not set(frappe.get_roles()) & {"QA Tester", "QA Lead", "Vendor Developer", "UAT User", "System Manager"}:
		frappe.throw(_("You are not allowed to post updates"), frappe.PermissionError)
	shots = _as_list(screenshots)
	message = (message or "").strip()
	if not message and not shots:
		frappe.throw(_("Write a message or attach a screenshot"))
	row = append_update(issue, message or _("Screenshot added"), screenshot=shots[0] if shots else None)
	for url in shots[1:]:
		append_update(issue, _("Screenshot added"), screenshot=url, notify=False)
	return row.name


# ---------------------------------------------------------------------------
# one-click stage actions with their details
# ---------------------------------------------------------------------------
ACTIONS = {
	"fix": ("Mark Fixed", {"resolution": "notes", "root_cause": "root_cause", "fixed_in_build": "build"}, None),
	"answer": ("Answer Query", {"resolution": "notes"}, None),
	"retest_pass": ("Retest Passed", {"retest_notes": "notes", "retest_build": "build"}, ("retest_result", "Pass", "retest_screenshots")),
	"retest_fail": ("Retest Failed", {"retest_notes": "notes", "retest_build": "build"}, ("retest_result", "Fail", "retest_screenshots")),
	"uat_accept": ("UAT Accept", {"uat_notes": "notes"}, ("uat_result", "Accepted", "uat_screenshots")),
	"uat_reject": ("UAT Reject", {"uat_notes": "notes"}, ("uat_result", "Rejected", "uat_screenshots")),
}


@frappe.whitelist()
def record_result(issue, kind, notes=None, build=None, root_cause=None, screenshots=None):
	from frappe.model.workflow import apply_workflow

	if kind not in ACTIONS:
		frappe.throw(_("Unknown action"))
	action, mapping, result = ACTIONS[kind]
	doc = frappe.get_doc("QA Issue", issue)
	doc.check_permission("write")
	values = {"notes": notes, "build": build, "root_cause": root_cause}
	for field, key in mapping.items():
		if values.get(key):
			doc.set(field, values[key])
	shots = _as_list(screenshots)
	if result:
		field, value, shot_field = result
		doc.set(field, value)
		for url in shots:
			doc.append(shot_field, {"image": url, "added_by": frappe.session.user})
	# apply_workflow reloads from DB, so persist the details first
	doc.save()
	doc = apply_workflow(doc, action)
	if shots and not result:
		for url in shots:
			append_update(issue, _("Screenshot added"), screenshot=url, notify=False)
	return doc.status


# ---------------------------------------------------------------------------
# test execution helpers
# ---------------------------------------------------------------------------
@frappe.whitelist()
def raise_issue_from_execution(execution):
	exe = frappe.get_doc("QA Test Execution", execution)
	exe.check_permission("write")
	if exe.issue:
		return exe.issue
	case = frappe.get_doc("QA Test Case", exe.test_case)
	cycle = frappe.get_doc("QA Test Cycle", exe.test_cycle)
	issue = frappe.get_doc(
		{
			"doctype": "QA Issue",
			"title": f"{case.title} - failed",
			"issue_type": "Bug",
			"severity": {"Critical": "Blocker", "High": "High", "Low": "Low"}.get(case.priority, "Medium"),
			"found_in_phase": cycle.phase or "Test",
			"site": cycle.site,
			"project": cycle.get("project"),
			"vendor": cycle.get("vendor"),
			"module": case.module,
			"screen": case.screen,
			"test_cycle": exe.test_cycle,
			"test_case": exe.test_case,
			"test_execution": exe.name,
			"steps_to_reproduce": html2text(case.steps or ""),
			"expected_result": case.expected_result,
			"actual_result": exe.actual_result,
			"build_found": exe.build_version or cycle.build_version,
			"reported_by": exe.tester or frappe.session.user,
			"source_channel": "Web",
		}
	)
	for s in exe.screenshots:
		issue.append("screenshots", {"image": s.image, "caption": s.caption, "added_by": s.added_by})
	issue.insert()
	exe.db_set("issue", issue.name)
	return issue.name


@frappe.whitelist()
def create_cycle_runs(cycle):
	"""Create 'Not Run' executions for each tester assignment in the cycle."""
	doc = frappe.get_doc("QA Test Cycle", cycle)
	doc.check_permission("write")
	created = 0
	for a in doc.assignments:
		cases = [a.test_case] if a.test_case else frappe.get_all(
			"QA Test Case", filters={"module": a.module, "is_active": 1}, pluck="name", order_by="name asc"
		)
		for case in cases:
			if frappe.db.exists("QA Test Execution", {"test_cycle": cycle, "test_case": case, "tester": a.tester}):
				continue
			frappe.get_doc(
				{
					"doctype": "QA Test Execution",
					"test_cycle": cycle,
					"test_case": case,
					"tester": a.tester,
					"result": "Not Run",
					"build_version": doc.build_version,
				}
			).insert()
			created += 1
	from qa_tracker.qa_tracker.doctype.qa_test_cycle.qa_test_cycle import update_cycle_stats

	update_cycle_stats(cycle)
	return created


# ---------------------------------------------------------------------------
# generic intake API (Power Automate, scripts, other tools)
# ---------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True, methods=["POST"])
def intake(**kwargs):
	"""POST JSON with header X-QA-Token.

	{
	  "channel": "Teams" | "API" | "WhatsApp" | "Email",
	  "sender_id": "unique sender id (email / phone / AAD id)",
	  "sender_name": "Jane Tester",
	  "sender_email": "jane@hospital.co.ke",   (optional, used to match a user)
	  "sender_phone": "2547...",                (optional)
	  "message_id": "unique id to avoid duplicates",  (optional)
	  "text": "message text, may contain #PKL #BIL or ISS-00012 ...",
	  "images": [{"filename": "a.png", "content": "<base64>"} , {"url": "https://..."}]
	}
	Returns {"issue": "ISS-00012", "reply": "...", "url": "..."}
	"""
	import hmac

	import requests

	s = settings()
	token = s.get_password("api_token", raise_exception=False) if s.api_token else None
	given = frappe.get_request_header("X-QA-Token") or ""
	if not (s.api_enabled and token and hmac.compare_digest(given, token)):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	data = frappe.request.get_json(silent=True) or kwargs
	images = []
	for i, img in enumerate(data.get("images") or []):
		name = img.get("filename") or f"image_{i}.png"
		if img.get("content"):
			content = img["content"]
			if "," in content[:100] and content.startswith("data:"):
				content = content.split(",", 1)[1]
			images.append((name, base64.b64decode(content)))
		elif img.get("url"):
			r = requests.get(img["url"], timeout=30)
			if r.ok:
				images.append((name, r.content))
	channel = data.get("channel") if data.get("channel") in ("Teams", "WhatsApp", "Email", "API") else "API"

	from qa_tracker import intake as _intake

	frappe.set_user("Administrator")
	out = _intake.handle_chat_message(
		channel,
		data.get("sender_id") or data.get("sender_email") or data.get("sender_phone"),
		text=data.get("text"),
		images=images,
		sender_name=data.get("sender_name"),
		email=data.get("sender_email"),
		phone=data.get("sender_phone"),
		message_id=data.get("message_id"),
	)
	frappe.db.commit()
	from qa_tracker.utils import issue_url

	return {"issue": out.get("issue"), "reply": out.get("reply"), "url": issue_url(out["issue"]) if out.get("issue") else None}


def _as_list(value):
	if not value:
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			value = [value]
	return [v for v in value if v]
