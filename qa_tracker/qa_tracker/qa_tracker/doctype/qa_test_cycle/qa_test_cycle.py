# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe.model.document import Document


class QATestCycle(Document):
	def validate(self):
		if self.start_date and self.end_date and self.end_date < self.start_date:
			frappe.throw("End Date cannot be before Start Date")


def update_cycle_stats(cycle):
	rows = frappe.get_all(
		"QA Test Execution", filters={"test_cycle": cycle}, fields=["result", "count(name) as n"], group_by="result"
	)
	counts = {r.result: r.n for r in rows}
	total = sum(counts.values())
	executed = total - counts.get("Not Run", 0) - counts.get("Skipped", 0)
	frappe.db.set_value(
		"QA Test Cycle",
		cycle,
		{
			"total_runs": total,
			"passed": counts.get("Pass", 0),
			"failed": counts.get("Fail", 0),
			"blocked": counts.get("Blocked", 0),
			"not_run": counts.get("Not Run", 0),
			"pass_rate": round(100.0 * counts.get("Pass", 0) / executed, 1) if executed else 0,
		},
		update_modified=False,
	)
