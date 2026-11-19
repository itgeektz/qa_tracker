frappe.query_reports["QA Issue Summary"] = {
	filters: [
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select", default: "Reporter (Tester)",
		  options: ["Reporter (Tester)", "Assigned Developer", "Module", "Site", "Test Cycle", "Severity", "Source Channel"] },
		{ fieldname: "site", label: __("Site"), fieldtype: "Link", options: "QA Site" },
		{ fieldname: "module", label: __("Module"), fieldtype: "Link", options: "QA Module" },
		{ fieldname: "test_cycle", label: __("Test Cycle"), fieldtype: "Link", options: "QA Test Cycle" },
		{ fieldname: "severity", label: __("Severity"), fieldtype: "Select", options: "\nBlocker\nHigh\nMedium\nLow" },
		{ fieldname: "from_date", label: __("Reported From"), fieldtype: "Date" },
	],
};
