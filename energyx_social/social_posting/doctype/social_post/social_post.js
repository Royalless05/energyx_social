const FORMATS = {
	"Instagram": ["Post", "Reel", "Story", "Carousel"],
	"Facebook Page": ["Photo", "Video", "Text", "Album"],
	"YouTube": ["Short", "Video"],
	"TikTok": ["Video", "Photo"],
	"LinkedIn": ["Text", "Photo", "Video"],
};
const MULTI = { "Carousel": 1, "Album": 1 };
const MANAGER = ["Social Manager", "System Manager"];
const API = "energyx_social.api.";

frappe.ui.form.on("Social Post", {
	setup(frm) {
		frm.set_query("account", "channels", (doc, cdt, cdn) => ({
			query: API + "search_accounts",
			filters: { channel: locals[cdt][cdn].channel },
		}));
		frm.set_query("hashtag_template", "channels", (doc, cdt, cdn) => ({
			query: API + "search_hashtag_templates",
			filters: { channel: locals[cdt][cdn].channel, account: locals[cdt][cdn].account },
		}));
	},

	title: (frm) => render_preview(frm),
	base_caption: (frm) => render_preview(frm),
	base_media: (frm) => render_preview(frm),
	media_asset(frm) {
		if (!frm.doc.media_asset) return;
		frappe.db.get_value("Social Media Asset", frm.doc.media_asset, "file").then((r) => {
			if (r.message && r.message.file) frm.set_value("base_media", r.message.file);
		});
	},
	media_items_add: (frm) => render_preview(frm),
	media_items_remove: (frm) => render_preview(frm),
	before_workflow_action(frm) {
		const action = frm.selected_workflow_action;
		const open = (frm.doc.revision_notes || []).filter((n) => n.status !== "Resolved").length;
		if (["Reject", "Request Revision"].includes(action) && !open) {
			frappe.throw(__("Tambahkan minimal satu catatan revisi (status Open) pada tabel Revision Notes sebelum menolak."));
		}
		if (action === "Submit for Approval" && open) {
			frappe.throw(__("Masih ada {0} catatan revisi berstatus Open. Tandai Resolved sebelum mengajukan ulang.", [open]));
		}
	},
	channels_add: (frm) => render_preview(frm),
	channels_remove: (frm) => render_preview(frm),

	refresh(frm) {
		render_preview(frm);
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
		if (["Published", "Partial"].includes(s)) {
			frm.add_custom_button(__("Pull Comments"), () => frappe.call({
				method: API + "pull_comments", args: { post: frm.doc.name }, freeze: true,
				callback: (r) => frappe.show_alert({ message: r.message, indicator: "green" }),
			}), __("Actions"));
		}
		frm.add_custom_button(__("Link Clicks"), () => frappe.call({
			method: API + "link_stats", args: { post: frm.doc.name },
			callback: (r) => {
				const d = r.message || { links: 0, clicks: 0, rows: [] };
				const lines = (d.rows || []).map((x) => `${frappe.utils.escape_html(x.channel || "")}: ${frappe.utils.escape_html(x.short_url || x.code)} — ${x.clicks || 0}`);
				frappe.msgprint({ title: __("Short Links"), message: `${d.links} ${__("links")}, ${d.clicks} ${__("clicks")}<br>${lines.join("<br>")}` });
			},
		}), __("Actions"));
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
	account(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.account && !row.hashtag_template) {
			frappe.call({
				method: API + "get_default_hashtag_template",
				args: { channel: row.channel, account: row.account },
				callback: (r) => r.message && frappe.model.set_value(cdt, cdn, "hashtag_template", r.message),
			});
		}
		render_preview(frm);
	},
	hashtag_template(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.hashtag_template) return;
		frappe.db.get_value("Social Hashtag Template", row.hashtag_template, "hashtags").then((r) => {
			const tags = (r.message && r.message.hashtags) || "";
			const current = row.caption_override || frm.doc.base_caption || "";
			if (!tags || current.includes(tags)) return;
			frappe.model.set_value(cdt, cdn, "caption_override", (current.trimEnd() + "\n\n" + tags).trim());
		});
	},
	media_asset(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.media_asset) return;
		frappe.db.get_value("Social Media Asset", row.media_asset, "file").then((r) => {
			if (r.message && r.message.file) frappe.model.set_value(cdt, cdn, "media_override", r.message.file);
		});
	},
	post_format: (frm) => render_preview(frm),
	caption_override: (frm) => render_preview(frm),
	media_override: (frm) => render_preview(frm),
	thumbnail: (frm) => render_preview(frm),
	first_comment: (frm) => render_preview(frm),
	active: (frm) => render_preview(frm),
});

