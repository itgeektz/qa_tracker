// Copyright (c) 2026, QA Tracker contributors
// License: MIT

frappe.ui.form.on("QA Import Batch", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status !== "Completed") {
			frm.add_custom_button(__("Run Import"), () => {
				frm.call({ method: "run_import", doc: frm.doc, freeze: true, freeze_message: __("Importing...") }).then((r) => {
					frappe.msgprint(__("{0} issues created", [r.message]));
					frm.reload_doc();
				});
			}).addClass("btn-primary");
		}
		if (frm.doc.status === "Completed") {
			frm.add_custom_button(__("Imported Issues"), () => frappe.set_route("List", "QA Issue", { import_batch: frm.doc.name }));
		}
	},
});
