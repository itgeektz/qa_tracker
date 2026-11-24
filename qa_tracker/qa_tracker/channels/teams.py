"""Microsoft Teams.

Inbound (Teams -> tickets), three options - see README:
1. "Share to Outlook" on any Teams message, sent to the QA intake mailbox
   -> handled by the email intake (text + screenshots, no setup).
2. Outgoing Webhook "@QA Tracker <message>" in a channel -> this module's
   `outgoing_webhook`. Replies in the thread with the ticket number.
3. Power Automate flow -> `qa_tracker.api.intake` (generic JSON API).

Outbound (tickets -> Teams): status changes posted as Adaptive Cards to a Teams
Workflows webhook URL ("Post to a channel when a webhook request is received").
"""

import base64
import hashlib
import hmac
import json
import re

import frappe

from qa_tracker.compat import request_data
import requests
from qa_tracker.utils import html2text
from werkzeug.wrappers import Response

from qa_tracker.utils import issue_url, settings


WEBHOOK_PATH = "/api/method/qa_tracker.channels.teams.outgoing_webhook"


def _signature_ok():
	s = settings()
	secret = s.get_password("teams_outgoing_secret", raise_exception=False) if s.teams_outgoing_secret else None
	if not (s.teams_enabled and secret):
		return False
	raw = request_data()
	auth = frappe.get_request_header("Authorization") or ""
	try:
		expected = base64.b64encode(hmac.new(base64.b64decode(secret), raw, hashlib.sha256).digest()).decode()
	except Exception:
		return False
	return hmac.compare_digest(auth, f"HMAC {expected}")


def auth_hook():
	"""Frappe auth hook: accept a correctly signed Teams request to our endpoint."""
	req = getattr(frappe.local, "request", None)
	if not req or req.path.rstrip("/") != WEBHOOK_PATH:
		return
	if not (frappe.get_request_header("Authorization") or "").startswith("HMAC "):
		return
	if _signature_ok():
		frappe.set_user("Administrator")


@frappe.whitelist(allow_guest=True, methods=["POST"])
def outgoing_webhook(**kwargs):
	if not _signature_ok():
		return _reply("Unauthorized", status=401)
	raw = request_data()

	activity = json.loads(raw or b"{}")
	sender = activity.get("from") or {}
	html = activity.get("text") or ""
	# drop the @mention of the webhook itself
	html = re.sub(r"<at>.*?</at>", "", html, flags=re.S)
	text = html2text(html).strip()

	images, failed = [], 0
	sources = re.findall(r"<img[^>]+src=\"([^\"]+)\"", activity.get("text") or "")
	for att in activity.get("attachments") or []:
		if (att.get("contentType") or "").startswith("image/") and att.get("contentUrl"):
			sources.append(att["contentUrl"])
		elif att.get("contentType") == "text/html":
			sources += re.findall(r"<img[^>]+src=\"([^\"]+)\"", att.get("content") or "")
	for i, src in enumerate(dict.fromkeys(sources)):
		try:
			r = requests.get(src, timeout=15)
			if r.ok and r.headers.get("content-type", "").startswith("image/"):
				ext = r.headers["content-type"].split("/")[-1].split(";")[0]
				images.append((f"teams_{activity.get('id', 'msg')[-8:]}_{i}.{ext}", r.content))
			else:
				failed += 1
		except Exception:
			failed += 1

	from qa_tracker import intake

	frappe.set_user("Administrator")
	sender_id = sender.get("aadObjectId") or sender.get("id")
	from qa_tracker.utils import find_user

	user = find_user(channel="Teams", external_id=sender_id)
	out = intake.handle_chat_message(
		"Teams",
		sender_id,
		text=text,
		images=images,
		sender_name=sender.get("name"),
		email=frappe.db.get_value("User", user, "email") if user else None,
		message_id=activity.get("id"),
	)
	frappe.db.commit()
	reply = out.get("reply") or "OK"
	if failed:
		reply += (
			f"\n⚠️ Teams didn't let me download {failed} pasted screenshot(s). "
			"Use '… > Share to Outlook' to the QA mailbox, or add them on the ticket page."
		)
	return _reply(reply)


def _reply(text, status=200):
	body = json.dumps({"type": "message", "text": text.replace("\n", "<br>")})
	return Response(body, status=status, mimetype="application/json")


def post_card(doc, headline, text):
	url = ((frappe.db.get_value("QA Project", doc.project, "teams_webhook_url") if doc.get("project") else None)
		or settings().teams_notify_webhook_url or "").strip()
	if not url:
		return
	facts = [
		{"title": "Status", "value": doc.status},
		{"title": "Severity", "value": doc.severity or "-"},
		{"title": "Site / Module", "value": f"{doc.site or '-'} / {doc.module or '-'}"},
		{"title": "Developer", "value": frappe.utils.get_fullname(doc.assigned_to) if doc.assigned_to else "-"},
		{"title": "Reporter", "value": doc.reporter_name or (frappe.utils.get_fullname(doc.reported_by) if doc.reported_by else "-")},
	]
	card = {
		"type": "AdaptiveCard",
		"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
		"version": "1.3",
		"body": [
			{"type": "TextBlock", "text": headline, "weight": "Bolder", "size": "Medium", "wrap": True},
			{"type": "TextBlock", "text": text or "", "wrap": True},
			{"type": "FactSet", "facts": facts},
		],
		"actions": [{"type": "Action.OpenUrl", "title": "Open ticket", "url": issue_url(doc.name)}],
	}
	payload = {
		"type": "message",
		"attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}],
	}
	requests.post(url, json=payload, timeout=15).raise_for_status()
