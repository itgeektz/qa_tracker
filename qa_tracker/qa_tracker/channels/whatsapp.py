"""WhatsApp intake via Meta's WhatsApp Business Cloud API.

Webhook URL to register in the Meta developer console (WhatsApp > Configuration):
    https://<your-site>/api/method/qa_tracker.channels.whatsapp.webhook
Subscribe to the "messages" field. Use the Verify Token from QA Settings.

Testers message the hospital QA WhatsApp number. Text, images (with or without a
caption) and image documents are supported. Replying (swipe-reply) to a bot message
about a ticket adds the reply to that ticket.
"""

import hashlib
import hmac
import json
import mimetypes

import frappe

from qa_tracker.compat import request_data
import requests
from werkzeug.wrappers import Response

from qa_tracker.utils import settings

GRAPH = "https://graph.facebook.com"


def _cfg():
	s = settings()
	return frappe._dict(
		enabled=s.whatsapp_enabled,
		phone_id=s.whatsapp_phone_number_id,
		token=s.get_password("whatsapp_access_token", raise_exception=False) if s.whatsapp_access_token else None,
		verify=s.whatsapp_verify_token,
		secret=s.get_password("whatsapp_app_secret", raise_exception=False) if s.whatsapp_app_secret else None,
		version=s.whatsapp_api_version or "v21.0",
		template=s.whatsapp_template,
	)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def webhook(**kwargs):
	cfg = _cfg()
	if frappe.request.method == "GET":
		args = frappe.request.args
		if args.get("hub.mode") == "subscribe" and cfg.verify and args.get("hub.verify_token") == cfg.verify:
			return Response(args.get("hub.challenge", ""), status=200, mimetype="text/plain")
		return Response("forbidden", status=403)

	raw = request_data()
	if cfg.secret:
		sig = frappe.get_request_header("X-Hub-Signature-256") or ""
		expected = "sha256=" + hmac.new(cfg.secret.encode(), raw, hashlib.sha256).hexdigest()
		if not hmac.compare_digest(sig, expected):
			return Response("bad signature", status=401)
	if not cfg.enabled:
		return Response("disabled", status=200)

	payload = json.loads(raw or b"{}")
	frappe.set_user("Administrator")
	for entry in payload.get("entry", []):
		for change in entry.get("changes", []):
			value = change.get("value", {})
			names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
			for msg in value.get("messages", []):
				try:
					process_message(msg, names.get(msg.get("from")), cfg)
				except Exception:
					frappe.db.rollback()
					frappe.log_error(title="QA Tracker WhatsApp message failed", message=frappe.get_traceback())
	frappe.db.commit()
	return Response("ok", status=200)


def process_message(msg, sender_name, cfg):
	from qa_tracker import intake

	sender = msg.get("from")
	mtype = msg.get("type")
	text, images = None, []
	if mtype == "text":
		text = (msg.get("text") or {}).get("body")
	elif mtype in ("image", "document", "sticker"):
		media = msg.get(mtype) or {}
		text = media.get("caption")
		mime = media.get("mime_type") or ""
		if mime.startswith("image/"):
			content = download_media(media.get("id"), cfg)
			if content:
				ext = mimetypes.guess_extension(mime.split(";")[0]) or ".jpg"
				images.append((media.get("filename") or f"whatsapp_{msg.get('id', '')[-8:]}{ext}", content))
		elif mtype == "document" and not text:
			text = f"(document received: {media.get('filename', 'file')} - only images are stored)"
	elif mtype == "button":
		text = (msg.get("button") or {}).get("text")
	elif mtype == "interactive":
		inter = msg.get("interactive") or {}
		text = (inter.get("button_reply") or inter.get("list_reply") or {}).get("title")
	else:
		send_text(sender, "Sorry, I can only read text and screenshots.")
		return

	reply_to_issue = None
	ctx_id = (msg.get("context") or {}).get("id")
	if ctx_id:
		reply_to_issue = frappe.db.get_value("QA Channel Message", {"message_id": f"out:{ctx_id}"}, "issue")

	out = intake.handle_chat_message(
		"WhatsApp",
		sender,
		text=text,
		images=images,
		sender_name=sender_name,
		phone=sender,
		message_id=msg.get("id"),
		reply_to_issue=reply_to_issue,
	)
	if out.get("reply") and not out.get("duplicate"):
		try:
			send_text(sender, out["reply"], issue=out.get("issue"))
		except Exception:
			# never fail the webhook because a reply couldn't be sent (Meta would retry)
			frappe.log_error(title="QA Tracker WhatsApp reply failed", message=frappe.get_traceback())


def download_media(media_id, cfg):
	if not (media_id and cfg.token):
		return None
	headers = {"Authorization": f"Bearer {cfg.token}"}
	meta = requests.get(f"{GRAPH}/{cfg.version}/{media_id}", headers=headers, timeout=20)
	meta.raise_for_status()
	url = meta.json().get("url")
	r = requests.get(url, headers=headers, timeout=60)
	r.raise_for_status()
	return r.content


def send_text(to, body, issue=None):
	"""Send a text reply. Falls back to the configured template when outside the 24h window."""
	cfg = _cfg()
	if not (cfg.enabled and cfg.token and cfg.phone_id and to):
		return None
	url = f"{GRAPH}/{cfg.version}/{cfg.phone_id}/messages"
	headers = {"Authorization": f"Bearer {cfg.token}", "Content-Type": "application/json"}
	payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body[:4000], "preview_url": False}}
	r = requests.post(url, headers=headers, json=payload, timeout=20)
	if r.status_code >= 400 and cfg.template:
		err = (r.json().get("error") or {}) if r.headers.get("content-type", "").startswith("application/json") else {}
		if err.get("code") in (131047, 131026, 470):
			payload = {
				"messaging_product": "whatsapp",
				"to": to,
				"type": "template",
				"template": {
					"name": cfg.template,
					"language": {"code": "en"},
					"components": [{"type": "body", "parameters": [{"type": "text", "text": body[:900]}]}],
				},
			}
			r = requests.post(url, headers=headers, json=payload, timeout=20)
	r.raise_for_status()
	out_id = ((r.json().get("messages") or [{}])[0]).get("id")
	if out_id and issue:
		# remember which ticket this bot message was about, so swipe-replies map back
		frappe.get_doc(
			{
				"doctype": "QA Channel Message",
				"channel": "WhatsApp",
				"message_id": f"out:{out_id}",
				"sender": "bot",
				"issue": issue,
				"status": "Processed",
				"text": body[:500],
				"received_on": frappe.utils.now_datetime(),
			}
		).insert(ignore_permissions=True)
	return out_id
