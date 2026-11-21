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
STAFF = ("Social Editor",) + MANAGERS


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


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_hashtag_templates(doctype, txt, searchfield, start, page_len, filters):
    """Query Link template hashtag yang cocok dengan kanal/akun baris. Template tanpa kanal/akun berlaku untuk semua."""
    frappe.only_for(("Social Editor",) + MANAGERS)
    f = filters or {}
    return frappe.db.sql(
        """
        select name, left(hashtags, 60)
        from `tabSocial Hashtag Template`
        where name like %(txt)s
          and ifnull(channel, '') in ('', %(channel)s)
          and ifnull(account, '') in ('', %(account)s)
        order by is_default desc, name
        limit %(start)s, %(page_len)s
        """,
        {"txt": f"%{txt}%", "channel": f.get("channel") or "", "account": f.get("account") or "",
         "start": int(start), "page_len": int(page_len)},
    )


@frappe.whitelist()
def get_default_hashtag_template(channel, account=None):
    """Template default: khusus akun dulu, lalu per kanal, lalu umum. None bila tidak ada."""
    frappe.only_for(("Social Editor",) + MANAGERS)
    queries = []
    if account:
        queries.append(("ifnull(account, '') = %(account)s", {"account": account}))
    queries.append(("ifnull(account, '') = '' and ifnull(channel, '') = %(channel)s", {"channel": channel or ""}))
    queries.append(("ifnull(account, '') = '' and ifnull(channel, '') = ''", {}))
    for cond, params in queries:
        found = frappe.db.sql(
            f"select name from `tabSocial Hashtag Template` where is_default = 1 and {cond} order by modified desc limit 1",
            params,
        )
        if found:
            return found[0][0]
    return None


# ---------------------------------------------------------------------- inbox komentar
@frappe.whitelist()
def reply_comment(comment, text):
    frappe.only_for(STAFF)
    frappe.has_permission("Social Comment", "write", comment, throw=True)
    from energyx_social.services.comments import reply
    reply(comment, text)
    return _("Balasan terkirim.")


@frappe.whitelist()
def set_comment_status(comment, status):
    frappe.only_for(STAFF)
    if status not in ("New", "Ignored"):
        frappe.throw(_("Status tidak valid."))
    frappe.has_permission("Social Comment", "write", comment, throw=True)
    if frappe.db.get_value("Social Comment", comment, "status") == "Replied":
        frappe.throw(_("Komentar yang sudah dibalas tidak dapat diubah."))
    frappe.db.set_value("Social Comment", comment, "status", status)
    return status


@frappe.whitelist()
def pull_comments(post):
    frappe.only_for(STAFF)
    frappe.has_permission("Social Post", "read", post, throw=True)
    from energyx_social.services.comments import sync
    result = sync(post)
    msg = _("{0} komentar baru.").format(result["new"])
    if result["errors"]:
        msg += " " + "; ".join(result["errors"])[:300]
    return msg


# ---------------------------------------------------------------------- media library, link, bulk
@frappe.whitelist()
def asset_usage(asset):
    """Berapa postingan yang memakai file aset ini."""
    frappe.only_for(STAFF)
    file_url = frappe.db.get_value("Social Media Asset", asset, "file")
    if not file_url:
        return {"count": 0, "posts": []}
    posts = set(frappe.get_all("Social Post", filters={"base_media": file_url}, pluck="name"))
    posts |= set(frappe.get_all("Social Post Channel", filters={"media_override": file_url, "parenttype": "Social Post"}, pluck="parent"))
    posts |= set(frappe.get_all("Social Post Media", filters={"media": file_url, "parenttype": "Social Post"}, pluck="parent"))
    return {"count": len(posts), "posts": sorted(posts)[:20]}


@frappe.whitelist()
def link_stats(post):
    frappe.only_for(STAFF)
    frappe.has_permission("Social Post", "read", post, throw=True)
    rows = frappe.get_all("Social Short Link", filters={"post": post}, fields=["code", "channel", "clicks", "short_url"])
    return {"links": len(rows), "clicks": sum(r.clicks or 0 for r in rows), "rows": rows}


@frappe.whitelist()
def bulk_schedule(file_url, dry_run=1):
    """Impor CSV/XLSX -> Social Post Draft. dry_run=1 hanya memvalidasi."""
    frappe.only_for(STAFF)
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        frappe.throw(_("File tidak ditemukan."))
    doc = frappe.get_doc("File", name)
    from energyx_social.services.bulk import run
    return run(doc.get_content(), doc.file_name or file_url, dry_run=str(dry_run) not in ("0", "False", "false", ""))


def has_app_permission() -> bool:
    """Tampilkan ikon app di halaman Apps hanya untuk user yang berhak."""
    allowed = {"System Manager", "Social Manager", "Social Editor", "Social Final Approver"}
    return bool(allowed & set(frappe.get_roles()))