frappe.ui.form.on("Social Post Media", {
	media_asset(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.media_asset) return;
		frappe.db.get_value("Social Media Asset", row.media_asset, "file").then((r) => {
			if (r.message && r.message.file) frappe.model.set_value(cdt, cdn, "media", r.message.file);
		});
	},
	media: (frm) => render_preview(frm),
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

/* ------------------------------------------------------------------ preview (client-side, perkiraan tampilan) */
const PREVIEW = {
	limit: { "Instagram": 2200, "Facebook Page": 63206, "YouTube": 5000, "TikTok": 2200, "LinkedIn": 3000 },
	cut: { "Instagram": 125, "Facebook Page": 480, "YouTube": 100, "TikTok": 100, "LinkedIn": 210 },
};
const PREVIEW_CSS = `<style>
.sx-tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.sx-tab{border:1px solid var(--border-color);background:var(--control-bg);color:var(--text-color);border-radius:999px;padding:3px 12px;font-size:12px;cursor:pointer}
.sx-tab.active{background:var(--primary);border-color:var(--primary);color:#fff}
.sx-wrap{display:flex;gap:24px;flex-wrap:wrap;align-items:flex-start}
.sx-card{width:100%;max-width:360px;border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg);overflow:hidden;font-size:13px;color:var(--text-color)}
.sx-head{display:flex;align-items:center;gap:8px;padding:10px 12px;font-weight:600}
.sx-av{width:30px;height:30px;border-radius:50%;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px}
.sx-media{display:block;width:100%;object-fit:cover;background:#111}
.sx-r11{aspect-ratio:1/1}.sx-r169{aspect-ratio:16/9}.sx-r916{aspect-ratio:9/16}
.sx-empty{display:flex;align-items:center;justify-content:center;color:#999;font-size:12px}
.sx-body{padding:10px 12px;line-height:1.45;word-break:break-word}
.sx-tag{color:#1877f2}.sx-more{color:var(--text-muted)}
.sx-sub{color:var(--text-muted);font-size:12px;padding:0 12px 10px}
.sx-comment{border-top:1px solid var(--border-color);padding:8px 12px;font-size:12px}
.sx-tt{position:relative;background:#000;color:#fff}
.sx-tt .sx-over{position:absolute;left:0;right:0;bottom:0;padding:12px;background:linear-gradient(transparent,rgba(0,0,0,.75));font-size:13px}
.sx-note{margin-top:8px;font-size:12px;color:var(--text-muted)}
.sx-bad{color:var(--red-500,#e24c4c)}
</style>`;

function preview_media(url, ratio, poster) {
	const cls = `sx-media sx-${ratio}`;
	if (!url) return `<div class="${cls} sx-empty">${__("No media")}</div>`;
	const u = frappe.utils.escape_html(url);
	if (/\.(mp4|mov|webm)(\?|$)/i.test(url)) {
		const p = poster ? ` poster="${frappe.utils.escape_html(poster)}"` : "";
		return `<video class="${cls}" src="${u}"${p} controls muted playsinline></video>`;
	}
	return `<img class="${cls}" src="${u}" alt="">`;
}

function preview_caption(text, cut) {
	let shown = text || "";
	const more = cut && shown.length > cut;
	if (more) shown = shown.slice(0, cut).trimEnd();
	// pecah dulu lalu escape per bagian, agar entity (&#39;) tidak ikut terbaca sebagai hashtag
	const html = shown.split(/(#[\p{L}\p{N}_]+)/u).map((part, i) => {
		const esc = frappe.utils.escape_html(part).replace(/\n/g, "<br>");
		return i % 2 ? `<span class="sx-tag">${esc}</span>` : esc;
	}).join("");
	return html + (more ? ` … <span class="sx-more">${__("more")}</span>` : "");
}

function preview_card(frm, row) {
	const ch = row.channel;
	const fmt = row.post_format || (FORMATS[ch] || [""])[0];
	let media = row.media_override || frm.doc.base_media;
	let badge = "";
	if (MULTI[fmt]) {
		const items = (frm.doc.media_items || []).filter((i) => i.media);
		media = items.length ? items[0].media : null;
		badge = `<div class="sx-sub">${items.length} ${__("slides")}${items.length < 2 ? " · " + __("min. 2") : ""}</div>`;
	}
	const caption = row.caption_override || frm.doc.base_caption || "";
	const name = row.account_label || ch;
	const e = frappe.utils.escape_html;
	const head = `<div class="sx-head"><div class="sx-av">${e((name || "?").charAt(0).toUpperCase())}</div>${e(name)}</div>`;
	const cap = preview_caption(caption, PREVIEW.cut[ch]);
	const comment = row.first_comment
		? `<div class="sx-comment"><b>${e(name)}</b> ${preview_caption(row.first_comment)}</div>` : "";
	let html;
	if (ch === "Instagram") {
		const ratio = (fmt === "Post" || fmt === "Carousel") ? "r11" : "r916";
		html = `${head}${preview_media(media, ratio)}${badge}<div class="sx-body"><b>${e(name)}</b> ${cap}</div>${comment}`;
	} else if (ch === "Facebook Page") {
		const m = fmt === "Text" ? "" : preview_media(media, "r169");
		html = `${head}<div class="sx-body">${cap}</div>${m}${badge}${comment}`;
	} else if (ch === "LinkedIn") {
		const m = fmt === "Text" ? "" : preview_media(media, "r169");
		html = `${head}<div class="sx-body">${cap}</div>${m}`;
	} else if (ch === "YouTube") {
		const ratio = fmt === "Short" ? "r916" : "r169";
		html = `${preview_media(media, ratio, row.thumbnail)}<div class="sx-body"><b>${e(frm.doc.title || "")}</b></div>`
			+ `<div class="sx-sub">${e(name)}</div><div class="sx-body">${cap}</div>`;
	} else {
		html = `<div class="sx-tt">${preview_media(media, "r916")}<div class="sx-over"><b>@${e(name)}</b><br>${cap}</div></div>`;
	}
	const limit = PREVIEW.limit[ch];
	const len = caption.length;
	const over = len > limit;
	const note = `<div class="sx-note ${over ? "sx-bad" : ""}">${len} / ${limit} ${__("characters")} · ${e(ch)} / ${e(fmt)}</div>`;
	return `<div><div class="sx-card">${html}</div>${note}</div>`;
}

function render_preview(frm) {
	const field = frm.fields_dict.preview_html;
	if (!field) return;
	const rows = (frm.doc.channels || []).filter((r) => r.channel && r.active !== 0);
	if (!rows.length) {
		field.$wrapper.html(`<div class="text-muted small">${__("Add a channel to see a preview.")}</div>`);
		return;
	}
	const idx = Math.min(frm.__sx_preview_idx || 0, rows.length - 1);
	const tabs = rows.map((r, i) =>
		`<button type="button" class="sx-tab ${i === idx ? "active" : ""}" data-i="${i}">`
		+ `${frappe.utils.escape_html(r.channel)} · ${frappe.utils.escape_html(r.account_label || r.post_format || "")}</button>`).join("");
	field.$wrapper.html(`${PREVIEW_CSS}<div class="sx-tabs">${tabs}</div>`
		+ `<div class="sx-wrap">${preview_card(frm, rows[idx])}</div>`
		+ `<div class="sx-note">${__("Approximate preview. Each platform renders posts slightly differently.")}</div>`);
	field.$wrapper.find(".sx-tab").on("click", (ev) => {
		frm.__sx_preview_idx = parseInt($(ev.currentTarget).attr("data-i"), 10);
		render_preview(frm);
	});
}
