
// ---- merge duplicates (Desk) ----
window.qa_merge = window.qa_merge || {
	allowed(doctype) {
		return frappe.user.has_role("System Manager") || frappe.user.has_role("QA Lead") || (doctype === "Gap Item" && frappe.user.has_role("GA Analyst"));
	},
	method(doctype) { return doctype === "QA Issue" ? "qa_tracker.merge.merge_issues" : "qa_tracker.merge.merge_gaps"; },
	run(doctype, target, sources, after) {
		frappe.call({ method: this.method(doctype), args: { target, sources }, freeze: true, freeze_message: __("Merging…") }).then((r) => {
			frappe.show_alert({ message: __("Merged {0} into {1}", [r.message.merged.join(", "), r.message.target]), indicator: "green" });
			if (after) after(r.message);
		});
	},
	form(frm) {
		if (frm.doc.merged_into) {
			frm.dashboard.set_headline_alert(__("This was a duplicate and was merged into {0}",
				[`<a href="/app/${frappe.router.slug(frm.doctype)}/${frm.doc.merged_into}">${frm.doc.merged_into}</a>`]), "blue");
		}
		if (frm.is_new() || frm.doc.status === "Merged" || !this.allowed(frm.doctype)) return;
		const similar = frm.doctype === "QA Issue" ? "qa_tracker.merge.similar_issues" : "qa_tracker.merge.similar_gaps";
		const notMerged = () => ({ filters: { name: ["!=", frm.doc.name], status: ["!=", "Merged"] } });
		frm.add_custom_button(__("Merge duplicates into this"), () => {
			frappe.call(similar, { name: frm.doc.name }).then((r) => {
				const opts = (r.message || []).map((x) => ({ label: `${x.name}: ${x.title} (${Math.round(x.score * 100)}%)`, value: x.name }));
				const d = new frappe.ui.Dialog({
					title: __("Merge duplicates into {0}", [frm.doc.name]),
					fields: [
						{ fieldtype: "MultiCheck", fieldname: "similar", label: __("Similar records"), options: opts, columns: 1,
							description: opts.length ? "" : __("No similar records found") },
						{ fieldtype: "Link", fieldname: "other", options: frm.doctype, label: __("Or another one"), get_query: notMerged },
						{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Screenshots, files, links and history are copied here; the duplicates are marked Merged.")}</p>` },
					],
					primary_action_label: __("Merge"),
					primary_action: (v) => {
						const sources = (v.similar || []).concat(v.other ? [v.other] : []);
						if (!sources.length) { frappe.msgprint(__("Pick at least one duplicate")); return; }
						d.hide();
						qa_merge.run(frm.doctype, frm.doc.name, sources, () => frm.reload_doc());
					},
				});
				d.show();
			});
		}, __("Merge"));
		frm.add_custom_button(__("This is a duplicate of…"), () => {
			frappe.prompt([{ fieldtype: "Link", fieldname: "target", options: frm.doctype, reqd: 1, label: __("Keep this one"), get_query: notMerged }],
				(v) => qa_merge.run(frm.doctype, v.target, [frm.doc.name], (m) => frappe.set_route("Form", frm.doctype, m.target)),
				__("Merge {0} into…", [frm.doc.name]), __("Merge"));
		}, __("Merge"));
	},
	list(list, doctype) {
		if (!this.allowed(doctype)) return;
		list.page.add_actions_menu_item(__("Merge selected"), () => {
			const names = list.get_checked_items(true);
			if (names.length < 2) { frappe.msgprint(__("Select at least two records")); return; }
			frappe.prompt([{ fieldtype: "Select", fieldname: "target", label: __("Keep this one"), reqd: 1, options: names.join("\n"), default: names[0],
				description: __("The others are merged into it.") }],
			(v) => qa_merge.run(doctype, v.target, names.filter((n) => n !== v.target), () => list.refresh()),
			__("Merge {0} records", [names.length]), __("Merge"));
		});
	},
};

// Copyright (c) 2026, QA Tracker contributors
// License: MIT

const QA_COLORS = {
	New: "blue", Triaged: "cyan", Assigned: "purple", "In Progress": "orange",
	"Ready for Retest": "yellow", Reopened: "red", "Retest Passed": "light-green", Confirmed: "green",
	"In UAT": "pink", "UAT Accepted": "green", Answered: "cyan", Closed: "green", Deferred: "gray", Rejected: "gray", Merged: "gray",
};

frappe.listview_settings["QA Issue"] = {
	add_fields: ["status", "severity", "issue_code", "assigned_to"],
	has_indicator_for_draft: 1,
	get_indicator(doc) {
		return [__(doc.status), QA_COLORS[doc.status] || "gray", "status,=," + doc.status];
	},
	onload(list) {
		qa_merge.list(list, "QA Issue");
		const me = frappe.session.user;
		list.page.add_inner_button(__("Reported by me"), () => {
			list.filter_area.clear(false).then(() => list.filter_area.add([["QA Issue", "reported_by", "=", me]]));
		}, __("Quick Filters"));
		list.page.add_inner_button(__("Assigned to me"), () => {
			list.filter_area.clear(false).then(() => list.filter_area.add([["QA Issue", "assigned_to", "=", me]]));
		}, __("Quick Filters"));
		list.page.add_inner_button(__("Waiting for retest"), () => {
			list.filter_area.clear(false).then(() => list.filter_area.add([["QA Issue", "status", "=", "Ready for Retest"]]));
		}, __("Quick Filters"));
		list.page.add_inner_button(__("Open blockers"), () => {
			list.filter_area.clear(false).then(() => list.filter_area.add([
				["QA Issue", "severity", "=", "Blocker"],
				["QA Issue", "status", "not in", ["UAT Accepted", "Closed", "Rejected"]],
			]));
		}, __("Quick Filters"));
	},
};
