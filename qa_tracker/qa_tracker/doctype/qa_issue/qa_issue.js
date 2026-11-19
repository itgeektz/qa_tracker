
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

const QA_STAGES = [
	{ label: __("Logged"), states: ["New", "Triaged"] },
	{ label: __("With Developer"), states: ["Assigned", "In Progress", "Reopened"] },
	{ label: __("Retest"), states: ["Ready for Retest", "Answered"] },
	{ label: __("Confirmed"), states: ["Retest Passed", "Confirmed"] },
	{ label: __("UAT"), states: ["In UAT"] },
	{ label: __("Done"), states: ["UAT Accepted", "Closed"] },
];

function qa_has(...roles) {
	return roles.some((r) => frappe.user.has_role(r)) || frappe.session.user === "Administrator";
}

function qa_shot_fields(prefix) {
	return [
		{ fieldtype: "Section Break", label: __("Screenshots") },
		{ fieldname: prefix + "1", fieldtype: "Attach Image", label: __("Screenshot 1") },
		{ fieldtype: "Column Break" },
		{ fieldname: prefix + "2", fieldtype: "Attach Image", label: __("Screenshot 2") },
		{ fieldtype: "Column Break" },
		{ fieldname: prefix + "3", fieldtype: "Attach Image", label: __("Screenshot 3") },
	];
}

function qa_collect(values, prefix) {
	return [1, 2, 3].map((i) => values[prefix + i]).filter(Boolean);
}

