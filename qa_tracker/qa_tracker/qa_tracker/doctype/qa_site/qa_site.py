# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe.utils.nestedset import NestedSet


class QASite(NestedSet):
	nsm_parent_field = "parent_qa_site"

	def validate(self):
		self.site_code = (self.site_code or "").strip().upper()
		if self.parent_qa_site and not frappe.db.get_value("QA Site", self.parent_qa_site, "is_group"):
			frappe.db.set_value("QA Site", self.parent_qa_site, "is_group", 1)

	def on_update(self):
		super().on_update()
		from qa_tracker.access import clear_cache

		clear_cache()

	def on_trash(self):
		for dt in ("QA Issue", "Gap Item", "QA Test Cycle"):
			if frappe.db.exists(dt, {"site": self.name}):
				frappe.throw(frappe._("{0} records use this site. Mark it inactive instead of deleting.").format(frappe._(dt)))
		super().on_trash(allow_root_deletion=True)
