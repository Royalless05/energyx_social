"""Orkestrasi publikasi satu kanal (Social Post Channel) + status induk. Idempoten dan aman diulang."""
import contextlib
import json

import frappe
from frappe.utils import add_to_date, now_datetime

from energyx_social.services.credentials import Account
from energyx_social.services.errors import PermanentError, SocialError, redact
from energyx_social.services.links import resolve_mode, track_text
from energyx_social.services.media import MediaService, multi_limits, requires_media
from energyx_social.services.providers import get_provider
from energyx_social.services.providers.base import PublishContext

ROW = "Social Post Channel"
POST = "Social Post"
MAX_ATTEMPTS = 5
PUBLISH_PHASE = ("Approved", "Publishing", "Partial")
ERROR_LOG_LIMIT = 20000


# ---------------------------------------------------------------------- claim & enqueue
def claim_row(row_name: str, from_statuses) -> bool:
    """Compare-and-set dengan row lock: hanya satu pemanggil yang menang. Caller wajib commit."""
    status = frappe.db.get_value(ROW, row_name, "status", for_update=True)
    if status not in from_statuses:
        return False
    frappe.db.set_value(ROW, row_name, "status", "Publishing")
    return True


def enqueue_row(post: str, row_name: str):
    frappe.enqueue(
        "energyx_social.services.publisher.publish_channel",
        queue="long", timeout=1200, enqueue_after_commit=True,
        job_id=f"social_publish::{row_name}", deduplicate=True,
        post=post, row=row_name,
    )


def dispatch_rows(post: str, row_names, from_statuses, reset_attempts=False) -> int:
    count = 0
    for name in row_names:
        if reset_attempts:
            frappe.db.set_value(ROW, name, "attempts", 0)
        if claim_row(name, from_statuses):
            enqueue_row(post, name)
            count += 1
    if count:
        update_parent_status(post)
    return count


# ---------------------------------------------------------------------- the job
def publish_channel(post: str, row: str):
    data = frappe.db.get_value(
        ROW, row,
        ["name", "parent", "channel", "account", "post_format", "status", "remote_id", "attempts",
         "provider_state", "caption_override", "media_override", "thumbnail", "first_comment"],
        as_dict=True,
    )
    if not data or data.parent != post:
        return
    if data.remote_id:  # idempotensi: sudah terbit, jangan kirim ulang
        _mark_published_if_needed(data)
        return
    if data.status != "Publishing":
        return

    parent = frappe.db.get_value(POST, post, ["status", "title", "base_caption", "base_media", "link_tracking", "utm_campaign", "campaign_link"],
        as_dict=True)
    if parent.status not in PUBLISH_PHASE:  # di-hold / dibatalkan setelah diklaim
        frappe.db.set_value(ROW, row, "status", "Scheduled" if parent.status == "On Hold" else "Queued")
        frappe.db.commit()
        return

    secrets = []
    try:
        account = Account.load(data.account)
        secrets = account.secrets
        if not account.enabled:
            raise PermanentError("Akun belum aktif (Test Connection belum lolos).")
        if account.channel != data.channel:
            raise PermanentError("Kanal tidak cocok dengan akun.")
        provider = get_provider(account)

        def save_state(value):
            frappe.db.set_value(ROW, row, "provider_state", value, update_modified=False)
            frappe.db.commit()  # checkpoint: bila worker mati, percobaan berikutnya melanjutkan

        source = data.media_override or parent.base_media
        with contextlib.ExitStack() as stack:
            svc = MediaService()
            media, items = None, []
            if multi_limits(data.channel, data.post_format):
                sources = frappe.get_all("Social Post Media", filters={"parent": post, "parenttype": "Social Post"},
                                         pluck="media", order_by="idx asc")
                req = provider.media_requirements(data.post_format)
                items = [stack.enter_context(svc.prepared(src, data.channel, data.post_format, **req)) for src in sources if src]
            elif requires_media(data.channel, data.post_format):
                media = stack.enter_context(
                    svc.prepared(source, data.channel, data.post_format, **provider.media_requirements(data.post_format)))
            thumb = None
            if data.thumbnail and data.channel == "YouTube":
                thumb = stack.enter_context(svc.prepared(data.thumbnail, "YouTube", "Thumbnail", local=True))
            mode = resolve_mode(parent.link_tracking, frappe.db.get_single_value("Social Posting Settings", "link_tracking_default"))
            track = lambda text: track_text(  # noqa: E731
                text, post=post, channel=data.channel, post_format=data.post_format, title=parent.title or "",
                mode=mode, campaign_link=parent.campaign_link, utm_campaign=parent.utm_campaign)
            ctx = PublishContext(
                post=post, row=row, title=parent.title or "",
                caption=track(data.caption_override or parent.base_caption or ""),
                post_format=data.post_format, first_comment=track(data.first_comment or ""), media=media, thumbnail=thumb,
                provider_state=data.provider_state or "", save_state=save_state, media_items=items,
            )
            result = provider.publish(ctx)

        values = {
            "status": "Published", "remote_id": result.remote_id, "permalink": result.permalink or "",
            "published_on": now_datetime(), "provider_state": None, "error_log": "",
        }
        if result.warnings:
            values["error_log"] = _stamp("Peringatan: " + "; ".join(result.warnings), secrets)
        frappe.db.set_value(ROW, row, values)
        update_parent_status(post)
        frappe.db.commit()

    except SocialError as exc:
        frappe.db.rollback()
        _handle_failure(post, row, data, exc, secrets)
    except Exception as exc:  # galat tak terduga: jangan biarkan baris menggantung di 'Publishing'
        frappe.db.rollback()
        _handle_failure(post, row, data, exc, secrets, unexpected=True)


