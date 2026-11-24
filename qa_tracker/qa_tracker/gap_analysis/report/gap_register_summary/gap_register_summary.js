frappe.query_reports["Gap Register Summary"] = {
	filters: [
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select", default: "Module",
		  options: ["Module", "Site", "Assessment", "Resolution Approach", "Priority", "Gap Type", "Responsible Party", "Business Owner", "Status"] },
		{ fieldname: "assessment", label: __("Assessment"), fieldtype: "Link", options: "Gap Assessment" },
		{ fieldname: "site", label: __("Site"), fieldtype: "Link", options: "QA Site" },
		{ fieldname: "module", label: __("Module"), fieldtype: "Link", options: "QA Module" },
		{ fieldname: "priority", label: __("Priority"), fieldtype: "Select", options: "\nMust Have\nShould Have\nCould Have\nWon't Have" },
		{ fieldname: "regulatory_only", label: __("Regulatory only"), fieldtype: "Check" },
	],
};
