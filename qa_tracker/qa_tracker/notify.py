"""Outbound notifications: email, WhatsApp, Teams and in-app.

Who hears about what
* New ticket                -> sender gets an acknowledgement on the channel they used
* Assigned / Reopened       -> assigned developer
* Ready for Retest/Answered -> reporter (tester)
* Other status changes      -> reporter
* Update by developer       -> reporter;   update by tester/UAT -> developer;
  update by QA lead         -> both
* Every status change       -> Teams channel (if enabled)
"""

import frappe
from frappe import _
from frappe.utils import escape_html

from qa_tracker.utils import issue_url, portal_url, settings, user_contact

TO_DEVELOPER = {"Assigned", "Reopened"}
TO_REPORTER = {"Triaged", "Ready for Retest", "Answered", "Retest Passed", "Confirmed", "In UAT",
	"UAT Accepted", "Closed", "Rejected", "Deferred", "Reopened"}


def _safe(fn, *args, **kwargs):
	try:
		return fn(*args, **kwargs)
	except Exception:
		frappe.log_error(title="QA Tracker notification failed", message=frappe.get_traceback())


def _has_outgoing_email():
	if not hasattr(frappe.local, "qa_has_outgoing"):
		frappe.local.qa_has_outgoing = bool(frappe.db.exists("Email Account", {"enable_outgoing": 1}))
	return frappe.local.qa_has_outgoing


def _reporter(doc):
	"""Return dict(user, email, phone, name, channel) for the reporter."""
	c = user_contact(doc.reported_by)
	return frappe._dict(
		user=doc.reported_by,
		email=doc.raised_by_email or c.get("email"),
		phone=doc.raised_by_phone or (c.get("mobile_no") if doc.source_channel == "WhatsApp" else None),
		name=doc.reporter_name or c.get("full_name"),
		channel=doc.source_channel,
	)


def _developer(doc):
	c = user_contact(doc.assigned_to)
	return frappe._dict(user=doc.assigned_to, email=c.get("email"), phone=None, name=c.get("full_name"), channel="Web")


def send_to(person, doc, subject, text):
	"""Deliver one message to one person over the channels that make sense."""
	if not person:
		return
	s = settings()
	link = issue_url(doc.name)
	if person.user:
		_safe(
			lambda: frappe.get_doc(
				{
					"doctype": "Notification Log",
					"subject": subject,
					"email_content": escape_html(text),
					"for_user": person.user,
					"type": "Alert",
					"document_type": "QA Issue",
					"document_name": doc.name,
				}
			).insert(ignore_permissions=True)
		)
	if s.notify_email and person.email and _has_outgoing_email():
		_safe(
			frappe.sendmail,
			recipients=[person.email],
			subject=f"[{doc.name}] {subject}",
			message=f"<p>{escape_html(text).replace(chr(10), '<br>')}</p><p><a href='{link}'>{_('Open ticket')}</a></p>"
			f"<p style='color:#888'>{_('Reply to this email to add an update. Start your reply with pass / fail / fixed / accept / reject to record a result.')}</p>",
			reference_doctype="QA Issue",
			reference_name=doc.name,
		)
	if s.notify_whatsapp and s.whatsapp_enabled and person.phone and person.channel == "WhatsApp":
		from qa_tracker.channels import whatsapp

		_safe(whatsapp.send_text, person.phone, f"{subject}\n{text}\n{link}", issue=doc.name)
	if person.user:
		from qa_tracker.channels import raven, telegram

		portal = portal_url(doc.name)
		if s.raven_enabled:
			_safe(raven.send_dm, person.user, f"{subject}\n{text}", issue=doc.name)
		if s.telegram_enabled:
			_safe(telegram.notify_user, person.user, f"{subject}\n{text}\n{portal}", issue=doc.name)


def post_teams(doc, headline, text):
	"""Post to team channels: Teams, Google Chat and Raven."""
	s = settings()
	proj = frappe.db.get_value("QA Project", doc.project, ["teams_webhook_url", "gchat_webhook_url"], as_dict=True) if doc.get("project") else None
	if s.notify_teams and (s.teams_notify_webhook_url or (proj and proj.teams_webhook_url)):
		from qa_tracker.channels import teams

		_safe(teams.post_card, doc, headline, text)
	if (s.gchat_webhook_url or "").strip() or (proj and (proj.gchat_webhook_url or "").strip()):
		_safe(post_google_chat, doc, headline, text)
	if s.raven_enabled:
		from qa_tracker.channels import raven

		_safe(raven.post_status, doc, headline, text)


