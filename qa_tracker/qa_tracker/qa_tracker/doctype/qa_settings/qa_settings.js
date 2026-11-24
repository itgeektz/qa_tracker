// Copyright (c) 2026, QA Tracker contributors
// License: MIT

frappe.ui.form.on("QA Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Show Webhook URLs"), () => {
			frm.call({ method: "get_endpoints", doc: frm.doc }).then((r) => {
				const e = r.message;
				frappe.msgprint({
					title: __("Integration endpoints"),
					message: `<p><b>Tester portal</b><br><a href="${e.portal}" target="_blank">${e.portal}</a></p>
						<p><b>WhatsApp webhook</b><br><code>${e.whatsapp}</code></p>
						<p><b>Telegram webhook</b> (use Register Telegram Webhook)<br><code>${e.telegram}</code></p>
						<p><b>Teams outgoing webhook</b><br><code>${e.teams}</code></p>
						<p><b>Generic intake API</b> (header <code>X-QA-Token</code>)<br><code>${e.api}</code></p>
						<p><b>Email</b>: create an Email Account with Enable Incoming and <i>Append To = QA Issue</i>.</p>
						<p><b>Raven</b>: install Raven on this site, then use Pick Raven Channel.</p>`,
				});
			});
		});
		frm.add_custom_button(__("Pick Raven Channel"), () => {
			frappe.call("qa_tracker.channels.raven.list_channels").then((r) => {
				const chans = r.message || [];
				if (!chans.length) {
					frappe.msgprint(__("Create a channel in Raven first (for example #qa-reports)."));
					return;
				}
				const d = new frappe.ui.Dialog({
					title: __("Raven channel for QA reports"),
					fields: [{
						fieldname: "ch", fieldtype: "Select", label: __("Channel"), reqd: 1,
						options: chans.map((c) => ({ value: c.name, label: "#" + c.channel_name + (c.workspace ? " (" + c.workspace + ")" : "") })),
					}],
					primary_action_label: __("Use channel"),
					primary_action(v) {
						frm.set_value("raven_channel", v.ch);
						frm.set_value("raven_enabled", 1);
						d.hide();
						frappe.call("qa_tracker.channels.raven.setup_bot").then(() => frm.save());
					},
				});
				d.show();
			});
		}, __("Chat"));
		frm.add_custom_button(__("Register Telegram Webhook"), () => {
			frappe.call({ method: "qa_tracker.channels.telegram.register_webhook", freeze: true }).then((r) => {
				frappe.msgprint(__("Telegram webhook set for @{0}:<br><code>{1}</code>", [r.message.bot, r.message.url]));
				frm.reload_doc();
			});
		}, __("Chat"));
	},
});
