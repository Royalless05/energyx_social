"""Inbox komentar: tarik komentar dari platform, simpan sebagai Social Comment, kirim balasan."""
import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from energyx_social.services.credentials import Account
from energyx_social.services.errors import SocialError, redact
from energyx_social.services.providers import get_provider

COMMENT = "Social Comment"
ROW = "Social Post Channel"
SUPPORTED = ("Instagram", "Facebook Page", "YouTube")  # TikTok & LinkedIn: tidak ada API komentar di app ini
ROW_LIMIT = 200
MAX_REPLY = 2000


def parse_remote_time(value):
    """ISO-8601 dari platform (Z / +0000) -> datetime naif di zona waktu sistem."""
    if not value:
        return now_datetime()
    from datetime import timezone

    from dateutil import parser
    dt = parser.parse(str(value))
    if dt.tzinfo:
        from frappe.utils import convert_utc_to_system_timezone
        dt = convert_utc_to_system_timezone(dt.astimezone(timezone.utc).replace(tzinfo=None)).replace(tzinfo=None)
    return dt


def store_comments(row, comments) -> int:
    """Simpan komentar baru (dedup lewat remote_comment_id). Mengembalikan jumlah yang baru."""
    created = 0
    for c in comments:
        cid = str(c.get("id") or "")
        if not cid or frappe.db.exists(COMMENT, {"remote_comment_id": cid}):
            continue
        frappe.get_doc({
            "doctype": COMMENT, "status": "New", "channel": row.channel, "account": row.account,
            "account_label": row.get("account_label") or "", "post": row.parent, "post_channel": row.name,
            "remote_comment_id": cid, "parent_comment_id": c.get("parent_id") or "",
            "author_name": (c.get("author") or "")[:140], "text": c.get("text") or "",
            "commented_on": parse_remote_time(c.get("created")), "permalink": row.get("permalink") or "",
        }).insert(ignore_permissions=True)
        created += 1
    return created


def _rows(post=None, window_days=14):
    filters = {"status": "Published", "remote_id": ["is", "set"], "parenttype": "Social Post",
               "channel": ["in", list(SUPPORTED)], "active": 1}
    if post:
        filters["parent"] = post
    else:
        filters["published_on"] = [">=", add_days(now_datetime(), -window_days)]
    return frappe.get_all(ROW, filters=filters, order_by="published_on desc", limit=ROW_LIMIT,
                          fields=["name", "parent", "channel", "account", "account_label", "post_format",
                                  "remote_id", "permalink"])


def sync(post=None) -> dict:
    """Tarik komentar untuk satu post (manual) atau semua post terbaru (job). Kegagalan satu kanal tidak menghentikan yang lain."""
    window = int(frappe.db.get_single_value("Social Posting Settings", "comments_window_days") or 14)
    providers, new, errors = {}, 0, []
    for row in _rows(post, window):
        secrets = []
        try:
            if row.account not in providers:
                providers[row.account] = get_provider(Account.load(row.account))
            provider = providers[row.account]
            secrets = provider.account.secrets
            new += store_comments(row, provider.fetch_comments(row.remote_id, row.post_format))
            frappe.db.commit()
        except Exception as exc:
            frappe.db.rollback()
            msg = redact(f"{type(exc).__name__}: {exc}", secrets)
            errors.append(f"{row.channel}: {msg}")
            frappe.log_error(title=f"SocialX: tarik komentar {row.channel} gagal"[:140], message=msg,
                             reference_doctype="Social Post", reference_name=row.parent)
    return {"new": new, "errors": errors}


def pull_all():
    if not frappe.db.get_single_value("Social Posting Settings", "comments_enabled"):
        return
    sync()


def reply(comment_name: str, text: str) -> str:
    text = (text or "").strip()
    if not text:
        frappe.throw(_("Balasan tidak boleh kosong."))
    if len(text) > MAX_REPLY:
        frappe.throw(_("Balasan maksimal {0} karakter.").format(MAX_REPLY))
    doc = frappe.get_doc(COMMENT, comment_name)
    if doc.status == "Replied":
        frappe.throw(_("Komentar ini sudah dibalas."))
    row = frappe.db.get_value(ROW, doc.post_channel, ["remote_id", "account", "status"], as_dict=True)
    if not row or row.status != "Published" or not row.remote_id:
        frappe.throw(_("Postingan asal sudah tidak aktif di platform."))
    secrets = []
    try:
        account = Account.load(row.account)
        secrets = account.secrets
        # Platform hanya mengizinkan balasan 1 tingkat: balas ke komentar teratas.
        target = doc.parent_comment_id or doc.remote_comment_id
        reply_id = get_provider(account).reply_comment(row.remote_id, target, text)
    except SocialError as exc:
        frappe.throw(_("Gagal membalas: {0}").format(redact(str(exc), secrets)))
    doc.db_set({"status": "Replied", "reply_text": text, "replied_by": frappe.session.user,
                "replied_on": now_datetime(), "reply_remote_id": reply_id})
    return reply_id
