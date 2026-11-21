const API = "energyx_social.api.";

frappe.ui.form.on("Social Comment", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.status !== "Replied") {
			frm.add_custom_button(__("Reply"), () => {
				frappe.prompt(
					{ fieldname: "text", fieldtype: "Small Text", label: __("Reply"), reqd: 1 },
					(v) => frappe.call({
						method: API + "reply_comment", args: { comment: frm.doc.name, text: v.text }, freeze: true,
						callback: (r) => { frappe.show_alert({ message: r.message, indicator: "green" }); frm.reload_doc(); },
					}),
					__("Reply to {0}", [frm.doc.author_name || ""]), __("Send"));
			}).addClass("btn-primary");
			const target = frm.doc.status === "Ignored" ? "New" : "Ignored";
			frm.add_custom_button(target === "Ignored" ? __("Ignore") : __("Mark as New"), () => frappe.call({
				method: API + "set_comment_status", args: { comment: frm.doc.name, status: target },
				callback: () => frm.reload_doc(),
			}), __("Actions"));
		}
		if (frm.doc.post) {
			frm.add_custom_button(__("Open Post"), () => frappe.set_route("Form", "Social Post", frm.doc.post), __("Actions"));
		}
	},
});
