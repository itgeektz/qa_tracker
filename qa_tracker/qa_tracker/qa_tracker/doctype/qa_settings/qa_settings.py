# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe.model.document import Document
from frappe.utils import get_url


class QASettings(Document):
	def validate(self):
		if self.whatsapp_enabled and not (self.whatsapp_phone_number_id and self.whatsapp_access_token and self.whatsapp_verify_token):
			frappe.throw("WhatsApp needs Phone Number ID, Access Token and Verify Token")
		if self.api_enabled and not self.api_token:
			frappe.throw("Set an API Token to enable the Intake API")
		if self.teams_enabled and not self.teams_outgoing_secret:
			frappe.throw("Paste the security token Teams gave you for the outgoing webhook")
		if self.telegram_enabled and not (self.telegram_bot_token and self.telegram_secret):
			frappe.throw("Telegram needs the Bot Token and a Webhook Secret")
		if self.raven_enabled:
			from qa_tracker.compat import app_installed

			if not app_installed("raven"):
				frappe.throw("Raven is not installed on this site (it needs Frappe v15.111 or newer)")
		if self.portal_accent and not __import__("re").match(r"^#[0-9a-fA-F]{6}$", self.portal_accent.strip()):
			frappe.throw("Accent Colour must look like #0F766E")

	@frappe.whitelist()
	def get_endpoints(self):
		base = (self.public_base_url or "").rstrip("/") or get_url()
		return {
			"portal": f"{base}/qa",
			"telegram": f"{base}/api/method/qa_tracker.channels.telegram.webhook",
			"whatsapp": f"{base}/api/method/qa_tracker.channels.whatsapp.webhook",
			"teams": f"{base}/api/method/qa_tracker.channels.teams.outgoing_webhook",
			"api": f"{base}/api/method/qa_tracker.api.intake",
		}
