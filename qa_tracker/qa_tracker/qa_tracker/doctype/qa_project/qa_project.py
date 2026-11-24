# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet


class QAProject(NestedSet):
	nsm_parent_field = "parent_qa_project"

	def validate(self):
		from qa_tracker import access

		self.project_code = (self.project_code or "").strip().upper().replace(" ", "").lstrip("#")
		if self.parent_qa_project:
			if self.parent_qa_project == self.name:
				frappe.throw(_("A project can't be its own parent"))
			if not frappe.db.get_value("QA Project", self.parent_qa_project, "is_group"):
				frappe.db.set_value("QA Project", self.parent_qa_project, "is_group", 1)
		if self.is_new() and not access.is_admin() and not any(m.user == frappe.session.user for m in self.members):
			# whoever creates a project leads it (unless they already lead the parent project)
			if not (self.parent_qa_project and access.is_project_lead(frappe.session.user, self.parent_qa_project)):
				self.append("members", {"user": frappe.session.user, "project_role": "QA Lead", "is_active": 1})
		vendors = {v.vendor for v in self.vendors} | {
			v.vendor for v in access.project_vendors(self.parent_qa_project)} if self.parent_qa_project else {v.vendor for v in self.vendors}
		seen = set()
		for m in self.members:
			key = (m.user, m.project_role)
			if key in seen:
				frappe.throw(_("Row {0}: {1} is already in the team as {2}").format(m.idx, m.user, m.project_role))
			seen.add(key)
			if m.vendor and m.vendor not in vendors:
				frappe.throw(_("Row {0}: vendor {1} is not one of this project's vendors").format(m.idx, m.vendor))
		vs = [v.vendor for v in self.vendors]
		if len(vs) != len(set(vs)):
			frappe.throw(_("A vendor is listed twice"))
		if self.project_lead and not any(m.user == self.project_lead for m in self.members):
			self.append("members", {"user": self.project_lead, "project_role": "QA Lead", "is_active": 1})
		members = {m.user for m in self.members}
		combos = set()
		for a in self.allocations:
			if a.user not in members:
				frappe.throw(_("Allocation row {0}: add {1} to the team first").format(a.idx, a.user))
			if (a.user, a.site, a.module) in combos:
				frappe.throw(_("Allocation row {0} is a duplicate").format(a.idx))
			combos.add((a.user, a.site, a.module))

	def on_update(self):
		super().on_update()
		from qa_tracker.access import ROLE_MAP, clear_cache

		clear_cache()
		# give each active member the Frappe role behind their project role (roles are never removed here)
		need = {}
		for m in self.members:
			if m.is_active and ROLE_MAP.get(m.project_role):
				need.setdefault(m.user, set()).add(ROLE_MAP[m.project_role])
		for user, roles in need.items():
			if user in ("Administrator", "Guest"):
				continue
			missing = roles - set(frappe.get_roles(user))
			if missing:
				u = frappe.get_doc("User", user)
				u.flags.ignore_permissions = True
				u.add_roles(*sorted(missing))

	def on_trash(self):
		for dt in ("QA Issue", "Gap Item"):
			if frappe.db.exists(dt, {"project": self.name}):
				frappe.throw(_("This project has {0} records. Close it instead of deleting.").format(_(dt)))
		super().on_trash(allow_root_deletion=True)  # top-level projects can be deleted when empty