def post_google_chat(doc, headline, text):
	import requests

	url = ((frappe.db.get_value("QA Project", doc.project, "gchat_webhook_url") if doc.get("project") else None)
		or settings().gchat_webhook_url or "").strip()
	body = {
		"cardsV2": [
			{
				"cardId": doc.name,
				"card": {
					"header": {"title": headline, "subtitle": f"{doc.status} · {doc.severity or ''} · {doc.module or ''}"},
					"sections": [
						{
							"widgets": [
								{"textParagraph": {"text": frappe.utils.escape_html(text or doc.title)}},
								{"buttonList": {"buttons": [{"text": "Open ticket", "onClick": {"openLink": {"url": issue_url(doc.name)}}}]}},
							]
						}
					],
				},
			}
		],
		"text": f"{headline}: {doc.title}",
	}
	requests.post(url, json=body, timeout=15).raise_for_status()


def on_new_issue(name):
	doc = frappe.get_doc("QA Issue", name)
	if doc.source_channel == "Email" and doc.raised_by_email:
		# chat channels reply inline; email gets an acknowledgement mail
		send_to(
			frappe._dict(user=None, email=doc.raised_by_email, phone=None, name=doc.reporter_name, channel="Email"),
			doc,
			_("Ticket created: {0}").format(doc.title),
			_("Thanks - your report was logged as {0}.\nModule: {1}  Severity: {2}\nReply to this email to add more details or screenshots.").format(
				doc.name, doc.module or "-", doc.severity),
		)
	post_teams(doc, _("New ticket {0}").format(doc.name), doc.title)


def on_status_change(name, old, new):
	doc = frappe.get_doc("QA Issue", name)
	who = frappe.utils.get_fullname(frappe.session.user)
	text = _("{0}: {1} → {2} (by {3})").format(doc.name, old, new, who)
	if new == "Ready for Retest":
		text += "\n" + _("Fix: {0}").format(doc.resolution or "-") + "\n" + _("Please retest and reply '{0} pass' or '{0} fail <notes>'.").format(doc.name)
	elif new == "Answered":
		text += "\n" + _("Answer: {0}").format(doc.resolution or "-")
	elif new == "In UAT":
		text += "\n" + _("Please verify in UAT and reply '{0} accept' or '{0} reject <notes>'.").format(doc.name)
	elif new == "Reopened":
		note = doc.uat_notes if old == "In UAT" else doc.retest_notes
		if note:
			text += "\n" + _("Notes: {0}").format(note)
	subject = f"{doc.title} - {new}"
	sent = set()
	if new in TO_DEVELOPER and doc.assigned_to:
		send_to(_developer(doc), doc, subject, text)
		sent.add(doc.assigned_to)
	if new in TO_REPORTER:
		rep = _reporter(doc)
		if not rep.user or rep.user not in sent:
			send_to(rep, doc, subject, text)
	post_teams(doc, f"{doc.name} → {new}", doc.title)


def on_update_posted(issue, row):
	"""Notify the other party when someone adds an update."""
	doc = frappe.get_doc("QA Issue", issue)
	author = row.sender_name or row.posted_by or row.party
	subject = _("Update on {0}: {1}").format(doc.name, doc.title)
	text = f"{author} ({row.party}, {row.channel}): {row.message or ''}"
	targets = []
	if row.party in ("Tester", "UAT"):
		targets.append(_developer(doc) if doc.assigned_to else None)
	elif row.party == "Developer":
		targets.append(_reporter(doc))
	elif row.party == "QA Lead":
		targets += [_reporter(doc), _developer(doc) if doc.assigned_to else None]
	for person in targets:
		if not person:
			continue
		if person.user and person.user == row.posted_by:
			continue
		# don't echo a WhatsApp message back to the person who just sent it
		if row.channel == "WhatsApp" and person.channel == "WhatsApp" and row.party in ("Tester", "UAT"):
			continue
		send_to(person, doc, subject, text)


