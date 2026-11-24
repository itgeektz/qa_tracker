app_name = "qa_tracker"
app_title = "QA Tracker"
app_publisher = "QA Tracker contributors"
app_description = "Test, retest, confirmation and UAT tracking with screenshots, and email / WhatsApp / Teams ticket intake"
app_email = "qa@example.com"
app_license = "MIT"
required_apps = ["frappe"]

before_install = "qa_tracker.install.before_install"
after_install = "qa_tracker.install.after_install"
after_migrate = "qa_tracker.install.after_migrate"

doc_events = {
	# Email intake: an Email Account with "Append To = QA Issue" creates the issue;
	# these hooks turn the email body / image attachments into description,
	# screenshots and updates.
	"Communication": {
		# Frappe saves the email body in a second save (after attachments), so use on_update
		"on_update": "qa_tracker.channels.email_hooks.on_communication",
	},
	"File": {
		"after_insert": "qa_tracker.channels.email_hooks.on_file",
	},
	# Raven chat (only fires on sites where the Raven app is installed)
	"Raven Message": {
		"after_insert": "qa_tracker.channels.raven.on_raven_message",
	},
	# multi-project: fill project / vendor and check membership
	"Gap Item": {"validate": "qa_tracker.access.validate_scoped"},
	"Gap Assessment": {"validate": "qa_tracker.access.validate_scoped"},
	"QA Test Cycle": {"validate": "qa_tracker.access.validate_scoped"},
	"QA Import Batch": {"validate": "qa_tracker.access.validate_scoped"},
}

# ---- multi-project / multi-vendor row-level access (see access.py)
_SCOPED = ["QA Issue", "QA Test Cycle", "QA Test Case", "QA Test Execution", "QA Import Batch", "QA Module",
	"Gap Assessment", "Gap Item", "QA Project", "QA Vendor", "QA Site"]
permission_query_conditions = {
	dt: "qa_tracker.access.pqc_" + dt.lower().replace(" ", "_") for dt in _SCOPED
}
has_permission = {dt: "qa_tracker.access.has_permission" for dt in _SCOPED if dt != "QA Site"}

# Point-in-time notifications (also sent from QA Issue controller)
scheduler_events = {
	"daily": ["qa_tracker.notify.daily_digest", "qa_tracker.notify.overdue_digest"],
}

# Teams outgoing webhooks send "Authorization: HMAC <sig>", which Frappe would
# otherwise reject as an unknown API credential. This hook verifies the HMAC.
auth_hooks = ["qa_tracker.channels.teams.auth_hook"]

fixtures = []
