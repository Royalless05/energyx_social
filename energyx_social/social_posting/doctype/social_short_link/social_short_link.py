import re

import frappe
from frappe import _
from frappe.model.document import Document

from energyx_social.services.links import new_code, short_url_for

CODE_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")


class SocialShortLink(Document):
    def autoname(self):
        code = (self.code or "").strip()
        if not code:
            code = new_code(lambda c: frappe.db.exists("Social Short Link", c))
        self.code = code
        self.name = code

    def validate(self):
        self.code = (self.code or "").strip()
        if not CODE_RE.match(self.code):
            frappe.throw(_("Kode hanya boleh huruf, angka, '-' dan '_' (3-32 karakter)."))
        self.target_url = (self.target_url or "").strip()
        if not self.target_url.lower().startswith(("http://", "https://")):
            frappe.throw(_("Target URL harus diawali http:// atau https://"))
        self.short_url = short_url_for(self.code)
