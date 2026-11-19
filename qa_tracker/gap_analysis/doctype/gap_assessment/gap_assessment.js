// Copyright (c) 2026, QA Tracker contributors
// License: MIT

frappe.ui.form.on("Gap Assessment", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Add Gap"), () => frappe.new_doc("Gap Item", { assessment: frm.doc.name, site: frm.doc.site, module: frm.doc.module, business_owner: frm.doc.approver }));
		frm.add_custom_button(__("Gap Items"), () => frappe.set_route("List", "Gap Item", { assessment: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Fit-Gap Summary"), () => frappe.set_route("query-report", "Gap Register Summary", { assessment: frm.doc.name, group_by: "Module" }), __("View"));
		frm.add_custom_button(__("Sign-off Sheet"), () => {
			window.open(frappe.urllib.get_full_url(`/printview?doctype=Gap%20Assessment&name=${encodeURIComponent(frm.doc.name)}&format=Gap%20Assessment%20Sign-off&trigger_print=1`));
		}, __("View"));
		if (frm.doc.status !== "Signed Off" && (frappe.session.user === frm.doc.approver || frappe.user.has_role(["GA Approver", "QA Lead", "System Manager"]))) {
			frm.add_custom_button(__("Sign Off"), () => {
				frappe.prompt([{ fieldname: "comments", fieldtype: "Small Text", label: __("Sign-off comments") }], (v) => {
					frm.call({ method: "sign_off", doc: frm.doc, args: { comments: v.comments }, freeze: true }).then(() => frm.reload_doc());
				}, __("Sign off assessment"), __("Sign off"));
			}).addClass("btn-primary");
		}
		if (frm.doc.total_items) {
			const pct = frm.doc.fit_percent || 0;
			frm.dashboard.add_indicator(__("Fit {0}%", [pct]), pct >= 80 ? "green" : pct >= 60 ? "orange" : "red");
			frm.dashboard.add_indicator(__("Gaps {0} · Partial {1} · Fit {2}", [frm.doc.gap_count, frm.doc.partial_count, frm.doc.fit_count]), "blue");
			if (frm.doc.open_must_haves) frm.dashboard.add_indicator(__("{0} open must-haves", [frm.doc.open_must_haves]), "red");
		}
	},
});
