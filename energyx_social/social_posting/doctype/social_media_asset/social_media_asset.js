frappe.ui.form.on("Social Media Asset", {
	refresh(frm) {
		const field = frm.fields_dict.usage_html;
		if (!field) return;
		const e = frappe.utils.escape_html;
		let html = "";
		if (frm.doc.file) {
			const url = e(frm.doc.file);
			html += /\.(mp4|mov|webm)(\?|$)/i.test(frm.doc.file)
				? `<video src="${url}" controls muted style="max-width:320px;border-radius:8px"></video>`
				: `<img src="${url}" alt="" style="max-width:320px;border-radius:8px">`;
		}
		field.$wrapper.html(html + `<div class="text-muted small usage-info"></div>`);
		if (!frm.is_new()) {
			frappe.call({
				method: "energyx_social.api.asset_usage", args: { asset: frm.doc.name },
				callback: (r) => {
					const d = r.message || { count: 0, posts: [] };
					const links = d.posts.map((p) => `<a href="/desk/social-post/${encodeURIComponent(p)}">${e(p)}</a>`).join(", ");
					field.$wrapper.find(".usage-info").html(`${__("Used in")} <b>${d.count}</b> ${__("post(s)")} ${links}`);
				},
			});
		}
	},
	file: (frm) => frm.trigger("refresh"),
});
