frappe.listview_settings["Social Post"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Draft": "gray", "Pending Approval": "orange", "Pending Final Approval": "orange", "Approved": "blue", "Publishing": "yellow",
			"Published": "green", "Partial": "orange", "On Hold": "red", "Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
	onload(listview) {
		if (!["Social Editor", "Social Manager", "System Manager"].some((r) => frappe.user.has_role(r))) return;
		listview.page.add_inner_button(__("Bulk Schedule (CSV)"), () => bulk_schedule_dialog(listview));
	},
};

function bulk_schedule_dialog(listview) {
	const header = ["title", "caption", "media", "channels", "formats", "scheduled_at", "campaign", "hashtags"];
	const example = ["Promo Akhir Tahun", "Diskon 20%!", "https://example.com/promo.jpg", "Instagram:Brand IG; Facebook Page",
		"Instagram=Post", "2026-12-01 09:00", "", "#promo #diskon"];
	const d = new frappe.ui.Dialog({
		title: __("Bulk Schedule (CSV / XLSX)"),
		fields: [
			{ fieldtype: "HTML", fieldname: "help", options: `<p class="text-muted small">${__("Setiap baris menjadi satu Social Post berstatus Draft (maks. 200 baris). Kolom: ")}<code>${header.join(", ")}</code>. ${__("channels: pisahkan dengan ; , gunakan Channel:Nama Akun bila ada lebih dari satu akun.")}</p>` },
			{ fieldtype: "Button", fieldname: "template", label: __("Download CSV Template") },
			{ fieldtype: "Attach", fieldname: "file", label: __("File (.csv / .xlsx)"), reqd: 1 },
			{ fieldtype: "HTML", fieldname: "result" },
		],
		primary_action_label: __("Validate"),
		primary_action(values) { run(values.file, 1); },
		secondary_action_label: __("Create Drafts"),
		secondary_action() { run(d.get_value("file"), 0); },
	});
	d.fields_dict.template.input.onclick = () => {
		const q = (v) => `"${String(v).replace(/"/g, '""')}"`;
		const csv = "\ufeff" + [header, example].map((r) => r.map(q).join(",")).join("\r\n");
		const a = document.createElement("a");
		a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
		a.download = "socialx_bulk_template.csv";
		a.click();
	};
	function run(file, dry) {
		if (!file) return frappe.msgprint(__("Pilih file terlebih dahulu."));
		frappe.call({
			method: "energyx_social.api.bulk_schedule", args: { file_url: file, dry_run: dry }, freeze: true,
			callback(r) {
				const res = r.message || {};
				const e = frappe.utils.escape_html;
				let html = `<div class="${res.errors && res.errors.length ? "text-danger" : "text-success"}"><b>${res.ok}</b> / ${res.total} ${__("baris OK")} ${dry ? "(" + __("validasi saja") + ")" : "— " + __("Draft dibuat")}</div>`;
				if (res.errors && res.errors.length) {
					html += "<ul>" + res.errors.map((x) => `<li>${__("Baris")} ${x.row} (${e(x.title || "")}): ${e(x.error)}</li>`).join("") + "</ul>";
				}
				d.fields_dict.result.$wrapper.html(html);
				if (!dry) listview.refresh();
			},
		});
	}
	d.show();
}
