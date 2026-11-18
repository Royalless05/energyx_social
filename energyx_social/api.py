"""Endpoint whitelisted. Setiap aksi memeriksa peran + izin dokumen."""
import json

import frappe
from frappe import _

from energyx_social.services.credentials import Account
from energyx_social.services.errors import SocialError, redact
from energyx_social.services.providers import get_provider
from energyx_social.services.publisher import (
    PUBLISH_PHASE, ROW, dispatch_rows,
)
from energyx_social.services.publisher import (
    delete_remote as _delete_remote,
)

MANAGERS = ("Social Manager", "System Manager")


def _rows(post, rows, statuses):
    if isinstance(rows, str):
        rows = json.loads(rows)
    filters = {"parent": post, "parenttype": "Social Post", "active": 1, "status": ["in", statuses]}
    if rows:
        filters["name"] = ["in", rows]
    return frappe.get_all(ROW, filters=filters, pluck="name")


def _guard(post):
    frappe.only_for(MANAGERS)
    frappe.has_permission("Social Post", "write", post, throw=True)


@frappe.whitelist()
def publish_now(post, rows=None):
    _guard(post)
    if frappe.db.get_value("Social Post", post, "status") not in PUBLISH_PHASE:
        frappe.throw(_("Post harus berstatus Approved sebelum dipublikasikan."))
    n = dispatch_rows(post, _rows(post, rows, ["Queued", "Scheduled"]), ("Queued", "Scheduled"))
    return _("{0} kanal dimasukkan ke antrean publikasi.").format(n)


@frappe.whitelist()
def retry(post, rows=None):
    _guard(post)
    if frappe.db.get_value("Social Post", post, "status") not in PUBLISH_PHASE:
        frappe.throw(_("Post tidak dalam fase publikasi."))
    n = dispatch_rows(post, _rows(post, rows, ["Failed"]), ("Failed",), reset_attempts=True)
    return _("{0} kanal dicoba ulang.").format(n)


@frappe.whitelist()
def delete_remote(post, rows=None):
    _guard(post)
    return "; ".join(_delete_remote(post, _rows(post, rows, ["Published"]))) or _("Tidak ada yang dihapus.")


@frappe.whitelist()
def test_connection(account):
    """Hanya System Manager. Berhasil -> enabled=1; gagal -> enabled=0."""
    frappe.only_for("System Manager")
    secrets = []
    try:
        acc = Account.load(account)
        secrets = acc.secrets
        detail = get_provider(acc).test_connection()
        ok, message = True, _("Koneksi berhasil: {0}").format(detail)
    except SocialError as exc:
        ok, message = False, redact(f"{type(exc).__name__}: {exc}", secrets)
    except Exception as exc:
        frappe.log_error(title="Social Posting: test connection error", message=redact(frappe.get_traceback(), secrets))
        ok, message = False, redact(f"Galat tak terduga: {type(exc).__name__}", secrets)
    frappe.db.set_value("Social Account", account, {"enabled": 1 if ok else 0, "connection_status": message[:500]})
    frappe.clear_document_cache("Social Posting Settings", "Social Posting Settings")
    return {"ok": ok, "message": message}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_accounts(doctype, txt, searchfield, start, page_len, filters):
    """Query Link untuk Social Account: hanya akun aktif, tanpa kredensial. Editor tidak perlu akses Settings."""
    frappe.only_for(("Social Editor",) + MANAGERS)
    channel = (filters or {}).get("channel")
    cond = "and channel = %(channel)s" if channel else ""
    return frappe.db.sql(
        f"""
        select name, concat(channel, ' - ', account_name)
        from `tabSocial Account`
        where parent = 'Social Posting Settings' and parenttype = 'Social Posting Settings' and enabled = 1
          and (account_name like %(txt)s or name like %(txt)s) {cond}
        order by account_name
        limit %(start)s, %(page_len)s
        """,
        {"txt": f"%{txt}%", "channel": channel, "start": int(start), "page_len": int(page_len)},
    )


def has_app_permission() -> bool:
    """Tampilkan ikon app di halaman Apps hanya untuk user yang berhak."""
    allowed = {"System Manager", "Social Manager", "Social Editor"}
    return bool(allowed & set(frappe.get_roles()))
