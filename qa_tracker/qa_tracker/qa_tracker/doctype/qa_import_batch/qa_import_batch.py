# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe.model.document import Document


class QAImportBatch(Document):
	@frappe.whitelist()
	def run_import(self):
		from qa_tracker.importer import import_batch

		self.check_permission("write")
		return import_batch(self.name)
