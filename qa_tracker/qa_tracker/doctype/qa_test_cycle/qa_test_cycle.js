// Copyright (c) 2026, QA Tracker contributors
// License: MIT

frappe.ui.form.on("QA Test Cycle", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Create Test Runs for Testers"), () => {
			frappe.call({
				method: "qa_tracker.api.create_cycle_runs",
				args: { cycle: frm.doc.name },
				freeze: true,
				callback(r) {
					frappe.show_alert({ message: __("{0} test runs created", [r.message]), indicator: "green" });
					frm.reload_doc();
				},
			});
		});
		frm.add_custom_button(__("Test Runs"), () => frappe.set_route("List", "QA Test Execution", { test_cycle: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Issues"), () => frappe.set_route("List", "QA Issue", { test_cycle: frm.doc.name }), __("View"));
	},
});
