# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import getseries
from frappe.utils import now_datetime

from qa_tracker.compat import after_commit, assign
from qa_tracker.utils import party_for_user, settings

CLOSED_STATES = ("UAT Accepted", "Closed", "Rejected", "Merged")


class QAIssue(Document):
	def before_insert(self):
		user = frappe.session.user
		if not self.reported_by and user not in ("Guest", "Administrator") and self.source_channel in (None, "", "Web"):
			self.reported_by = user
		if not self.reported_on:
			self.reported_on = now_datetime()
		s = settings()
		if not self.site and s.default_site:
			self.site = s.default_site
		if not self.test_cycle and s.default_test_cycle and self.source_channel not in ("Web", "Import"):
			self.test_cycle = s.default_test_cycle
		if not self.module:
			from qa_tracker.intake import guess_module

			self.module = guess_module(f"{self.title or ''} {frappe.utils.strip_html(self.description or '')}") or s.default_module

	def validate(self):
		from qa_tracker import access

		self.title = (self.title or "").strip()[:240] or _("(no title)")
		access.apply_defaults(self)
		if self.vendor and self.project:
			allowed = [v.vendor for v in access.project_vendors(self.project)]
			if allowed and self.vendor not in allowed:
				frappe.throw(_("Vendor {0} is not part of project {1}").format(self.vendor, self.project))
		if self.is_new() and self.project and not self.flags.ignore_permissions:
			access.check_project(self.project)
		self.set_issue_code()
		for table in ("screenshots", "retest_screenshots", "uat_screenshots"):
			for row in self.get(table):
				if not row.added_by and frappe.session.user != "Guest":
					row.added_by = frappe.session.user
		self.handle_status_change()

	def on_update(self):
		before = self.get_doc_before_save()
		if self.assigned_to and (not before or before.assigned_to != self.assigned_to):
			self.assign_todo()
		old = before.status if before else None
		if old and old != self.status:
			from qa_tracker import notify

			name, new = self.name, self.status
			after_commit(lambda: notify.on_status_change(name, old, new))

	def after_insert(self):
		if self.source_channel == "Import":
			return
		from qa_tracker import notify

		name = self.name
		after_commit(lambda: notify.on_new_issue(name))

	# ------------------------------------------------------------------
	def set_issue_code(self):
		"""SITE-MODULE-#### . While the issue is still New the code follows site/module
		changes (e.g. a chat message adds #UTW after the first screenshot); once triaged it is fixed."""
		if not (self.site and self.module):
			return
		site_code = frappe.db.get_value("QA Site", self.site, "site_code")
		module_code = frappe.db.get_value("QA Module", self.module, "module_code")
		if not (site_code and module_code):
			return
		prefix = f"{site_code}-{module_code}-".upper()
		if self.issue_code and (self.issue_code.startswith(prefix) or self.status not in (None, "", "New")):
			return
		self.issue_code = prefix + getseries(prefix, 4)

	def handle_status_change(self):
		before = self.get_doc_before_save()
		old = before.status if before else None
		new = self.status
		if not old or old == new:
			return
		user = frappe.session.user
		now = now_datetime()
		s = settings()

		if new == "Triaged":
			if s.require_site_module_on_triage and not (self.site and self.module):
				frappe.throw(_("Set Site and Module before triaging"))
			if s.auto_assign_on_triage and not self.assigned_to:
				from qa_tracker.access import default_assignee

				self.assigned_to = default_assignee(self)
		if new == "Assigned" and not self.target_date:
			from qa_tracker.access import sla_days

			days = sla_days(self.vendor, self.severity)
			if days:
				self.target_date = frappe.utils.add_days(frappe.utils.today(), int(days))
		if new == "Ready for Retest":
			self.fixed_by = user
			self.fixed_on = now
			self.retest_result = "Pending"
			self.add_row("Fix", _("Marked fixed{0}: {1}").format(
				f" in build {self.fixed_in_build}" if self.fixed_in_build else "", self.resolution or ""))
		elif new == "Answered":
			self.fixed_by = user
			self.fixed_on = now
			self.add_row("Fix", _("Answer: {0}").format(self.resolution or ""))

		if old == "Ready for Retest" and new in ("Retest Passed", "Reopened"):
			self.retest_by = user
			self.retest_on = now
			self.retest_count = (self.retest_count or 0) + 1
			self.add_row("Retest", _("Retest {0}{1}{2}").format(
				_("PASSED") if new == "Retest Passed" else _("FAILED"),
				f" on build {self.retest_build}" if self.retest_build else "",
				f": {self.retest_notes}" if self.retest_notes else ""))
		if new == "Confirmed":
			self.confirmed_by = user
			self.confirmed_on = now
		if new == "In UAT":
			self.uat_result = "Pending"
		if old == "In UAT" and new in ("UAT Accepted", "Reopened"):
			self.uat_by = user
			self.uat_on = now
			self.add_row("UAT", _("UAT {0}{1}").format(
				_("ACCEPTED") if new == "UAT Accepted" else _("REJECTED"),
				f": {self.uat_notes}" if self.uat_notes else ""))
		if new == "Reopened":
			self.reopen_count = (self.reopen_count or 0) + 1
			self.closed_on = None
		if new in CLOSED_STATES:
			self.closed_on = now
		if old in CLOSED_STATES and new not in CLOSED_STATES:
			self.closed_on = None

		self.add_row("Status Change", f"{old} → {new}")

	def add_row(self, update_type, message):
		self.append(
			"updates",
			{
				"posted_on": now_datetime(),
				"posted_by": frappe.session.user if frappe.session.user != "Guest" else None,
				"party": party_for_user(frappe.session.user) if update_type not in ("Status Change",) else "System",
				"channel": "Web" if not frappe.flags.qa_channel else frappe.flags.qa_channel,
				"update_type": update_type,
				"message": message,
				"sender_name": frappe.utils.get_fullname(frappe.session.user),
			},
		)

	def assign_todo(self):
		assign(self.doctype, self.name, self.assigned_to, description=self.title,
			priority="High" if self.severity in ("Blocker", "High") else "Medium")
