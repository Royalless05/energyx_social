app_name = "energyx_social"
app_title = "SocialX"
app_publisher = "EnergyX 369"
app_description = "SocialX: publish ke Instagram, Facebook Page, YouTube, TikTok, LinkedIn dari EnergyX 369 ERP"
app_email = "dev@example.com"
app_license = "mit"

required_apps = ["frappe", "erpnext"]  # Campaign dilink dari ERPNext

# Ikon di halaman Apps (Desk v16). Route = slug dari label Workspace.
add_to_apps_screen = [
    {
        "name": "energyx_social",
        "logo": "/assets/energyx_social/images/logo.svg",
        "title": "SocialX",
        "route": "/desk/socialx",
        "has_permission": "energyx_social.api.has_app_permission",
    }
]

# /s/<kode> -> pengalih short link (www/s.py)
website_route_rules = [{"from_route": "/s/<code>", "to_route": "s"}]

after_install = "energyx_social.setup.install.after_install"
after_migrate = "energyx_social.setup.install.after_migrate"

doctype_list_js = {"Social Post": "social_posting/doctype/social_post/social_post_list.js"}

# Notifikasi editor/manager saat status Social Post berubah (perubahan lewat publisher dipanggil langsung dari sana)
doc_events = {"Social Post": {"on_update": "energyx_social.notifications.on_post_update"}}

scheduler_events = {
    "cron": {
        # Tiap 5 menit: ambil <= 10 kanal jatuh tempo -> enqueue (queue long, timeout 1200s)
        "*/5 * * * *": ["energyx_social.jobs.dispatch_due_posts"],
    },
    "hourly": [
        "energyx_social.jobs.create_recurring_posts",
        "energyx_social.jobs.pull_comments",
    ],
    "daily_long": [
        "energyx_social.jobs.renew_tokens",
        "energyx_social.jobs.pull_metrics",
    ],
}
