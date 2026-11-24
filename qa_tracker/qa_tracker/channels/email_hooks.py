"""Email intake.

Set up an Email Account (IMAP/POP) with "Enable Incoming" and "Append To = QA Issue".
Frappe then creates one QA Issue per new email thread (subject -> title, sender ->
reporter email) and links replies to the same issue. These hooks:

* fill the description from the first email and read #tags from the subject/body
* copy image attachments into the Screenshots table
* turn replies into Updates, including commands such as "pass", "fail", "fixed"
* add images attached to replies as update screenshots
"""

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from qa_tracker.utils import add_screenshot, append_update, find_user, html2text, is_image, link_file_to_issue, refresh_issue_code


def _strip_reply(text):
	try:
		from email_reply_parser import EmailReplyParser

		return EmailReplyParser.parse_reply(text or "").strip()
	except Exception:
		return (text or "").strip()


def on_communication(doc, method=None):
	if (
		doc.communication_type != "Communication"
		or doc.sent_or_received != "Received"
		or doc.reference_doctype != "QA Issue"
		or not doc.reference_name
	):
		return
	if not (doc.content or "").strip():
		return  # body not saved yet
	if frappe.db.exists("QA Issue Update", {"parent": doc.reference_name, "source_message": doc.name}):
		return  # this reply was already processed
	from qa_tracker import intake

	issue = frappe.get_doc("QA Issue", doc.reference_name)
	if issue.origin_communication == doc.name:
		return
	sender = (doc.sender or "").strip()
	user = find_user(email=sender)
	recent = get_datetime(issue.creation) >= add_to_date(now_datetime(), minutes=-10)

	if not issue.origin_communication and not issue.description and recent:
		# first email of the thread -> this is the ticket itself
		subject_clean, tags = intake.parse_tags(doc.subject or issue.title)
		body_text = _strip_reply(html2text(doc.content or ""))
		body_clean, body_tags = intake.parse_tags(body_text)
		for k, v in body_tags.items():
			tags.setdefault(k, v)
		values = {
			"origin_communication": doc.name,
			"source_channel": "Email",
			"channel_sender": sender,
			"title": (subject_clean or issue.title)[:240],
			"description": intake.text_to_html(body_clean),
			"reported_by": issue.reported_by or user,
			"issue_type": tags.get("issue_type") or intake.guess_type(f"{subject_clean}\n{body_clean}"),
		}
		for k in ("site", "module", "severity", "found_in_phase"):
			if tags.get(k):
				values[k] = tags[k]
		if not tags.get("module"):
			guessed = intake.guess_module(f"{subject_clean} {body_clean}")
			if guessed:
				values["module"] = guessed
		frappe.db.set_value("QA Issue", issue.name, values)
		# issue code may now be computable
		refresh_issue_code(issue.name)
		return

	# a reply on an existing ticket -> update (and maybe a command)
	text = _strip_reply(html2text(doc.content or ""))
	if not text.strip():
		return
	frappe.flags.qa_source_message = doc.name
	try:
		intake.handle_issue_message(issue.name, text, None, user=user, channel="Email", sender_name=doc.sender_full_name or sender)
	finally:
		frappe.flags.qa_source_message = None


def on_file(doc, method=None):
	if frappe.flags.qa_skip_file_hook or not is_image(doc.file_name or doc.file_url):
		return
	if doc.attached_to_doctype == "Communication" and doc.attached_to_name:
		comm = frappe.db.get_value(
			"Communication",
			doc.attached_to_name,
			["reference_doctype", "reference_name", "sent_or_received", "sender", "sender_full_name"],
			as_dict=True,
		)
		if not comm or comm.reference_doctype != "QA Issue" or comm.sent_or_received != "Received":
			return
		issue = comm.reference_name
		link_file_to_issue(doc.file_url, issue, doc.file_name)
		origin = frappe.db.get_value("QA Issue", issue, "origin_communication")
		user = find_user(email=comm.sender)
		if origin == doc.attached_to_name or not origin:
			add_screenshot(issue, doc.file_url, caption=doc.file_name, user=user or "Guest")
		else:
			append_update(issue, "Screenshot added", channel="Email", screenshot=doc.file_url, user=user or "Guest",
				sender_name=comm.sender_full_name or comm.sender, notify=False)
	elif doc.attached_to_doctype == "QA Issue" and doc.attached_to_name and not getattr(frappe.local, "request", None):
		# images attached to the issue by background jobs (email pull). Uploads made in
		# the browser are left alone - the form saves its own screenshot rows.
		if not frappe.db.exists("QA Issue", doc.attached_to_name):
			return
		for field in ("screenshots", "retest_screenshots", "uat_screenshots"):
			if frappe.db.exists("QA Screenshot", {"parent": doc.attached_to_name, "image": doc.file_url}):
				return
		if frappe.db.exists("QA Issue Update", {"parent": doc.attached_to_name, "screenshot": doc.file_url}):
			return
		add_screenshot(doc.attached_to_name, doc.file_url, caption=doc.file_name)