def daily_digest():
	"""Morning email: QA leads get the overview, developers their queue, testers their retests."""
	if not settings().notify_email or not _has_outgoing_email():
		return
	open_states = ["New", "Triaged", "Assigned", "In Progress", "Reopened", "Ready for Retest",
		"Retest Passed", "Confirmed", "In UAT", "Answered"]
	counts = frappe.get_all("QA Issue", filters={"status": ["in", open_states]}, fields=["status", "count(name) as n"],
		group_by="status")
	if not counts:
		return
	blockers = frappe.get_all("QA Issue", filters={"status": ["in", open_states], "severity": "Blocker"},
		fields=["name", "title", "status", "assigned_to"], limit=30)
	summary = "".join(f"<li>{escape_html(c.status)}: <b>{c.n}</b></li>" for c in counts)
	block = "".join(f"<li><a href='{issue_url(b.name)}'>{b.name}</a> [{b.status}] {escape_html(b.title)}</li>" for b in blockers)
	leads = [u for u in frappe.get_all("Has Role", filters={"role": "QA Lead", "parenttype": "User"}, pluck="parent")
		if frappe.db.get_value("User", u, "enabled") and u not in ("Administrator",)]
	for u in leads:
		_safe(frappe.sendmail, recipients=[u], subject=_("QA Tracker daily summary"),
			message=f"<h3>{_('Open issues')}</h3><ul>{summary}</ul><h3>{_('Open blockers')}</h3><ul>{block or '<li>-</li>'}</ul>")
	for field, states, title in (
		("assigned_to", ["Assigned", "In Progress", "Reopened"], _("Your open issues")),
		("reported_by", ["Ready for Retest", "Answered"], _("Waiting for your retest / confirmation")),
	):
		rows = frappe.get_all("QA Issue", filters={"status": ["in", states], field: ["is", "set"]},
			fields=["name", "title", "status", field], order_by="severity asc, modified asc")
		by_user = {}
		for r in rows:
			by_user.setdefault(r.get(field), []).append(r)
		for u, items in by_user.items():
			body = "".join(f"<li><a href='{issue_url(i.name)}'>{i.name}</a> [{i.status}] {escape_html(i.title)}</li>" for i in items)
			_safe(frappe.sendmail, recipients=[u], subject=f"QA Tracker: {title} ({len(items)})", message=f"<ul>{body}</ul>")


def overdue_digest():
	"""Daily: tickets past their SLA target date, sent to the project's QA leads and to that vendor's staff."""
	if not settings().notify_email or not _has_outgoing_email():
		return
	rows = frappe.get_all(
		"QA Issue",
		filters={"target_date": ["<", frappe.utils.today()], "status": ["in", ["Assigned", "In Progress", "Reopened", "Triaged"]]},
		fields=["name", "title", "status", "severity", "project", "vendor", "assigned_to", "target_date"],
		order_by="target_date asc",
		limit=500,
	)
	groups = {}
	for r in rows:
		groups.setdefault((r.project, r.vendor), []).append(r)
	for (project, vendor), items in groups.items():
		from qa_tracker.access import members_for

		members = [m for m in members_for(project) if m.is_active] if project else []
		to = {m.user for m in members if m.project_role == "QA Lead" and not m.vendor}
		to |= {m.user for m in members if vendor and m.vendor == vendor}
		to |= {i.assigned_to for i in items if i.assigned_to}
		to.discard(None)
		if not to:
			continue
		body = "".join(
			f"<li><a href='{issue_url(i.name)}'>{i.name}</a> [{i.severity} · {i.status}] {escape_html(i.title)} "
			f"- due {frappe.utils.formatdate(i.target_date)}, {frappe.utils.date_diff(frappe.utils.today(), i.target_date)} day(s) late</li>"
			for i in items)
		title = _("{0} overdue ticket(s)").format(len(items))
		label = " · ".join(x for x in (project, vendor) if x)
		_safe(frappe.sendmail, recipients=sorted(to), subject=f"QA Tracker: {title} - {label}",
			message=f"<p>{_('These tickets are past their fix target date (vendor SLA).')}</p><ul>{body}</ul>")
