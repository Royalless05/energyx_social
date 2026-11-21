frappe.listview_settings["Social Comment"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = { "New": "red", "Replied": "green", "Ignored": "gray" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
	onload(listview) {
		listview.filter_area.add([[listview.doctype, "status", "=", "New"]]);
	},
};
