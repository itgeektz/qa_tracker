import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/qa"
		raise frappe.Redirect
	from qa_tracker import __version__
	from qa_tracker.utils import settings

	s = settings()
	context.no_cache = 1
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.version = __version__
	context.title = s.portal_title or "QA Tracker"
	context.accent = (s.portal_accent or "#0F766E").strip()
	context.lang = frappe.local.lang or "en"
	return context
