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

BATCH_LIMIT = 10
STALE_MINUTES = 30
TOKEN_RENEW_DAYS = 10
METRICS_WINDOW_DAYS = 30
METRICS_ROW_LIMIT = 500


# ---------------------------------------------------------------------- tiap 5 menit
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
        {"now": now_datetime(), "phase": PUBLISH_PHASE, "limit": BATCH_LIMIT},
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


def pull_metrics():
    since = add_days(now_datetime(), -METRICS_WINDOW_DAYS)
    rows = frappe.get_all(ROW, filters={"status": "Published", "published_on": [">=", since],
                                        "remote_id": ["is", "set"], "parenttype": "Social Post"},
                          fields=["name", "parent", "channel", "account", "post_format", "remote_id"],
                          order_by="published_on desc", limit=METRICS_ROW_LIMIT)
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
                _upsert_metric(row, today, metrics)
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
        return
    idx = frappe.db.count("Social Post Metric", {"parent": row.parent, "parenttype": "Social Post"}) + 1
    frappe.get_doc({
        "doctype": "Social Post Metric", "parent": row.parent, "parenttype": "Social Post", "parentfield": "metrics",
        "idx": idx, "date": day, "channel": row.channel, "post_channel": row.name, **values,
    }).insert(ignore_permissions=True)
