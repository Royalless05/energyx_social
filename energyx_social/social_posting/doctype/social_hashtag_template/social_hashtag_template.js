frappe.ui.form.on("Social Hashtag Template", {
	setup(frm) {
		frm.set_query("account", () => ({
			query: "energyx_social.api.search_accounts",
			filters: { channel: frm.doc.channel },
		}));
	},
});
