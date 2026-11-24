
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

const GAP_STAGES = [
	{ label: __("Identified"), states: ["Identified"] },
	{ label: __("Analysed"), states: ["Analysed"] },
	{ label: __("Approval"), states: ["Awaiting Approval"] },
	{ label: __("Delivery"), states: ["Approved", "In Progress"] },
	{ label: __("Verification"), states: ["Delivered", "Verified"] },
	{ label: __("Closed"), states: ["Closed"] },
];

function gap_has(...roles) {
	return roles.some((r) => frappe.user.has_role(r)) || frappe.session.user === "Administrator";
}

function gap_dialog(frm, title, kind, fields, label, style) {
	const d = new frappe.ui.Dialog({
		title,
		fields: (fields || []).concat(kind.startsWith("verify") || kind === "deliver" ? [
			{ fieldname: "ev", fieldtype: "Attach", label: __("Evidence (optional)") },
		] : []),
		primary_action_label: label || title,
		primary_action(v) {
			const kinds = typeof kind === "function" ? kind(v) : kind;
			frappe.call({
				method: "qa_tracker.gap_analysis.api.record",
				args: { gap: frm.doc.name, kind: kinds, notes: v.notes, build: v.build, evidence: v.ev ? [v.ev] : [] },
				freeze: true,
				callback() { d.hide(); frm.reload_doc(); },
			});
		},
	});
	if (style) d.get_primary_btn().removeClass("btn-primary").addClass(style);
	d.show();
}

function gap_simple(frm, kind) {
	frappe.call({ method: "qa_tracker.gap_analysis.api.record", args: { gap: frm.doc.name, kind }, freeze: true, callback: () => frm.reload_doc() });
}

frappe.ui.form.on("Gap Item", {
	setup(frm) {
		["assigned_to", "business_owner", "raised_by"].forEach((f) =>
			frm.set_query(f, () => ({ query: "frappe.core.doctype.user.user.user_query", filters: { ignore_user_type: 1 } })));
	},

	assessment(frm) {
		if (!frm.doc.assessment) return;
		frappe.db.get_value("Gap Assessment", frm.doc.assessment, ["site", "module", "approver"]).then((r) => {
			const a = r.message || {};
			if (!frm.doc.site && a.site) frm.set_value("site", a.site);
			if (!frm.doc.module && a.module) frm.set_value("module", a.module);
			if (!frm.doc.business_owner && a.approver) frm.set_value("business_owner", a.approver);
		});
	},

	refresh(frm) {
		qa_merge.form(frm);
		if (frm.is_new()) return;
		gap_render_stage(frm);
		const s = frm.doc.status;

		frm.add_custom_button(__("Add Update"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Add Update"),
				fields: [
					{ fieldname: "message", fieldtype: "Small Text", label: __("Update") },
					{ fieldname: "file", fieldtype: "Attach", label: __("Attachment") },
				],
				primary_action_label: __("Post"),
				primary_action(v) {
					frappe.call({ method: "qa_tracker.gap_analysis.api.add_update", args: { gap: frm.doc.name, message: v.message, attachment: v.file },
						freeze: true, callback() { d.hide(); frm.reload_doc(); } });
				},
			});
			d.show();
		});

		const analyst = gap_has("GA Analyst", "QA Lead");
		if (s === "Identified" && analyst) frm.add_custom_button(__("Analyse"), () => gap_simple(frm, "analyse"), __("Stage"));
		if (["Identified", "Analysed"].includes(s) && analyst && ["Fit", "Not Applicable"].includes(frm.doc.fit_status))
			frm.add_custom_button(__("Close as Fit"), () => gap_simple(frm, "close_fit"), __("Stage"));
		if (s === "Analysed" && analyst && ["Gap", "Partial Fit"].includes(frm.doc.fit_status))
			frm.add_custom_button(__("Submit for Approval"), () => {
				if (!frm.doc.resolution_approach || !frm.doc.business_owner) {
					frappe.msgprint(__("Set the Resolution Approach and the Business Owner on the Resolution tab first."));
					frm.scroll_to_field(!frm.doc.resolution_approach ? "resolution_approach" : "business_owner");
					return;
				}
				gap_simple(frm, "submit");
			}, __("Stage"));
		if (s === "Awaiting Approval" && gap_has("GA Approver", "QA Lead")) {
			const notes = [{ fieldname: "notes", fieldtype: "Small Text", label: __("Decision notes") }];
			frm.add_custom_button(__("Approve"), () => gap_dialog(frm, __("Approve gap"), "approve", notes, __("Approve"), "btn-success"), __("Decision"));
			frm.add_custom_button(__("Reject"), () => gap_dialog(frm, __("Reject gap"), "reject",
				[{ fieldname: "notes", fieldtype: "Small Text", label: __("Why is it rejected?"), reqd: 1 }], __("Reject"), "btn-danger"), __("Decision"));
			frm.add_custom_button(__("Defer"), () => gap_dialog(frm, __("Defer gap"), "defer",
				[{ fieldname: "notes", fieldtype: "Small Text", label: __("Defer until / reason"), reqd: 1 }], __("Defer")), __("Decision"));
			frm.add_custom_button(__("Send Back"), () => gap_dialog(frm, __("Send back for analysis"), "send_back",
				[{ fieldname: "notes", fieldtype: "Small Text", label: __("What needs more analysis?"), reqd: 1 }], __("Send back")), __("Decision"));
		}
		const deliverer = gap_has("Vendor Developer", "GA Analyst", "QA Lead");
		if (s === "Approved" && deliverer) frm.add_custom_button(__("Start Work"), () => gap_simple(frm, "start"), __("Stage"));
		if (["Approved", "In Progress"].includes(s) && deliverer)
			frm.add_custom_button(__("Mark Delivered"), () => gap_dialog(frm, __("Mark delivered"), "deliver", [
				{ fieldname: "notes", fieldtype: "Small Text", label: __("What was delivered?"), reqd: 1, default: frm.doc.delivery_notes },
				{ fieldname: "build", fieldtype: "Data", label: __("Build / release"), default: frm.doc.delivered_in_build || frm.doc.target_release },
			], __("Mark delivered")), __("Stage"));
		if (s === "Delivered" && gap_has("QA Tester", "UAT User", "GA Analyst", "QA Lead"))
			frm.add_custom_button(__("Record Verification"), () => gap_dialog(frm, __("Verification result"),
				(v) => (v.result === "Pass" ? "verify_pass" : "verify_fail"), [
					{ fieldname: "result", fieldtype: "Select", label: __("Result"), options: "Pass\nFail", reqd: 1 },
					{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes"), mandatory_depends_on: "eval:doc.result=='Fail'" },
				], __("Save")), __("Stage"));
		if (s === "Verified" && gap_has("GA Approver", "GA Analyst", "QA Lead")) frm.add_custom_button(__("Close"), () => gap_simple(frm, "close"), __("Stage"));
		if (["Closed", "Rejected", "Deferred"].includes(s) && analyst) frm.add_custom_button(__("Reopen"), () => gap_simple(frm, "reopen"), __("Stage"));

		if (!["Closed", "Rejected"].includes(s)) {
			frm.add_custom_button(__("Verification Test Case"), () => {
				frappe.call({ method: "qa_tracker.gap_analysis.api.create_test_case", args: { gap: frm.doc.name }, freeze: true,
					callback(r) { frappe.show_alert({ message: __("Test case {0} created", [r.message]), indicator: "green" }); frm.reload_doc(); } });
			}, __("Create"));
		}
		if (frm.doc.created_from_issue)
			frm.add_custom_button(__("Source QA Issue"), () => frappe.set_route("Form", "QA Issue", frm.doc.created_from_issue), __("View"));
		if (frm.doc.assessment)
			frm.add_custom_button(__("Assessment"), () => frappe.set_route("Form", "Gap Assessment", frm.doc.assessment), __("View"));
	},
});

