# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class QATestExecution(Document):
	def validate(self):
		if not self.tester:
			self.tester = frappe.session.user
		before = self.get_doc_before_save()
		if self.result not in ("Not Run", None) and (not before or before.result != self.result):
			self.execution_date = now_datetime()
		if self.result in ("Fail", "Blocked") and not (self.actual_result or "").strip():
			frappe.throw("Describe the actual result for a failed or blocked test")
		for row in self.screenshots:
			if not row.added_by:
				row.added_by = frappe.session.user

	def on_update(self):
		from qa_tracker.qa_tracker.doctype.qa_test_cycle.qa_test_cycle import update_cycle_stats

		update_cycle_stats(self.test_cycle)

	def on_trash(self):
		self.flags.cycle = self.test_cycle

	def after_delete(self):
		from qa_tracker.qa_tracker.doctype.qa_test_cycle.qa_test_cycle import update_cycle_stats

		update_cycle_stats(self.flags.cycle or self.test_cycle)
