"""Raven (https://github.com/The-Commit-Company/raven) - chat that runs on the same Frappe site.

* Messages / images posted in the configured Raven channel become tickets (same rules
  as WhatsApp: grouping window, #tags, "ISS-00012 pass", "status ISS-00012" ...).
* Replying (Raven "reply") to a QA Tracker bot message adds the reply to that ticket.
* The bot answers in the channel with a ticket card - Raven shows the QA Issue with its
  status and workflow buttons, so a QA lead or UAT user can act from the chat.
* Personal notifications can be sent as Raven direct messages.

Raven supports Frappe v15.111+; on sites without Raven everything here is a no-op.
"""

import frappe

from qa_tracker.compat import app_installed, doctype_exists
from qa_tracker.utils import html2text, is_image, issue_url, settings


def enabled():
	s = settings()
	return bool(s.raven_enabled and app_installed("raven") and doctype_exists("Raven Message"))


# ---------------------------------------------------------------------------
# inbound: doc_events on "Raven Message"
# ---------------------------------------------------------------------------
def on_raven_message(doc, method=None):
	"""after_insert hook on Raven Message (registered in hooks.py)."""
	if doc.get("is_bot_message") or frappe.flags.qa_raven_sending:
		return
	if not enabled():
		return
	s = settings()
	channel = doc.get("channel_id")
	reply_to_issue = None
	linked = doc.get("linked_message") if doc.get("is_reply") else None
	if linked:
		reply_to_issue = frappe.db.get_value("QA Channel Message", {"message_id": f"out:raven:{linked}"}, "issue")
	thread_issue = _thread_issue(channel)
	project = frappe.db.get_value("QA Project", {"raven_channel": channel}, "name") if channel else None
	if channel != (s.raven_channel or "").strip() and not project and not reply_to_issue and not thread_issue:
		return
	# defer to after commit so the file / message is fully saved
	name = doc.name
	frappe.enqueue(
		"qa_tracker.channels.raven.process_message",
		message=name,
		reply_to_issue=reply_to_issue or thread_issue,
		project=project,
		enqueue_after_commit=True,
		now=frappe.flags.in_test or frappe.conf.get("qa_tracker_sync_raven", 0),
	)


def _thread_issue(channel):
	"""A Raven thread started from a bot ticket message belongs to that ticket."""
	if not channel:
		return None
	try:
		if frappe.db.get_value("Raven Channel", channel, "is_thread"):
			# thread channels are named after the message that started them
			return frappe.db.get_value("QA Channel Message", {"message_id": f"out:raven:{channel}"}, "issue")
	except Exception:
		return None
	return None


def process_message(message, reply_to_issue=None, project=None):
	from qa_tracker import intake

	doc = frappe.get_doc("Raven Message", message)
	user = doc.owner
	text = html2text(doc.get("text") or "").strip()
	images = []
	if doc.get("message_type") == "Image" or (doc.get("file") and is_image(doc.file)):
		content = _read_file(doc.file)
		if content:
			images.append((doc.file.split("/")[-1].split("?")[0], content))
	elif doc.get("message_type") == "File" and not text:
		return  # non-image files are ignored

	original = frappe.session.user
	frappe.set_user("Administrator")
	try:
		full_name = frappe.utils.get_fullname(user)
		email = frappe.db.get_value("User", user, "email")
		out = intake.handle_chat_message(
			"Raven",
			user,
			text=text,
			images=images,
			sender_name=full_name,
			email=email,
			message_id=f"raven:{doc.name}",
			reply_to_issue=reply_to_issue,
			project=project,
		)
		if out.get("reply") and not out.get("duplicate"):
			reply(doc.channel_id, out["reply"], issue=out.get("issue"), reply_to=doc.name,
				card=bool(out.get("created")))
	finally:
		frappe.set_user(original)


def _read_file(file_url):
	try:
		f = frappe.get_doc("File", {"file_url": file_url})
		return f.get_content()
	except Exception:
		frappe.log_error(title="QA Tracker: could not read Raven image", message=frappe.get_traceback())
		return None


