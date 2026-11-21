"""Scheduler: dispatch tiap 5 menit, perpanjang token & tarik metrik harian."""
import frappe
from frappe.utils import add_days, add_to_date, getdate, now_datetime

from energyx_social.services.credentials import Account
from energyx_social.services.errors import redact
from energyx_social.services.providers import get_provider
from energyx_social.services.publisher import (
    MAX_ATTEMPTS, PUBLISH_PHASE, ROW, claim_row, enqueue_row, update_parent_status,
)
from energyx_social.social_posting.doctype.social_post_metric.social_post_metric import compute_engagement_rate

BATCH_LIMIT = 25  # default; bisa diubah di Social Posting Settings (1-200)
STALE_MINUTES = 30
TOKEN_RENEW_DAYS = 10
METRICS_WINDOW_DAYS = 90  # default; bisa diubah di Social Posting Settings
METRICS_ROW_LIMIT = 1000


# ---------------------------------------------------------------------- tiap 5 menit
def _batch_limit() -> int:
    value = frappe.db.get_single_value("Social Posting Settings", "dispatch_batch_limit")
    return min(max(int(value or BATCH_LIMIT), 1), 200)


def dispatch_due_posts():
    _recover_stale()
    due = frappe.db.sql(
        """
        select c.name, c.parent
        from `tabSocial Post Channel` c
        join `tabSocial Post` p on p.name = c.parent
        where c.parenttype = 'Social Post' and c.active = 1 and c.status = 'Scheduled'
          and c.scheduled_at <= %(now)s and p.status in %(phase)s
        order by c.scheduled_at asc
        limit %(limit)s
        """,
        {"now": now_datetime(), "phase": PUBLISH_PHASE, "limit": _batch_limit()},
        as_dict=True,
    )
    for item in due:
        try:
            if claim_row(item.name, ("Scheduled",)):
                enqueue_row(item.parent, item.name)
                update_parent_status(item.parent)
                frappe.db.commit()  # melepas lock; enqueue_after_commit baru jalan setelah ini
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Social Posting: gagal enqueue", reference_doctype="Social Post",
                             reference_name=item.parent)


def _recover_stale():
    """Worker mati di tengah publish -> baris menggantung 'Publishing'. Jadwalkan ulang (state tetap, jadi bisa lanjut)."""
    cutoff = add_to_date(now_datetime(), minutes=-STALE_MINUTES)
    for row in frappe.get_all(ROW, filters={"status": "Publishing", "modified": ["<", cutoff], "remote_id": ["is", "not set"]},
                              fields=["name", "parent", "attempts"], limit=50):
        attempts = (row.attempts or 0) + 1
        values = {"attempts": attempts}
        if attempts >= MAX_ATTEMPTS:
            values.update(status="Failed", error_log="Job macet berulang kali (worker berhenti).")
        else:
            values.update(status="Scheduled", scheduled_at=now_datetime())
        frappe.db.set_value(ROW, row.name, values)
        update_parent_status(row.parent)
    frappe.db.commit()


# ---------------------------------------------------------------------- harian
def renew_tokens():
    horizon = add_days(now_datetime(), TOKEN_RENEW_DAYS)
    rows = frappe.get_all("Social Account", filters={
        "parent": "Social Posting Settings", "enabled": 1, "token_expires_on": ["<", horizon]},
        fields=["name", "channel", "account_name"])
    for row in rows:
        secrets = []
        try:
            account = Account.load(row.name)
            secrets = account.secrets
            get_provider(account).refresh_token()
            frappe.db.commit()
        except Exception as exc:
            frappe.db.rollback()
            msg = redact(f"{type(exc).__name__}: {exc}", secrets)
            frappe.log_error(title=f"Social Posting: perpanjang token {row.channel} gagal"[:140], message=msg)
            _notify_admins(f"Token {row.channel} '{row.account_name}' gagal diperpanjang", msg)


def _notify_admins(subject, message):
    users = frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent")
    for user in set(users) - {"Administrator"}:
        try:
            frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert",
                            "subject": subject, "email_content": message}).insert(ignore_permissions=True)
        except Exception:
            pass


def _metrics_settings():
    window = frappe.db.get_single_value("Social Posting Settings", "metrics_window_days")
    limit = frappe.db.get_single_value("Social Posting Settings", "metrics_row_limit")
    return max(int(window or METRICS_WINDOW_DAYS), 1), max(int(limit or METRICS_ROW_LIMIT), 1)


def pull_metrics():
    window, row_limit = _metrics_settings()
    since = add_days(now_datetime(), -window)
    rows = frappe.get_all(ROW, filters={"status": "Published", "published_on": [">=", since],
                                        "remote_id": ["is", "set"], "parenttype": "Social Post"},
                          fields=["name", "parent", "channel", "account", "account_label", "post_format", "remote_id"],
                          order_by="published_on desc", limit=row_limit)
    today = getdate()
    providers = {}
    for row in rows:
        secrets = []
        try:
            if row.account not in providers:
                account = Account.load(row.account)
                providers[row.account] = get_provider(account)
            provider = providers[row.account]
            secrets = provider.account.secrets
            metrics = provider.fetch_metrics(row.remote_id, row.post_format)
            if metrics:
                values = _upsert_metric(row, today, metrics)
                _upsert_weekly(row, today, values)
            frappe.db.commit()
        except Exception as exc:
            frappe.db.rollback()
            frappe.log_error(title=f"Social Posting: metrik {row.channel} gagal"[:140],
                             message=redact(f"{type(exc).__name__}: {exc}", secrets),
                             reference_doctype="Social Post", reference_name=row.parent)


def _upsert_metric(row, day, m):
    values = {k: int(m.get(k) or 0) for k in ("impressions", "reach", "likes", "comments", "shares")}
    values["engagement_rate"] = compute_engagement_rate(**values)
    existing = frappe.db.get_value("Social Post Metric", {
        "parent": row.parent, "parenttype": "Social Post", "post_channel": row.name, "date": day})
    if existing:
        frappe.db.set_value("Social Post Metric", existing, values, update_modified=False)
        return values
    idx = frappe.db.count("Social Post Metric", {"parent": row.parent, "parenttype": "Social Post"}) + 1
    frappe.get_doc({
        "doctype": "Social Post Metric", "parent": row.parent, "parenttype": "Social Post", "parentfield": "metrics",
        "idx": idx, "date": day, "channel": row.channel, "post_channel": row.name, **values,
    }).insert(ignore_permissions=True)
    return values


def _upsert_weekly(row, day, values):
    """Rekap mingguan (Senin-Minggu): satu baris per kanal per minggu berisi angka terbaru minggu itu.
    Metrik platform bersifat kumulatif, jadi snapshot terakhir sepanjang minggu = nilai akhir minggu."""
    week_start = add_days(day, -getdate(day).weekday())
    existing = frappe.db.get_value("Social Metric Weekly", {"post_channel": row.name, "week_start": week_start})
    if existing:
        frappe.db.set_value("Social Metric Weekly", existing, values, update_modified=False)
        return
    frappe.get_doc({
        "doctype": "Social Metric Weekly", "post": row.parent, "post_channel": row.name, "week_start": week_start,
        "channel": row.channel, "account_label": row.get("account_label") or "", **values,
    }).insert(ignore_permissions=True)


# ---------------------------------------------------------------------- tiap jam
def pull_comments():
    from energyx_social.services.comments import pull_all
    pull_all()


def create_recurring_posts():
    from energyx_social.services.recurring import create_due
    create_due()
