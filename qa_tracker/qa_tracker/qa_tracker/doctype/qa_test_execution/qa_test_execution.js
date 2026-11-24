// Copyright (c) 2026, QA Tracker contributors
// License: MIT

frappe.ui.form.on("QA Test Execution", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (["Fail", "Blocked"].includes(frm.doc.result) && !frm.doc.issue) {
			frm.add_custom_button(__("Raise Issue"), () => {
				frappe.call({
					method: "qa_tracker.api.raise_issue_from_execution",
					args: { execution: frm.doc.name },
					freeze: true,
					callback(r) {
						frm.reload_doc();
						frappe.set_route("Form", "QA Issue", r.message);
					},
				});
			}).addClass("btn-danger");
		}
		["Pass", "Fail", "Blocked"].forEach((res) => {
			if (frm.doc.result !== res) {
				frm.add_custom_button(__(res), () => {
					frm.set_value("result", res).then(() => {
						if (res === "Pass") frm.save();
						else frappe.show_alert(__("Describe the actual result, add screenshots, then Save"));
					});
				}, __("Set Result"));
			}
		});
	},
});
