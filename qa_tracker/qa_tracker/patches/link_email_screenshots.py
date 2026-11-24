import frappe


def execute():
	"""Make screenshots that arrived by email viewable by everyone who can read the issue."""
	from qa_tracker.utils import link_file_to_issue

	rows = frappe.db.sql(
		"""select s.parent, s.image from `tabQA Screenshot` s
		where s.parenttype = 'QA Issue' and s.image like '/private/%%'""",
		as_dict=True,
	)
	for r in rows:
		link_file_to_issue(r.image, r.parent)