def _stamp(message: str, secrets) -> str:
    return redact(f"[{now_datetime():%Y-%m-%d %H:%M:%S}] {message}", secrets)


def _handle_failure(post, row, data, exc, secrets, unexpected=False):
    attempts = (data.attempts or 0) + 1
    minutes = getattr(exc, "reschedule_minutes", None)
    retry = bool(minutes) and attempts < MAX_ATTEMPTS and not unexpected
    message = f"{type(exc).__name__}: {exc}"
    previous = frappe.db.get_value(ROW, row, "error_log") or ""
    entry = _stamp(f"Percobaan {attempts}: {message}" + (f" -> dijadwalkan ulang {minutes} menit" if retry else ""), secrets)
    values = {"attempts": attempts, "error_log": (entry + "\n" + previous)[:ERROR_LOG_LIMIT]}
    if retry:
        values.update(status="Scheduled", scheduled_at=add_to_date(now_datetime(), minutes=minutes))
    else:
        values["status"] = "Failed"
    frappe.db.set_value(ROW, row, values)
    update_parent_status(post)
    if not retry:
        from energyx_social.notifications import notify_channel_failed
        notify_channel_failed(post, data.channel, redact(message, secrets))
    frappe.db.commit()
    frappe.log_error(
        title=f"Social Posting: {data.channel} gagal ({post})"[:140],
        message=redact(frappe.get_traceback() if unexpected else message, secrets),
        reference_doctype=POST, reference_name=post,
    )


def _mark_published_if_needed(data):
    if data.status != "Published":
        frappe.db.set_value(ROW, data.name, {"status": "Published", "provider_state": None})
        update_parent_status(data.parent)
        frappe.db.commit()


# ---------------------------------------------------------------------- parent status
def update_parent_status(post: str):
    current = frappe.db.get_value(POST, post, "status")
    if current not in PUBLISH_PHASE + ("Published",):
        return
    rows = frappe.get_all(ROW, filters={"parent": post, "parenttype": POST, "active": 1}, pluck="status")
    live = [s for s in rows if s != "Deleted"]
    if not live:
        new = "Cancelled" if rows else current
    elif "Publishing" in live:
        new = "Publishing"
    elif all(s == "Published" for s in live):
        new = "Published"
    elif "Published" in live:
        new = "Partial"
    else:
        new = "Approved"
    if new != current:
        frappe.db.set_value(POST, post, "status", new)
        if new in ("Published", "Partial"):
            from energyx_social.notifications import notify_publish_result
            notify_publish_result(post, new)


# ---------------------------------------------------------------------- remove from platform
def delete_remote(post: str, row_names) -> list:
    """Hapus dari platform bila API mendukung. Mengembalikan daftar pesan per kanal."""
    messages = []
    for name in row_names:
        data = frappe.db.get_value(ROW, name, ["parent", "channel", "account", "remote_id", "status"], as_dict=True)
        if not data or data.parent != post or data.status != "Published" or not data.remote_id:
            continue
        secrets = []
        try:
            account = Account.load(data.account)
            secrets = account.secrets
            provider = get_provider(account)
            provider.ensure_fresh_token()
            provider.delete(data.remote_id)
            frappe.db.set_value(ROW, name, {"status": "Deleted", "error_log": _stamp("Dihapus dari platform.", secrets)})
            messages.append(f"{data.channel}: dihapus")
        except SocialError as exc:
            frappe.log_error(title=f"Social Posting: hapus {data.channel} gagal ({post})"[:140],
                             message=redact(str(exc), secrets), reference_doctype=POST, reference_name=post)
            messages.append(f"{data.channel}: {redact(str(exc), secrets)}")
    update_parent_status(post)
    return messages