function gap_render_stage(frm) {
	const s = frm.doc.status;
	const off = ["Deferred", "Rejected"].includes(s);
	const idx = GAP_STAGES.findIndex((st) => st.states.includes(s));
	const fitColor = { "Fit": "var(--green-500)", "Partial Fit": "var(--orange-500)", "Gap": "var(--red-500)", "Not Applicable": "var(--gray-500)" }[frm.doc.fit_status];
	const steps = GAP_STAGES.map((st, i) => {
		const color = off ? "var(--gray-300)" : i === idx ? "var(--primary)" : i < idx ? "var(--green-500)" : "var(--gray-300)";
		return `<div style="flex:1;text-align:center"><div style="height:6px;border-radius:3px;background:${color}"></div>
			<div style="font-size:11px;margin-top:4px;${i === idx ? "font-weight:600" : ""}">${st.label}</div></div>`;
	}).join('<div style="width:6px"></div>');
	const facts = [
		`<span style="color:${fitColor};font-weight:600">● ${__(frm.doc.fit_status || "")}</span>`,
		frappe.utils.escape_html(frm.doc.priority || ""),
		frm.doc.resolution_approach ? frappe.utils.escape_html(frm.doc.resolution_approach) : null,
		frm.doc.effort_days ? __("{0} days", [frm.doc.effort_days]) : null,
		frm.doc.decision && frm.doc.decision !== "Pending" ? __("Decision: {0}", [frm.doc.decision]) : null,
		frm.doc.gap_code,
	].filter(Boolean).join(" · ");
	frm.dashboard.add_section(`<div style="display:flex;align-items:flex-start">${steps}</div>
		<div class="text-muted small" style="margin-top:6px">${__("Status")}: <b>${__(s)}</b> · ${facts}</div>`, __("Stage"));
	frm.dashboard.show();
}
