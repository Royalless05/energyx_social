"""Posting berulang: hitung jadwal berikutnya + job pembuat Social Post (selalu lewat approval)."""
import datetime as dt

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
GUARD = 50


def to_time(value) -> dt.time:
    if isinstance(value, dt.time):
        return value
    if isinstance(value, dt.timedelta):
        return (dt.datetime.min + value).time()
    h, m, *rest = str(value or "00:00:00").split(":")
    return dt.time(int(h), int(m), int(float(rest[0])) if rest else 0)


def next_occurrence(frequency, after, post_time, weekday=None, day_of_month=None, start_date=None):
    """Waktu terbit pertama yang STRICTLY setelah `after` sesuai aturan; None bila tidak ada dalam 400 hari."""
    t = to_time(post_time)
    start = getdate(start_date) if start_date else None
    base = after.date()
    for i in range(401):
        d = base + dt.timedelta(days=i)
        if start and d < start:
            continue
        if frequency == "Weekly" and d.weekday() != WEEKDAYS.index(weekday):
            continue
        if frequency == "Monthly" and d.day != int(day_of_month):
            continue
        cand = dt.datetime.combine(d, t)
        if cand > after:
            return cand
    return None


def compute_next(rec, after=None):
    nxt = next_occurrence(rec.frequency, after or now_datetime(), rec.post_time, rec.weekday, rec.day_of_month, rec.start_date)
    if nxt and rec.end_date and nxt.date() > getdate(rec.end_date):
        return None
    return nxt


def build_post(rec, when) -> dict:
    caption = rec.base_caption or ""
    channels = []
    for row in rec.channels:
        tags = frappe.db.get_value("Social Hashtag Template", row.hashtag_template, "hashtags") if row.hashtag_template else ""
        channels.append({"channel": row.channel, "account": row.account, "post_format": row.post_format or None, "active": 1,
                         "hashtag_template": row.hashtag_template,
                         "caption_override": row.caption_override or ((caption + "\n\n" + tags).strip() if tags else None)})
    return {
        "doctype": "Social Post", "title": f"{rec.title} - {when:%d %b %Y}"[:140], "status": rec.initial_status or "Pending Approval",
        "campaign_link": rec.campaign_link, "default_scheduled_at": when, "base_caption": caption,
        "base_media": rec.base_media, "media_asset": rec.media_asset, "recurring_source": rec.name, "channels": channels,
    }


def create_due(now=None):
    """Job per jam: buat postingan untuk jadwal yang masuk jendela `lead_days`, lalu majukan jadwal."""
    now = now or now_datetime()
    for name in frappe.get_all("Social Recurring Post", filters={"enabled": 1, "next_run_on": ["is", "set"]}, pluck="name"):
        try:
            _process(frappe.get_doc("Social Recurring Post", name), now)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"SocialX: recurring {name} error"[:140])


def _process(rec, now):
    lead = int(rec.lead_days or 0)
    nxt, last_post, error = get_datetime(rec.next_run_on), None, ""
    guard = 0
    while nxt and guard < GUARD:
        guard += 1
        if rec.end_date and nxt.date() > getdate(rec.end_date):
            nxt = None
            break
        if add_days(nxt, -lead) > now:
            break  # belum masuk jendela pembuatan
        if nxt <= now:
            error = f"Jadwal {nxt:%Y-%m-%d %H:%M} terlewat (scheduler tidak berjalan?) dan dilewati."
        elif not frappe.db.exists("Social Post", {"recurring_source": rec.name, "default_scheduled_at": nxt}):
            try:
                frappe.db.savepoint("recurring_post")
                last_post = _create(rec, nxt)
                error = ""
            except Exception as exc:
                frappe.db.rollback(save_point="recurring_post")
                error = f"Gagal membuat postingan {nxt:%Y-%m-%d %H:%M}: {exc}"[:500]
                _notify_failure(rec, error)
        nxt = compute_next(rec, nxt)
    values = {"next_run_on": nxt, "last_error": error}
    if last_post:
        values.update(last_post=last_post, last_created_on=now)
    rec.db_set(values, update_modified=False)


def _create(rec, when) -> str:
    frappe.flags.social_recurring = True
    try:
        doc = frappe.get_doc(build_post(rec, when)).insert(ignore_permissions=True)
    finally:
        frappe.flags.social_recurring = False
    doc.db_set("requested_by", rec.owner, update_modified=False)
    from energyx_social.notifications import notify, users_with_role
    if doc.status == "Pending Approval":
        notify(users_with_role("Social Manager"), f"Menunggu approval: {doc.title}", doc.name,
               f"Postingan berulang '{rec.title}' dibuat otomatis dan menunggu persetujuan.")
    return doc.name


def _notify_failure(rec, message):
    from energyx_social.notifications import notify, users_with_role
    notify([rec.owner] + users_with_role("Social Manager"), f"Recurring gagal: {rec.title}", None, message)
