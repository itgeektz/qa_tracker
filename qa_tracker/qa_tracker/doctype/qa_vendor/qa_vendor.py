# Copyright (c) 2026, QA Tracker contributors
# License: MIT

from frappe.model.document import Document


class QAVendor(Document):
	def validate(self):
		self.vendor_code = (self.vendor_code or "").strip().upper().replace(" ", "")
