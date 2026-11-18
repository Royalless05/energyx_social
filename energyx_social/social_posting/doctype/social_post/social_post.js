const FORMATS = {
	"Instagram": ["Post", "Reel", "Story"],
	"Facebook Page": ["Photo", "Video", "Text"],
	"YouTube": ["Short", "Video"],
	"TikTok": ["Video", "Photo"],
};
const MANAGER = ["Social Manager", "System Manager"];
const API = "energyx_social.api.";

frappe.ui.form.on("Social Post", {
	setup(frm) {
		frm.set_query("account", "channels", (doc, cdt, cdn) => ({
			query: API + "search_accounts",
			filters: { channel: locals[cdt][cdn].channel },
		}));
	},

	refresh(frm) {
		if (frm.is_new() || !MANAGER.some((r) => frappe.user.has_role(r))) return;
		const s = frm.doc.status;
		const live = ["Approved", "Publishing", "Partial"].includes(s);
		if (live) {
			add_action(frm, __("Publish Now"), ["Queued", "Scheduled"], "publish_now");
			add_action(frm, __("Retry Failed"), ["Failed"], "retry");
		}
		if (["Published", "Partial", "Approved"].includes(s)) {
			add_action(frm, __("Remove from Platform"), ["Published"], "delete_remote", true);
		}
	},
});

frappe.ui.form.on("Social Post Channel", {
	channel(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "account", null);
		frappe.model.set_value(cdt, cdn, "post_format", (FORMATS[row.channel] || [""])[0]);
		set_format_options(frm, cdn, row.channel);
	},
	form_render(frm, cdt, cdn) {
		set_format_options(frm, cdn, locals[cdt][cdn].channel);
	},
});

function set_format_options(frm, cdn, channel) {
	const grid_row = frm.fields_dict.channels.grid.grid_rows_by_docname[cdn];
	const field = grid_row && grid_row.get_field("post_format");
	if (!field) return;
	field.df.options = [""].concat(FORMATS[channel] || []).join("\n");
	field.refresh();
}

function add_action(frm, label, statuses, method, danger) {
	frm.add_custom_button(label, () => {
		const rows = (frm.doc.channels || []).filter((r) => r.active && statuses.includes(r.status));
		if (!rows.length) {
			frappe.msgprint(__("Tidak ada kanal dengan status {0}.", [statuses.join("/")]));
			return;
		}
		const d = new frappe.ui.Dialog({
			title: label,
			fields: [{
				fieldtype: "MultiCheck", fieldname: "rows", label: __("Kanal"), columns: 1,
				options: rows.map((r) => ({
					label: `${r.channel} · ${r.account_label || ""} · ${r.post_format}`,
					value: r.name, checked: 1,
				})),
			}],
			primary_action_label: label,
			primary_action(values) {
				if (!(values.rows || []).length) return;
				d.hide();
				frappe.call({
					method: API + method,
					args: { post: frm.doc.name, rows: values.rows },
					freeze: true,
					callback: (r) => {
						frappe.show_alert({ message: r.message || __("Selesai"), indicator: "green" });
						frm.reload_doc();
					},
				});
			},
		});
		d.show();
	}, __("Actions"));
}
