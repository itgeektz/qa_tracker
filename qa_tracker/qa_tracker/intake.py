"""Turn incoming messages (email, WhatsApp, Teams, API) into tickets and updates.

Message conventions (same on every channel):

* Any message + screenshots      -> new ticket (chat messages from the same sender
                                    within the grouping window go into the same ticket)
* Tags anywhere in the text      -> #PKL / [PKL] site, #BIL module code, #blocker #high #low,
                                    #query (question instead of bug)
* "ISS-00012 <text>"             -> adds an update (and any screenshot) to that ticket
* "ISS-00012 fixed <resolution>" -> developer marks it fixed  (ready for retest)
* "ISS-00012 pass|fail <notes>"  -> tester records the retest result
* "ISS-00012 accept|reject ..."  -> UAT user records the UAT result
* "status ISS-00012"             -> current status
* "my tickets"                   -> sender's latest open tickets
* "new"                          -> next message starts a new ticket
* "help"                         -> this list
"""

import re
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, escape_html, now_datetime

from qa_tracker.compat import cache as _cache
from qa_tracker.compat import clear_last_message
from qa_tracker.utils import (
	ISSUE_REF_RE,
	add_screenshot,
	append_update,
	find_user,
	issue_url,
	refresh_issue_code,
	party_for_user,
	save_file,
	settings,
)

PLACEHOLDER_TITLE = "Screenshot from "
SEVERITY_TAGS = {"blocker": "Blocker", "critical": "Blocker", "high": "High", "medium": "Medium", "low": "Low"}
TYPE_TAGS = {"query": "Query", "question": "Query", "config": "Configuration", "cr": "Change Request", "change": "Change Request"}

HELP_TEXT = """QA Tracker - how to report
• Send a message and screenshots: a ticket is created.
  Messages within a few minutes join the same ticket.
• Tags: #PKL (site) #BIL (module) #blocker #high #query
• ISS-00012 your text  → add an update / screenshot
• ISS-00012 fixed <what was done>  → developer: ready for retest
• ISS-00012 pass <notes>  /  ISS-00012 fail <notes>  → retest result
• ISS-00012 accept / reject <notes>  → UAT result
• status ISS-00012  → see status
• my tickets  → your open tickets
• new  → start a fresh ticket"""


# ---------------------------------------------------------------------------
# parsing helpers
# ---------------------------------------------------------------------------
def _codes(doctype, code_field, name_field):
	rows = frappe.get_all(doctype, fields=["name", code_field], filters={"is_active": 1})
	out = {}
	for r in rows:
		out[(r.get(code_field) or "").lower()] = r.name
		out[r.name.lower().replace(" ", "")] = r.name
	return out


def parse_tags(text):
	"""Extract #TAG / [TAG] markers. Returns (clean_text, dict of fields)."""
	found = {}
	if not text:
		return text, found
	sites = _codes("QA Site", "site_code", "site_name")
	modules = _codes("QA Module", "module_code", "module_name")
	projects = {}
	for r in frappe.get_all("QA Project", fields=["name", "project_code"], filters={"status": ["!=", "Closed"]}):
		projects[(r.project_code or "").lower()] = r.name

	def repl(m):
		tag = (m.group(1) or m.group(2) or "").lower()
		if tag in sites and "site" not in found:
			found["site"] = sites[tag]
		elif tag in modules and "module" not in found:
			found["module"] = modules[tag]
		elif tag in projects and "project" not in found:
			found["project"] = projects[tag]
		elif tag in SEVERITY_TAGS:
			found["severity"] = SEVERITY_TAGS[tag]
		elif tag in TYPE_TAGS:
			found["issue_type"] = TYPE_TAGS[tag]
		elif tag in ("uat", "retest"):
			found["found_in_phase"] = tag.upper() if tag == "uat" else "Retest"
		else:
			return m.group(0)
		return " "

	clean = re.sub(r"\[([A-Za-z&]{2,20})\]|(?<![\w/])#([A-Za-z&]{2,20})\b", repl, text)
	clean = re.sub(r"[ \t]{2,}", " ", clean).strip()
	return clean, found


