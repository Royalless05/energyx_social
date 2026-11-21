// Calendar view antrean konten: memakai field jadwal yang sudah ada (Default Scheduled At).
frappe.views.calendar["Social Post"] = {
	field_map: {
		start: "default_scheduled_at",
		end: "default_scheduled_at",
		id: "name",
		title: "title",
		status: "status",
	},
	get_css_class(data) {
		const map = {
			"Draft": "default", "Pending Approval": "warning", "Approved": "info", "Publishing": "warning",
			"Published": "success", "Partial": "warning", "On Hold": "danger", "Cancelled": "danger",
		};
		return map[data.status] || "default";
	},
	order_by: "default_scheduled_at",
};
