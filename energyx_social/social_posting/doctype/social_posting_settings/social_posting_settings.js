frappe.ui.form.on("Social Account", {
	test_connection(frm, cdt, cdn) {
		if (frm.is_dirty() || locals[cdt][cdn].__islocal) {
			frappe.msgprint(__("Simpan dokumen terlebih dahulu agar token tersimpan terenkripsi, lalu klik Test Connection."));
			return;
		}
		frappe.call({
			method: "energyx_social.api.test_connection",
			args: { account: cdn },
			freeze: true,
			freeze_message: __("Menguji koneksi..."),
			callback: (r) => {
				const res = r.message || {};
				frappe.msgprint({
					title: __("Test Connection"),
					indicator: res.ok ? "green" : "red",
					message: res.message,
				});
				frm.reload_doc();
			},
		});
	},
});
