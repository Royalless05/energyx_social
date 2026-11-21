frappe.query_reports["Social Analytics"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -90) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "group_by", label: __("View"), fieldtype: "Select", reqd: 1, default: "Post",
			options: ["Post", "Account", "Channel", "Week", "Hour of Day", "Weekday"] },
		{ fieldname: "channel", label: __("Channel"), fieldtype: "Select",
			options: ["", "Instagram", "Facebook Page", "YouTube", "TikTok", "LinkedIn"] },
		{ fieldname: "account", label: __("Account"), fieldtype: "Link", options: "Social Account" },
	],
};
