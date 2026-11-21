"""Short link publik: /s/<kode> -> 302 ke URL tujuan (dengan UTM) + hitung klik."""
import re

import frappe
from frappe.utils import getdate, now_datetime

no_cache = 1
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")


def get_context(context):
    code = frappe.form_dict.get("code") or ""
    row = None
    if CODE_RE.match(code):
        row = frappe.db.get_value("Social Short Link", code, ["destination", "target_url", "enabled", "expires_on"], as_dict=True)
    if not row or not row.enabled or (row.expires_on and getdate(row.expires_on) < getdate()):
        raise frappe.DoesNotExistError
    url = (row.destination or row.target_url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise frappe.DoesNotExistError
    try:
        if frappe.request.method == "GET":
            frappe.db.sql("update `tabSocial Short Link` set clicks = ifnull(clicks, 0) + 1, last_clicked_on = %s where name = %s",
                          (now_datetime(), code))
            frappe.db.commit()
    except Exception:  # menghitung klik tidak boleh menggagalkan pengalihan
        frappe.db.rollback()
    frappe.local.flags.redirect_location = url
    raise frappe.Redirect
