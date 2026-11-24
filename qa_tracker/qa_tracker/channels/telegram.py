"""Telegram bot (free).

Setup: create a bot with @BotFather, paste the token and any secret into QA Settings,
then click "Register Telegram Webhook". Webhook URL:
    https://<site>/api/method/qa_tracker.channels.telegram.webhook

Users start the bot, tap "Share my phone number" once - that links their Telegram
account to their QA Tracker user (matched on the mobile number in their profile).
Photos, image files, captions, text and replies are supported.
"""

import hmac
import json

import frappe
import requests
from werkzeug.wrappers import Response

from qa_tracker.compat import request_data
from qa_tracker.utils import digits, find_user, settings

API = "https://api.telegram.org"


def _token():
	s = settings()
	return s.get_password("telegram_bot_token", raise_exception=False) if s.telegram_bot_token else None


def call(method, **payload):
	token = _token()
	if not token:
		return None
	r = requests.post(f"{API}/bot{token}/{method}", json=payload, timeout=30)
	data = r.json() if r.content else {}
	if not data.get("ok"):
		raise Exception(f"Telegram {method} failed: {data.get('description') or r.status_code}")
	return data.get("result")


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook(**kwargs):
	s = settings()
	secret = (s.telegram_secret or "").strip()
	given = frappe.get_request_header("X-Telegram-Bot-Api-Secret-Token") or ""
	if not (s.telegram_enabled and secret and hmac.compare_digest(given, secret)):
		return Response("forbidden", status=403)
	update = json.loads(request_data() or b"{}")
	msg = update.get("message") or update.get("edited_message")
	if not msg:
		return Response("ok", status=200)
	frappe.set_user("Administrator")
	try:
		process_message(msg)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="QA Tracker Telegram message failed", message=frappe.get_traceback())
	return Response("ok", status=200)


def _link(chat_id):
	return frappe.db.get_value("QA Channel Link", {"channel": "Telegram", "external_id": str(chat_id)},
		["name", "user", "display_name"], as_dict=True)


def process_message(msg):
	from qa_tracker import intake

	chat = msg.get("chat") or {}
	if chat.get("type") not in (None, "private"):
		return  # only 1:1 chats with the bot
	chat_id = str(chat.get("id"))
	sender = msg.get("from") or {}
	name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or sender.get("username")
	link = _link(chat_id)

	# contact sharing -> link account
	if msg.get("contact"):
		contact = msg["contact"]
		if str(contact.get("user_id")) != str(sender.get("id")):
			send(chat_id, "Please share your own number using the button.")
			return
		phone = contact.get("phone_number")
		user = find_user(phone=phone)
		values = {"channel": "Telegram", "external_id": chat_id, "display_name": name, "phone": digits(phone),
			"user": user, "linked_on": frappe.utils.now_datetime()}
		if link:
			frappe.db.set_value("QA Channel Link", link.name, values)
		else:
			frappe.get_doc(dict(doctype="QA Channel Link", **values)).insert(ignore_permissions=True)
		if user:
			send(chat_id, f"✅ Linked to {frappe.utils.get_fullname(user)}. Send a message with screenshots to report an issue, or 'help'.",
				remove_keyboard=True)
		else:
			send(chat_id, "Thanks. Your number isn't on a QA Tracker user yet - you can still report issues; "
				"ask your QA lead to add your mobile number to your profile.", remove_keyboard=True)
		return

	text = msg.get("text") or msg.get("caption") or ""
	if text.strip().lower() in ("/start", "start"):
		send(chat_id, "Welcome to QA Tracker. Tap the button below once to link your account, then send screenshots and a short description to report an issue.",
			request_contact=not (link and link.user))
		if link and link.user:
			from qa_tracker.intake import HELP_TEXT

			send(chat_id, HELP_TEXT)
		return
	if text.strip().lower() in ("/help",):
		text = "help"

	images = []
	photo = msg.get("photo")
	if photo:
		biggest = max(photo, key=lambda p: p.get("file_size") or p.get("width", 0))
		content = download(biggest["file_id"])
		if content:
			images.append((f"telegram_{msg.get('message_id')}.jpg", content))
	doc = msg.get("document")
	if doc and (doc.get("mime_type") or "").startswith("image/"):
		content = download(doc["file_id"])
		if content:
			images.append((doc.get("file_name") or f"telegram_{msg.get('message_id')}.png", content))

	reply_to_issue = None
	replied = (msg.get("reply_to_message") or {}).get("message_id")
	if replied:
		reply_to_issue = frappe.db.get_value("QA Channel Message",
			{"message_id": f"out:telegram:{chat_id}:{replied}"}, "issue")

	user = link.user if link else None
	email = frappe.db.get_value("User", user, "email") if user else None
	out = intake.handle_chat_message(
		"Telegram",
		f"tg:{chat_id}",
		text=text,
		images=images,
		sender_name=name,
		email=email,
		message_id=f"tg:{chat_id}:{msg.get('message_id')}",
		reply_to_issue=reply_to_issue,
	)
	if out.get("reply") and not out.get("duplicate"):
		send(chat_id, out["reply"], issue=out.get("issue"))


def download(file_id):
	token = _token()
	info = call("getFile", file_id=file_id)
	if not info or not info.get("file_path"):
		return None
	r = requests.get(f"{API}/file/bot{token}/{info['file_path']}", timeout=60)
	r.raise_for_status()
	return r.content


def send(chat_id, text, issue=None, request_contact=False, remove_keyboard=False):
	if not _token():
		return None
	payload = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
	if request_contact:
		payload["reply_markup"] = {
			"keyboard": [[{"text": "📱 Share my phone number", "request_contact": True}]],
			"resize_keyboard": True,
			"one_time_keyboard": True,
		}
	elif remove_keyboard:
		payload["reply_markup"] = {"remove_keyboard": True}
	try:
		result = call("sendMessage", **payload)
	except Exception:
		frappe.log_error(title="QA Tracker Telegram reply failed", message=frappe.get_traceback())
		return None
	if issue and result:
		frappe.get_doc(
			{
				"doctype": "QA Channel Message",
				"channel": "Telegram",
				"message_id": f"out:telegram:{chat_id}:{result.get('message_id')}",
				"sender": "bot",
				"issue": issue,
				"status": "Processed",
				"text": text[:500],
				"received_on": frappe.utils.now_datetime(),
			}
		).insert(ignore_permissions=True)
	return result


def notify_user(user, text, issue=None):
	"""Send a notification to a user who has linked Telegram."""
	s = settings()
	if not (s.telegram_enabled and user):
		return
	chat = frappe.db.get_value("QA Channel Link", {"channel": "Telegram", "user": user}, "external_id")
	if chat:
		send(chat, text, issue=issue)


@frappe.whitelist()
def register_webhook():
	frappe.only_for(("System Manager", "QA Lead"))
	s = frappe.get_single("QA Settings")
	if not (_token() and s.telegram_secret):
		frappe.throw("Set the Bot Token and Webhook Secret first, then save.")
	from qa_tracker.utils import site_base_url

	url = f"{site_base_url()}/api/method/qa_tracker.channels.telegram.webhook"
	call("setWebhook", url=url, secret_token=s.telegram_secret.strip(), allowed_updates=["message", "edited_message"])
	me = call("getMe") or {}
	frappe.db.set_single_value("QA Settings", "telegram_bot_username", me.get("username"))
	return {"url": url, "bot": me.get("username")}
