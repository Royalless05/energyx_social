frappe.listview_settings["Social Post"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Draft": "gray", "Pending Approval": "orange", "Approved": "blue", "Publishing": "yellow",
			"Published": "green", "Partial": "orange", "On Hold": "red", "Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