function qa_result_dialog(frm, title, kinds, fields, primary) {
	const d = new frappe.ui.Dialog({
		title: title,
		fields: fields.concat(qa_shot_fields("shot")),
		primary_action_label: primary || __("Save"),
		primary_action(values) {
			const kind = typeof kinds === "function" ? kinds(values) : kinds;
			frappe.call({
				method: "qa_tracker.api.record_result",
				args: {
					issue: frm.doc.name,
					kind: kind,
					notes: values.notes,
					build: values.build,
					root_cause: values.root_cause,
					screenshots: qa_collect(values, "shot"),
				},
				freeze: true,
				callback() {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

frappe.ui.form.on("QA Issue", {
	setup(frm) {
		// developers of this project (and of the ticket's vendor); any developer when no project is set
		frm.set_query("assigned_to", () => ({
			query: "qa_tracker.access.developer_query",
			filters: { project: frm.doc.project || "", vendor: frm.doc.vendor || "" },
		}));
		frm.set_query("module", () => ({ filters: { is_active: 1 } }));
	},

	refresh(frm) {
		qa_merge.form(frm);
		if (frm.is_new()) return;
		qa_render_stage(frm);
		qa_render_gallery(frm);

		frm.add_custom_button(__("Add Update"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Add Update to {0}", [frm.doc.name]),
				fields: [
					{ fieldname: "message", fieldtype: "Small Text", label: __("Update"), reqd: 0 },
				].concat(qa_shot_fields("shot")),
				primary_action_label: __("Post"),
				primary_action(values) {
					frappe.call({
						method: "qa_tracker.api.add_update",
						args: { issue: frm.doc.name, message: values.message, screenshots: qa_collect(values, "shot") },
						freeze: true,
						callback() {
							d.hide();
							frm.reload_doc();
							frappe.show_alert({ message: __("Update posted"), indicator: "green" });
						},
					});
				},
			});
			d.show();
		}).addClass("btn-primary");

		const s = frm.doc.status;
		if (s === "Triaged" && qa_has("QA Lead")) {
			frm.add_custom_button(__("Assign Developer"), () => {
				frappe.prompt([{ fieldname: "dev", fieldtype: "Link", options: "User", label: __("Developer"), reqd: 1, default: frm.doc.assigned_to,
					get_query: () => ({ query: "qa_tracker.access.developer_query", filters: { project: frm.doc.project || "", vendor: frm.doc.vendor || "" } }) }], (v) => {
					frm.set_value("assigned_to", v.dev).then(() => frm.save()).then(() =>
						frappe.xcall("frappe.model.workflow.apply_workflow", { doc: frm.doc, action: "Assign to Developer" })).then(() => frm.reload_doc());
				}, __("Assign to developer"), __("Assign"));
			}).addClass("btn-primary");
		}
		if (["Assigned", "In Progress", "Reopened"].includes(s) && qa_has("Vendor Developer", "QA Lead")) {
			frm.add_custom_button(__("Mark Fixed"), () =>
				qa_result_dialog(frm, __("Mark Fixed - ready for retest"), "fix", [
					{ fieldname: "notes", fieldtype: "Small Text", label: __("What was fixed"), reqd: 1, default: frm.doc.resolution },
					{ fieldname: "root_cause", fieldtype: "Small Text", label: __("Root Cause"), default: frm.doc.root_cause },
					{ fieldname: "build", fieldtype: "Data", label: __("Fixed In Build"), default: frm.doc.fixed_in_build },
				]), __("Developer"));
			if (frm.doc.issue_type === "Query" || s !== "Reopened") {
				frm.add_custom_button(__("Answer Query"), () =>
					qa_result_dialog(frm, __("Answer"), "answer", [
						{ fieldname: "notes", fieldtype: "Small Text", label: __("Answer"), reqd: 1 },
					]), __("Developer"));
			}
		}
		if (s === "Ready for Retest" && qa_has("QA Tester", "QA Lead")) {
			frm.add_custom_button(__("Record Retest"), () =>
				qa_result_dialog(frm, __("Retest Result"), (v) => (v.result === "Pass" ? "retest_pass" : "retest_fail"), [
					{ fieldname: "result", fieldtype: "Select", label: __("Result"), options: "Pass\nFail", reqd: 1 },
					{ fieldname: "build", fieldtype: "Data", label: __("Build Tested"), default: frm.doc.fixed_in_build },
					{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes"), mandatory_depends_on: "eval:doc.result=='Fail'" },
				]), __("Tester"));
		}
		if (s === "In UAT" && qa_has("UAT User", "QA Lead")) {
			frm.add_custom_button(__("Record UAT Result"), () =>
				qa_result_dialog(frm, __("UAT Result"), (v) => (v.result === "Accepted" ? "uat_accept" : "uat_reject"), [
					{ fieldname: "result", fieldtype: "Select", label: __("Result"), options: "Accepted\nRejected", reqd: 1 },
					{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes"), mandatory_depends_on: "eval:doc.result=='Rejected'" },
				]), __("UAT"));
		}
		frm.add_custom_button(__("Log as Gap"), () => {
			frappe.prompt([
				{ fieldname: "fit_status", fieldtype: "Select", label: __("Fit status"), options: "Gap\nPartial Fit", default: "Gap", reqd: 1 },
				{ fieldname: "priority", fieldtype: "Select", label: __("Priority"), options: "Must Have\nShould Have\nCould Have\nWon't Have",
					default: frm.doc.severity === "Blocker" ? "Must Have" : "Should Have" },
			], (v) => {
				frappe.call({ method: "qa_tracker.gap_analysis.api.create_from_issue", args: { issue: frm.doc.name, fit_status: v.fit_status, priority: v.priority },
					freeze: true, callback(r) { frappe.set_route("Form", "Gap Item", r.message); } });
			}, __("Log this ticket as a gap"), __("Create gap"));
		}, __("Create"));
		frm.add_custom_button(__("Open in Portal"), () => window.open("/qa#/t/" + encodeURIComponent(frm.doc.name), "_blank"), __("View"));
		if (frm.doc.test_execution) {
			frm.add_custom_button(__("Test Run"), () => frappe.set_route("Form", "QA Test Execution", frm.doc.test_execution), __("View"));
		}
	},
});

function qa_render_stage(frm) {
	const s = frm.doc.status;
	const idx = QA_STAGES.findIndex((st) => st.states.includes(s));
	const off = ["Deferred", "Rejected"].includes(s);
	const steps = QA_STAGES.map((st, i) => {
		const done = !off && i < idx;
		const cur = !off && i === idx;
		const color = cur ? "var(--primary)" : done ? "var(--green-500)" : "var(--gray-400)";
		return `<div style="flex:1;text-align:center">
			<div style="height:6px;border-radius:3px;background:${color}"></div>
			<div style="font-size:11px;margin-top:4px;${cur ? "font-weight:600" : ""}">${st.label}</div></div>`;
	}).join('<div style="width:6px"></div>');
	const extra = [];
	if (frm.doc.retest_count) extra.push(__("Retests: {0}", [frm.doc.retest_count]));
	if (frm.doc.reopen_count) extra.push(__("Reopened: {0}", [frm.doc.reopen_count]));
	if (frm.doc.issue_code) extra.push(frm.doc.issue_code);
	frm.dashboard.add_section(
		`<div style="display:flex;align-items:flex-start">${steps}</div>
		 <div class="text-muted small" style="margin-top:6px">${__("Status")}: <b>${__(s)}</b>${off ? "" : ""} ${extra.length ? "· " + extra.join(" · ") : ""}</div>`,
		__("Stage")
	);
	frm.dashboard.show();
}

function qa_render_gallery(frm) {
	const groups = [
		[__("Reported"), frm.doc.screenshots || []],
		[__("Retest"), frm.doc.retest_screenshots || []],
		[__("UAT"), frm.doc.uat_screenshots || []],
		[__("Updates"), (frm.doc.updates || []).filter((u) => u.screenshot).map((u) => ({ image: u.screenshot, caption: u.message }))],
	].filter((g) => g[1].length);
	const media = (frm.doc.media_files || []).filter((r) => r.file);
	const recs = media.filter((r) => r.file_type === "Recording");
	const docs = media.filter((r) => r.file_type !== "Recording");
	if (!groups.length && !media.length) return;
	const html = groups.map(([label, rows]) => `
		<div style="margin-bottom:8px"><div class="small text-muted">${label}</div>
		<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:4px">
		${rows.filter((r) => r.image).map((r) => `<a href="${encodeURI(r.image)}" target="_blank" title="${frappe.utils.escape_html(r.caption || "")}">
			<img src="${encodeURI(r.image)}" style="height:90px;max-width:160px;object-fit:cover;border:1px solid var(--border-color);border-radius:6px"></a>`).join("")}
		</div></div>`).join("") + (recs.length ? `<div style="margin-bottom:8px"><div class="small text-muted">${__("Screen recordings")}</div>
		<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:4px">${recs.map((r) => `<div><video src="${encodeURI(r.file)}" controls preload="metadata"
			style="height:140px;max-width:260px;border-radius:6px;background:#000"></video><div class="small text-muted">${frappe.utils.escape_html(r.caption || "")} ${frappe.utils.escape_html(r.duration || "")}</div></div>`).join("")}</div></div>` : "")
		+ (docs.length ? `<div style="margin-bottom:8px"><div class="small text-muted">${__("Files")}</div><div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:4px">
		${docs.map((r) => `<a href="${encodeURI(r.file)}" target="_blank" class="btn btn-default btn-xs">${frappe.utils.escape_html((r.file_type || "File") + ": " + r.file.split("/").pop())}</a>`).join("")}</div></div>` : "");
	frm.dashboard.add_section(html, __("Screenshots & recordings"));
}
