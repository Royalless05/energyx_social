app_name = "energyx_social"
app_title = "EnergyX Social"
app_publisher = "EnergyX 369"
app_description = "Social Posting: publish ke Instagram, Facebook Page, YouTube, TikTok dari ERPNext"
app_email = "dev@example.com"
app_license = "mit"

required_apps = ["frappe", "erpnext"]  # Campaign dilink dari ERPNext

after_install = "energyx_social.setup.install.after_install"
after_migrate = "energyx_social.setup.install.after_migrate"

doctype_list_js = {"Social Post": "social_posting/doctype/social_post/social_post_list.js"}

scheduler_events = {
    "cron": {
        # Tiap 5 menit: ambil <= 10 kanal jatuh tempo -> enqueue (queue long, timeout 1200s)
        "*/5 * * * *": ["energyx_social.jobs.dispatch_due_posts"],
    },
    "daily_long": [
        "energyx_social.jobs.renew_tokens",
        "energyx_social.jobs.pull_metrics",
    ],
}
