"""Small shims so the app runs unchanged on Frappe v14, v15, v16 and v17-dev."""

import frappe


def major_version():
	try:
		return int(str(frappe.__version__).split(".")[0])
	except Exception:
		return 15


def cache():
	"""frappe.cache() is a function up to v15; newer versions expose an object that may not be callable."""
	c = frappe.cache
	try:
		return c() if callable(c) and not hasattr(c, "get_value") else c
	except TypeError:
		return c


def after_commit(fn):
	"""Run fn after the current transaction commits (immediately if not supported)."""
	hook = getattr(getattr(frappe, "db", None), "after_commit", None)
	if hook is not None and hasattr(hook, "add"):
		hook.add(fn)
	else:
		try:
			fn()
		except Exception:
			frappe.log_error(title="QA Tracker after-commit task failed", message=frappe.get_traceback())


def clear_last_message():
	fn = getattr(frappe, "clear_last_message", None)
	if fn:
		fn()
	elif getattr(frappe.local, "message_log", None):
		frappe.local.message_log = frappe.local.message_log[:-1]


def assign(doctype, name, user, description=None, priority="Medium"):
	from frappe.desk.form import assign_to

	args = {"assign_to": [user], "doctype": doctype, "name": name, "description": description or name, "priority": priority}
	try:
		if hasattr(assign_to, "_add"):
			assign_to._add(args, ignore_permissions=True)
		else:
			assign_to.add(args)
	except Exception:
		clear_last_message()


def app_installed(app):
	try:
		return app in frappe.get_installed_apps()
	except Exception:
		return False


def doctype_exists(doctype):
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False


def request_data():
	req = getattr(frappe.local, "request", None)
	if not req:
		return b""
	try:
		return req.get_data(cache=True) or b""
	except TypeError:
		return req.get_data() or b""
