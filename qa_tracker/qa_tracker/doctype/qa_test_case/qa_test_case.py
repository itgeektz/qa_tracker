# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe.model.document import Document
from frappe.model.naming import getseries


class QATestCase(Document):
	def autoname(self):
		code = (frappe.db.get_value("QA Module", self.module, "module_code") or "TC").upper()
		self.name = f"{code}-" + getseries(f"TC-{code}-", 4)