def guess_module(text):
	text = (text or "").lower()
	if not text.strip():
		return None
	best, best_key = None, (0, 0)
	for m in frappe.get_all("QA Module", fields=["name", "keywords"], filters={"is_active": 1}):
		score, first = 0, len(text)
		for kw in (m.keywords or "").split(","):
			kw = kw.strip().lower()
			if not kw:
				continue
			hit = re.search(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", text)
			if hit:
				score += 1 + len(kw.split())  # multi-word keywords are more specific
				first = min(first, hit.start())
		# higher score wins; on a tie, the area mentioned first in the message wins
		key = (score, -first)
		if score and key > best_key:
			best, best_key = m.name, key
	return best


def guess_type(text):
	t = (text or "").strip().lower()
	if t.endswith("?") or re.match(r"^(how|why|what|which|is |are |can |could |will |should |do |does |please let us know)", t):
		return "Query"
	return "Bug"


def make_title(text, fallback):
	for line in (text or "").splitlines():
		line = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip()
		if line:
			return line[:140]
	return fallback


def text_to_html(text):
	return "".join(f"<p>{escape_html(line)}</p>" for line in (text or "").splitlines() if line.strip())


# ---------------------------------------------------------------------------
# ticket creation
# ---------------------------------------------------------------------------
def create_issue(
	channel,
	text,
	images=None,
	sender_key=None,
	sender_name=None,
	email=None,
	phone=None,
	user=None,
	extra=None,
):
	from qa_tracker import access

	clean, tags = parse_tags(text or "")
	user = user or find_user(email=email, phone=phone, full_name=sender_name)
	title = make_title(clean, f"{PLACEHOLDER_TITLE}{sender_name or sender_key or channel}")
	project = tags.get("project") or (extra or {}).get("project")
	if project and user:
		sc = access.scope(user)
		if sc is not None and project not in sc.projects:
			project = None  # not a member: fall back to their own / default project
	doc = frappe.get_doc(
		{
			"doctype": "QA Issue",
			"title": title,
			"description": text_to_html(clean),
			"issue_type": tags.get("issue_type") or guess_type(clean),
			"severity": tags.get("severity") or "Medium",
			"found_in_phase": tags.get("found_in_phase") or "Test",
			"site": tags.get("site"),
			"module": tags.get("module") or (guess_module(clean) if clean else None),
			"source_channel": channel,
			"channel_sender": sender_key,
			"reporter_name": sender_name,
			"raised_by_email": email,
			"raised_by_phone": phone,
			"reported_by": user,
		}
	)
	if extra:
		doc.update({k: v for k, v in extra.items() if k != "project"})
	if project:
		doc.project = project
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	for fname, content in images or []:
		url = save_file(doc.name, fname, content)
		add_screenshot(doc.name, url, user=user or "Guest")
	return doc


def append_to_new_issue(issue, text, images, user=None):
	"""Add a follow-up chat message to a ticket that is still New."""
	doc = frappe.get_doc("QA Issue", issue)
	clean, tags = parse_tags(text or "")
	updates = {}
	for k, v in tags.items():
		if not doc.get(k) or k in ("severity", "issue_type", "site", "module"):
			updates[k] = v
	if clean:
		updates["description"] = (doc.description or "") + text_to_html(clean)
		if (doc.title or "").startswith(PLACEHOLDER_TITLE):
			updates["title"] = make_title(clean, doc.title)
			updates["issue_type"] = tags.get("issue_type") or guess_type(clean)
		if not tags.get("module") and doc.module in (None, "", settings().default_module):
			guessed = guess_module(clean)
			if guessed:
				updates["module"] = guessed
	if updates:
		frappe.db.set_value("QA Issue", issue, updates)
		refresh_issue_code(issue)
	for fname, content in images or []:
		url = save_file(issue, fname, content)
		add_screenshot(issue, url, user=user or "Guest")
	return doc


# ---------------------------------------------------------------------------
# commands on existing tickets
# ---------------------------------------------------------------------------
COMMANDS = {
	"fixed": ("Mark Fixed", "resolution", None, None),
	"answer": ("Answer Query", "resolution", None, None),
	"pass": ("Retest Passed", "retest_notes", "retest_result", "Pass"),
	"passed": ("Retest Passed", "retest_notes", "retest_result", "Pass"),
	"fail": ("Retest Failed", "retest_notes", "retest_result", "Fail"),
	"failed": ("Retest Failed", "retest_notes", "retest_result", "Fail"),
	"accept": ("UAT Accept", "uat_notes", "uat_result", "Accepted"),
	"accepted": ("UAT Accept", "uat_notes", "uat_result", "Accepted"),
	"reject": ("UAT Reject", "uat_notes", "uat_result", "Rejected"),
	"rejected": ("UAT Reject", "uat_notes", "uat_result", "Rejected"),
}


def handle_issue_message(issue, text, images=None, user=None, channel="Web", sender_name=None):
	"""An update addressed to an existing ticket, optionally with a command word."""
	text = (text or "").strip()
	body = ISSUE_REF_RE.sub("", text, count=1).strip(" :-–\n")
	word, _sep, rest = body.partition(" ")
	cmd = COMMANDS.get(word.lower().strip(":,.")) if word else None
	result_msg = None
	screenshot_field = None

	if cmd:
		action, note_field, result_field, result_value = cmd
		rest = rest.strip()
		result_msg, ok = run_action(issue, action, note_field, rest, result_field, result_value, user, channel)
		if ok and result_field == "retest_result":
			screenshot_field = "retest_screenshots"
		elif ok and result_field == "uat_result":
			screenshot_field = "uat_screenshots"

	party = party_for_user(user) if user else "Tester"
	urls = []
	for fname, content in images or []:
		url = save_file(issue, fname, content)
		urls.append(url)
		if screenshot_field:
			add_screenshot(issue, url, field=screenshot_field, user=user or "Guest")

	if not cmd or not result_msg or not result_msg.startswith("✅"):
		message = body or (_("Screenshot added") if urls else "")
		if message or urls:
			append_update(
				issue, message, party=party, channel=channel, user=user or "Guest",
				screenshot=urls[0] if urls else None, sender_name=sender_name,
			)
			for extra in urls[1:]:
				append_update(issue, _("Screenshot added"), party=party, channel=channel, user=user or "Guest",
					screenshot=extra, sender_name=sender_name, notify=False)
	elif urls:
		for url in urls:
			append_update(issue, _("Screenshot added"), party=party, channel=channel, user=user or "Guest",
				screenshot=url, sender_name=sender_name, notify=False)

	status = frappe.db.get_value("QA Issue", issue, "status")
	return result_msg or _("📝 Update added to {0} (status: {1}).").format(issue, status)


def run_action(issue, action, note_field, note, result_field, result_value, user, channel):
	"""Apply a workflow action on behalf of a mapped user. Returns (message, ok)."""
	if not user:
		return (_("⚠️ I couldn't match you to a QA Tracker user, so I saved this as an update only. "
			"Ask your QA lead to add your phone/email to your user profile."), False)
	from frappe.model.workflow import apply_workflow, get_transitions

	original = frappe.session.user
	frappe.db.savepoint("qa_action")
	frappe.set_user(user)
	frappe.flags.qa_channel = channel
	try:
		doc = frappe.get_doc("QA Issue", issue)
		if result_field:
			doc.set(result_field, result_value)
		if note:
			doc.set(note_field, note)
		allowed = [t.action for t in get_transitions(doc)]  # evaluated on the in-memory values
		if action not in allowed:
			return (_("⚠️ {0} is '{1}'. '{2}' isn't possible for you right now (allowed: {3}). Saved as an update.").format(
				issue, doc.status, action, ", ".join(sorted(set(allowed))) or _("none")), False)
		doc.save()  # apply_workflow reloads from DB, so persist the details first
		doc = apply_workflow(doc, action)
		return (_("✅ {0} → {1}").format(issue, doc.status), True)
	except Exception as e:
		frappe.db.rollback(save_point="qa_action")
		clear_last_message()
		return (_("⚠️ Couldn't apply '{0}' to {1}: {2}. Saved as an update.").format(action, issue, frappe.utils.strip_html(str(e))[:200]), False)
	finally:
		frappe.flags.qa_channel = None
		frappe.set_user(original)


def status_text(issue):
	d = frappe.db.get_value(
		"QA Issue", issue,
		["name", "title", "status", "issue_code", "assigned_to", "severity", "modified", "retest_result", "uat_result"],
		as_dict=True,
	)
	if not d:
		return _("I couldn't find {0}.").format(issue)
	dev = frappe.utils.get_fullname(d.assigned_to) if d.assigned_to else _("not assigned")
	last = frappe.get_all("QA Issue Update", filters={"parent": issue}, fields=["message", "party"],
		order_by="idx desc", limit=1)
	lines = [
		f"{d.name}{' / ' + d.issue_code if d.issue_code else ''}: {d.title}",
		f"Status: {d.status}  |  Severity: {d.severity}",
		f"Developer: {dev}",
	]
	if last:
		lines.append(f"Last update ({last[0].party}): {(last[0].message or '')[:160]}")
	lines.append(issue_url(issue))
	return "\n".join(lines)


def my_tickets_text(channel, sender_key, user):
	filters = {"status": ["not in", ["UAT Accepted", "Closed", "Rejected", "Merged"]]}
	if user:
		rows = frappe.get_all("QA Issue", filters=dict(filters, reported_by=user),
			fields=["name", "title", "status"], order_by="modified desc", limit=8)
	else:
		rows = frappe.get_all("QA Issue", filters=dict(filters, channel_sender=sender_key),
			fields=["name", "title", "status"], order_by="modified desc", limit=8)
	if not rows:
		return _("You have no open tickets.")
	return "\n".join(f"• {r.name} [{r.status}] {r.title[:60]}" for r in rows)


# ---------------------------------------------------------------------------
# main entry point for chat-like channels
# ---------------------------------------------------------------------------
def handle_chat_message(
	channel,
	sender_key,
	text=None,
	images=None,
	sender_name=None,
	email=None,
	phone=None,
	message_id=None,
	reply_to_issue=None,
	project=None,
):
	"""Process one incoming chat message. Returns dict(reply=..., issue=...).
	project: project hint from the channel (e.g. a project's own Raven channel)."""
	if message_id and frappe.db.exists("QA Channel Message", {"message_id": message_id}):
		return {"reply": None, "issue": None, "duplicate": True}

	log = frappe.get_doc(
		{
			"doctype": "QA Channel Message",
			"channel": channel,
			"message_id": message_id,
			"sender": sender_key,
			"sender_name": sender_name,
			"text": text,
			"attachments": len(images or []),
			"received_on": now_datetime(),
		}
	).insert(ignore_permissions=True)

	try:
		out = _route(channel, sender_key, (text or "").strip(), images or [], sender_name, email, phone, reply_to_issue, project)
		log.db_set({"status": "Processed" if out.get("issue") or out.get("reply") else "Ignored", "issue": out.get("issue")})
		frappe.db.commit()
		return out
	except Exception:
		frappe.db.rollback()
		err = frappe.get_traceback()
		frappe.get_doc(
			{
				"doctype": "QA Channel Message",
				"channel": channel,
				"message_id": message_id,
				"sender": sender_key,
				"sender_name": sender_name,
				"text": text,
				"attachments": len(images or []),
				"received_on": now_datetime(),
				"status": "Error",
				"error": err,
			}
		).insert(ignore_permissions=True)
		frappe.log_error(title=f"QA intake failed ({channel})", message=err)
		return {"reply": _("⚠️ Sorry, something went wrong saving your message. The QA team has been alerted."), "issue": None}


def _visible(issue, user, sender_key):
	"""Can this chat sender see / act on this ticket? (vendors must not reach other vendors' tickets)"""
	from qa_tracker import access

	d = frappe.db.get_value("QA Issue", issue, ["name", "project", "vendor", "reported_by", "owner", "channel_sender"], as_dict=True)
	if not d:
		return False
	if sender_key and d.channel_sender == sender_key:
		return True
	if user:
		return access.can_access("QA Issue", d, user)
	return False


def _route(channel, sender_key, text, images, sender_name, email, phone, reply_to_issue, project=None):
	user = find_user(email=email, phone=phone, full_name=sender_name)
	low = text.lower()
	cache_key = f"qa_tracker:new:{channel}:{sender_key}"

	if low in ("help", "?", "hi", "hello", "menu") and not images:
		return {"reply": HELP_TEXT}
	if low == "new" and not images:
		_cache().set_value(cache_key, 1, expires_in_sec=3600)
		return {"reply": _("OK - your next message starts a new ticket.")}
	if low in ("my tickets", "mytickets", "list", "my issues") and not images:
		return {"reply": my_tickets_text(channel, sender_key, user)}

	m = re.match(r"^(status|track)\s+#?(ISS-\d+|\d+)\s*$", low, re.I)
	if m and not images:
		ref = m.group(2).upper()
		if ref.isdigit():
			ref = f"ISS-{int(ref):05d}"
		if not _visible(ref, user, sender_key):
			return {"reply": _("I couldn't find {0}. Send 'my tickets' to see yours.").format(ref)}
		from qa_tracker.merge import resolve

		real = resolve("QA Issue", ref)
		note = _("{0} was merged into {1}.\n").format(ref, real) if real != ref else ""
		return {"reply": note + status_text(real), "issue": real}

	ref = ISSUE_REF_RE.search(text[:40])
	issue = None
	if ref and ref.start() < 3:
		issue = ref.group(1).upper()
	elif reply_to_issue:
		issue = reply_to_issue
	if issue:
		if not frappe.db.exists("QA Issue", issue) or not _visible(issue, user, sender_key):
			return {"reply": _("I couldn't find {0}. Send 'my tickets' to see yours.").format(issue)}
		from qa_tracker.merge import resolve

		real = resolve("QA Issue", issue)
		note = ""
		if real != issue:
			note = _("ℹ️ {0} was merged into {1} - your message was added there.\n").format(issue, real)
			text = re.sub(re.escape(issue), real, text, count=1, flags=re.I)
			issue = real
		reply = handle_issue_message(issue, text, images, user=user, channel=channel, sender_name=sender_name)
		return {"reply": note + (reply or ""), "issue": issue}

	# grouping window: keep adding to the sender's latest New ticket
	window = cint(settings().group_window_minutes) or 10
	force_new = _cache().get_value(cache_key, expires=True)  # bypass request-local cache
	recent = None
	if not force_new and sender_key:
		recent = frappe.db.get_value(
			"QA Issue",
			{
				"source_channel": channel,
				"channel_sender": sender_key,
				"status": "New",
				"modified": [">=", now_datetime() - timedelta(minutes=window)],
			},
			"name",
			order_by="modified desc",
		)
	if recent:
		append_to_new_issue(recent, text, images, user=user)
		what = _("screenshot") if images and not text else _("details")
		return {"reply": _("📎 Added {0} to {1}.").format(what, recent), "issue": recent, "appended": True}

	_cache().delete_value(cache_key)
	doc = create_issue(channel, text, images, sender_key=sender_key, sender_name=sender_name,
		email=email, phone=phone, user=user, extra={"project": project} if project else None)
	reply = _("✅ Ticket {0} created: {1}\nModule: {2} | Severity: {3}\n"
		"Keep sending screenshots/details for the next {4} min and they'll be added.\n"
		"Later: reply '{0} your update' • 'status {0}' to track\n{5}").format(
		doc.name, doc.title, doc.module or "-", doc.severity, window, issue_url(doc.name))
	return {"reply": reply, "issue": doc.name, "created": True}
