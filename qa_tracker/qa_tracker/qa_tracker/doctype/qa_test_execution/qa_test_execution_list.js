frappe.listview_settings["QA Test Execution"] = {
	add_fields: ["result"],
	get_indicator(doc) {
		const c = { Pass: "green", Fail: "red", Blocked: "orange", Skipped: "gray", "Not Run": "blue" }[doc.result] || "gray";
		return [__(doc.result), c, "result,=," + doc.result];
	},
	onload(list) {
		list.page.add_inner_button(__("My test runs"), () => {
			list.filter_area.clear(false).then(() => list.filter_area.add([["QA Test Execution", "tester", "=", frappe.session.user]]));
		});
	},
};