# ---------------------------------------------------------------------------
# outbound
# ---------------------------------------------------------------------------
def get_bot():
	"""Return the Raven Bot used by QA Tracker, creating it when missing."""
	s = settings()
	name = (s.raven_bot or "QA Tracker").strip()
	if frappe.db.exists("Raven Bot", name):
		return frappe.get_doc("Raven Bot", name)
	bot = frappe.get_doc(
		{
			"doctype": "Raven Bot",
			"bot_name": name,
			"description": "Creates and tracks QA tickets from chat messages and screenshots.",
			"module": "QA Tracker",
		}
	)
	bot.insert(ignore_permissions=True)
	return bot


def reply(channel_id, text, issue=None, reply_to=None, card=False):
	"""Post a bot message (optionally as a reply, optionally with a ticket card)."""
	if not (enabled() and channel_id):
		return None
	bot = get_bot()
	html = "<p>" + frappe.utils.escape_html(text).replace("\n", "<br>") + "</p>"
	values = {
		"doctype": "Raven Message",
		"channel_id": channel_id,
		"text": html,
		"message_type": "Text",
		"is_bot_message": 1,
		"bot": bot.raven_user,
	}
	if card and issue:
		values.update({"link_doctype": "QA Issue", "link_document": issue})
	if reply_to:
		values.update({"is_reply": 1, "linked_message": reply_to})
	frappe.flags.qa_raven_sending = True
	try:
		msg = frappe.get_doc(values)
		msg.insert(ignore_permissions=True)
	finally:
		frappe.flags.qa_raven_sending = False
	if issue:
		_remember(msg.name, issue, text)
	return msg.name


def _remember(message_name, issue, text):
	frappe.get_doc(
		{
			"doctype": "QA Channel Message",
			"channel": "Raven",
			"message_id": f"out:raven:{message_name}",
			"sender": "bot",
			"issue": issue,
			"status": "Processed",
			"text": (text or "")[:500],
			"received_on": frappe.utils.now_datetime(),
		}
	).insert(ignore_permissions=True)


def post_status(doc, headline, text):
	s = settings()
	chan = (frappe.db.get_value("QA Project", doc.project, "raven_channel") if doc.get("project") else None) or s.raven_channel
	if not (enabled() and s.raven_post_status and chan):
		return
	if doc.source_channel == "Raven" and doc.status == "New":
		return  # the reporter already got a ticket card in the channel
	reply(chan, f"{headline}\n{text or ''}\n{issue_url(doc.name)}", issue=doc.name, card=True)


def send_dm(user, text, issue=None, doctype="QA Issue"):
	"""Direct message a user from the QA Tracker bot (only if they are a Raven user)."""
	s = settings()
	if not (enabled() and s.raven_dm_notifications and user):
		return
	if not frappe.db.exists("Raven User", {"user": user}):
		return
	bot = get_bot()
	channel = bot.create_direct_message_channel(user)
	frappe.flags.qa_raven_sending = True
	try:
		name = bot.send_message(channel_id=channel, text="<p>" + frappe.utils.escape_html(text).replace("\n", "<br>") + "</p>",
			link_doctype=doctype if issue else None, link_document=issue)
	finally:
		frappe.flags.qa_raven_sending = False
	if issue and name and doctype == "QA Issue":
		_remember(name, issue, text)
	return name


@frappe.whitelist()
def list_channels():
	"""For QA Settings: channels the admin can pick."""
	frappe.only_for(("System Manager", "QA Lead"))
	if not (app_installed("raven") and doctype_exists("Raven Channel")):
		frappe.throw("Raven is not installed on this site. Install it with: bench get-app raven && bench --site <site> install-app raven")
	fields = ["name", "channel_name", "type"]
	if frappe.get_meta("Raven Channel").has_field("workspace"):
		fields.append("workspace")
	return frappe.get_all(
		"Raven Channel",
		filters={"is_direct_message": 0, "is_thread": 0, "is_archived": 0},
		fields=fields,
		order_by="channel_name asc",
	)


@frappe.whitelist()
def setup_bot():
	frappe.only_for(("System Manager", "QA Lead"))
	if not (app_installed("raven") and doctype_exists("Raven Bot")):
		frappe.throw("Raven is not installed on this site.")
	bot = get_bot()
	return {"bot": bot.name, "raven_user": bot.raven_user}
